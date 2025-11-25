"""
Enhanced Sanctions Screener v2.0
Multi-layer matching with confidence scoring, document search, and validation

Features:
- Multi-layer matching engine (exact, high confidence, moderate, low)
- Document-based screening (passport, national ID, tax ID, vessel IMO)
- Short name protection and common name filtering
- Nationality coherence validation
- Quality indicators and recommendation engine
- Configurable thresholds via config.yaml

SECURITY: Input validation and secure XML parsing to prevent attacks.
"""

import csv
import json
import uuid
import logging
import re
import unicodedata
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Optional, Any, Tuple
from dataclasses import dataclass, field

from rapidfuzz import fuzz

# Try to import lxml for better XML parsing
try:
    from lxml import etree
    HAS_LXML = True
except ImportError:
    import xml.etree.ElementTree as etree
    HAS_LXML = False

from config_manager import get_config, ConfigManager
from xml_utils import sanitize_for_logging, secure_parse, get_secure_parser

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Unicode script ranges for internationalization
# CJK Unified Ideographs (Chinese)
UNICODE_CJK_START = '\u4E00'
UNICODE_CJK_END = '\u9FFF'
# Arabic
UNICODE_ARABIC_START = '\u0600'
UNICODE_ARABIC_END = '\u06FF'
# Cyrillic
UNICODE_CYRILLIC_START = '\u0400'
UNICODE_CYRILLIC_END = '\u04FF'

# Input validation patterns
NAME_PATTERN = re.compile(r'^[A-Za-zÀ-ÿ\s\-\.\'\,\u0600-\u06FF\u0400-\u04FF\u4E00-\u9FFF]{2,200}$')
DOB_PATTERN = re.compile(r'^\d{4}(-\d{2}(-\d{2})?)?$')  # YYYY, YYYY-MM, or YYYY-MM-DD
DOC_NUMBER_PATTERN = re.compile(r'^[A-Za-z0-9\-\s\.]{1,50}$')


@dataclass
class ConfidenceBreakdown:
    """Detailed confidence score breakdown"""
    overall: float
    name_score: float = 0.0
    document_score: float = 0.0
    dob_score: float = 0.0
    nationality_score: float = 0.0
    address_score: float = 0.0
    
    def to_dict(self) -> Dict[str, float]:
        return {
            'overall': round(self.overall, 2),
            'name': round(self.name_score, 2),
            'document': round(self.document_score, 2),
            'dob': round(self.dob_score, 2),
            'nationality': round(self.nationality_score, 2),
            'address': round(self.address_score, 2)
        }


@dataclass
class MatchResult:
    """Complete match result with confidence breakdown and flags"""
    entity: Dict[str, Any]
    confidence: ConfidenceBreakdown
    flags: List[str] = field(default_factory=list)
    recommendation: str = 'MANUAL_REVIEW'
    match_layer: int = 4  # 1=exact, 2=high, 3=moderate, 4=low
    matched_name: str = ''
    matched_document: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'entity': self.entity,
            'confidence': self.confidence.to_dict(),
            'flags': self.flags,
            'recommendation': self.recommendation,
            'match_layer': self.match_layer,
            'matched_name': self.matched_name,
            'matched_document': self.matched_document
        }


@dataclass  
class ScreeningInput:
    """Input data for screening"""
    name: str
    document_number: Optional[str] = None
    document_type: Optional[str] = None
    date_of_birth: Optional[str] = None
    nationality: Optional[str] = None
    country: Optional[str] = None


class InputValidationError(ValueError):
    """Raised when input validation fails
    
    Attributes:
        field: The field that failed validation
        code: Error code for programmatic handling
        message: Human-readable error message
        suggestion: Optional suggestion for fixing the error
    """
    def __init__(self, message: str, field: str = "unknown", code: str = "VALIDATION_ERROR", suggestion: str = ""):
        self.field = field
        self.code = code
        self.suggestion = suggestion
        super().__init__(message)


def validate_screening_input(input_data: ScreeningInput, config: Optional['ConfigManager'] = None) -> None:
    """Validate screening input data for security and correctness
    
    Supports international names including Chinese, Arabic, Cyrillic, etc.
    Validates against blocked characters that could indicate injection attacks.
    
    Args:
        input_data: ScreeningInput to validate
        config: Optional configuration manager for validation settings
        
    Raises:
        InputValidationError: If validation fails with detailed error info
    """
    # Get config or use defaults
    if config is None:
        config = get_config()
    
    iv_config = config.input_validation
    
    # Validate name length
    name = input_data.name or ""
    name_stripped = name.strip()
    
    if len(name_stripped) < iv_config.name_min_length:
        raise InputValidationError(
            f"Name too short ({len(name_stripped)} chars, minimum {iv_config.name_min_length}). Example: 'Li'",
            field="name",
            code="NAME_TOO_SHORT",
            suggestion=f"Provide a name with at least {iv_config.name_min_length} characters"
        )
    
    if len(name) > iv_config.name_max_length:
        raise InputValidationError(
            f"Name too long ({len(name)} chars, maximum {iv_config.name_max_length})",
            field="name",
            code="NAME_TOO_LONG",
            suggestion=f"Shorten the name to {iv_config.name_max_length} characters or less"
        )
    
    # Check for blocked characters (potential injection attacks)
    blocked = iv_config.blocked_characters
    found_blocked = [c for c in name if c in blocked]
    if found_blocked:
        # Log security event
        logger.warning("SECURITY: Blocked characters detected in name input: %s", 
                      sanitize_for_logging(name))
        raise InputValidationError(
            f"Name contains blocked characters: {found_blocked}. Allowed: letters, spaces, hyphens, periods, apostrophes",
            field="name",
            code="BLOCKED_CHARACTERS",
            suggestion="Remove special characters like < > { } [ ] | \\ ; ` $"
        )
    
    # Validate Unicode categories if Unicode is allowed
    if iv_config.allow_unicode_names:
        # Allow Unicode letters (any script), spaces, common punctuation
        for char in name:
            category = unicodedata.category(char)
            # L* = letters, Zs = space separator, Pd = dash punctuation, Po = other punctuation
            # Cc = control chars (blocked), Cs = surrogates (blocked)
            if category.startswith('C'):  # Control or format characters
                logger.warning("SECURITY: Control character detected in name: %s", 
                              sanitize_for_logging(name))
                raise InputValidationError(
                    f"Name contains invalid control character (code: {ord(char)})",
                    field="name",
                    code="CONTROL_CHARACTER",
                    suggestion="Remove invisible or control characters from the name"
                )
    else:
        # Strict Latin-only mode
        if not NAME_PATTERN.match(name):
            logger.warning("Invalid name format (Latin-only mode): %s", sanitize_for_logging(name))
            raise InputValidationError(
                "Name must contain only Latin letters, spaces, hyphens, periods, and apostrophes",
                field="name",
                code="INVALID_FORMAT",
                suggestion="Use Latin characters only (A-Z, a-z, À-ÿ)"
            )
    
    # Validate DOB if provided
    if input_data.date_of_birth:
        if not DOB_PATTERN.match(input_data.date_of_birth):
            raise InputValidationError(
                f"DOB must be ISO 8601 format. Got: '{input_data.date_of_birth}'. Example: '1980-01-15'",
                field="date_of_birth",
                code="INVALID_DOB_FORMAT",
                suggestion="Use format YYYY, YYYY-MM, or YYYY-MM-DD"
            )
    
    # Validate document number if provided
    if input_data.document_number:
        if len(input_data.document_number) > iv_config.document_max_length:
            raise InputValidationError(
                f"Document number too long ({len(input_data.document_number)} chars, maximum {iv_config.document_max_length})",
                field="document_number",
                code="DOCUMENT_TOO_LONG",
                suggestion=f"Shorten to {iv_config.document_max_length} characters or less"
            )
        if not DOC_NUMBER_PATTERN.match(input_data.document_number):
            raise InputValidationError(
                "Document number contains invalid characters. Allowed: letters, numbers, spaces, hyphens, periods",
                field="document_number",
                code="INVALID_DOCUMENT_FORMAT",
                suggestion="Use only alphanumeric characters, spaces, hyphens, and periods"
            )


class EnhancedSanctionsScreener:
    """Enhanced screener with multi-layer matching and comprehensive validation"""
    
    def __init__(self, config: Optional[ConfigManager] = None, data_dir: str = "sanctions_data"):
        """Initialize screener
        
        Args:
            config: Configuration manager instance
            data_dir: Directory containing sanctions data files
        """
        self.config = config or get_config()
        self.data_dir = Path(data_dir)
        self.entities: List[Dict[str, Any]] = []
        
        # Document index for fast lookup
        self._document_index: Dict[str, List[Dict[str, Any]]] = {}
        
        # Common names set (normalized)
        self._common_names: set = set()
        for name in self.config.matching.common_names:
            self._common_names.add(self._normalize_name(name))
        
        # Reports directory
        self.reports_dir = Path("reports")
        self.reports_dir.mkdir(exist_ok=True)
        # Audit log subdirectory
        (self.reports_dir / "audit_log").mkdir(exist_ok=True)
        
        # Screening history for audit trail (with size limit to prevent memory issues)
        self.screening_history: List[Dict[str, Any]] = []
        self._max_history_size = 10000  # Limit to prevent memory issues in long-running apps
        
        logger.info(f"🔧 Enhanced Screener initialized:")
        logger.info(f"   - Data directory: {self.data_dir}")
        logger.info(f"   - Name threshold: {self.config.matching.name_threshold}%")
        logger.info(f"   - Short name threshold: {self.config.matching.short_name_threshold}%")
        logger.info(f"   - Common names monitored: {len(self._common_names)}")
    
    def load_ofac(self) -> int:
        """Load OFAC entities from XML file
        
        Returns:
            Number of entities loaded
        """
        xml_file = self.data_dir / "sdn_enhanced.xml"
        if not xml_file.exists():
            logger.warning(f"⚠ OFAC file not found: {xml_file}")
            return 0
        
        # Extract namespace dynamically
        ns = self._extract_namespace(xml_file)
        
        # Use secure XML parsing to prevent XXE attacks
        tree, root = secure_parse(xml_file)
        count = 0
        
        for entity_elem in root.findall(f'.//{ns}entity'):
            entity = self._parse_ofac_entity(entity_elem, ns)
            if entity:
                self.entities.append(entity)
                self._index_documents(entity)
                count += 1
        
        logger.info(f"✓ Loaded {count} OFAC entities")
        return count
    
    def _extract_namespace(self, xml_path: Path) -> str:
        """Extract namespace from XML root"""
        try:
            with open(xml_path, 'rb') as f:
                for event, elem in etree.iterparse(f, events=('start',)):
                    tag = elem.tag
                    if tag.startswith('{'):
                        ns_end = tag.index('}')
                        return tag[:ns_end + 1]
                    break
        except Exception as e:
            logger.warning(f"Could not extract namespace: {e}")
        return ''
    
    def _parse_ofac_entity(self, elem: Any, ns: str) -> Optional[Dict[str, Any]]:
        """Parse OFAC entity element"""
        entity_id = elem.get('id')
        if not entity_id:
            return None
        
        # Entity type
        entity_type_elem = elem.find(f'{ns}entityType')
        entity_type = entity_type_elem.text if entity_type_elem is not None else 'entity'
        
        # Extract names
        all_names = []
        first_name = None
        last_name = None
        
        names_section = elem.find(f'{ns}names')
        if names_section is not None:
            for name_tag in names_section.findall(f'{ns}name'):
                translations = name_tag.find(f'{ns}translations')
                if translations is not None:
                    for translation in translations.findall(f'{ns}translation'):
                        formatted_full = translation.find(f'{ns}formattedFullName')
                        if formatted_full is not None and formatted_full.text:
                            all_names.append(formatted_full.text.strip())
                        
                        if entity_type.lower() == 'individual':
                            fn = translation.find(f'{ns}formattedFirstName')
                            ln = translation.find(f'{ns}formattedLastName')
                            if fn is not None and fn.text and not first_name:
                                first_name = fn.text.strip()
                            if ln is not None and ln.text and not last_name:
                                last_name = ln.text.strip()
        
        if not all_names:
            return None
        
        all_names = list(dict.fromkeys(all_names))
        
        entity = {
            'id': entity_id,
            'source': 'OFAC',
            'type': entity_type.lower(),
            'name': all_names[0],
            'all_names': all_names,
            'aliases': all_names[1:] if len(all_names) > 1 else [],
            'firstName': first_name,
            'lastName': last_name,
            'countries': [],
            'identity_documents': [],
            'features': []
        }
        
        # Parse identity documents (OFAC Enhanced XML: <identityDocuments>/<identityDocument>/<documentNumber>)
        identity_docs_section = elem.find(f'{ns}identityDocuments')
        if identity_docs_section is not None:
            for doc in identity_docs_section.findall(f'{ns}identityDocument'):
                doc_type = self._get_text(doc, f'{ns}type')
                doc_number = self._get_text(doc, f'{ns}documentNumber')
                if doc_number:
                    entity['identity_documents'].append({
                        'type': doc_type or 'Unknown',
                        'number': doc_number,
                        'issuingCountry': self._get_text(doc, f'{ns}issuingCountry'),
                        'issueDate': self._get_text(doc, f'{ns}issueDate'),
                        'expirationDate': self._get_text(doc, f'{ns}expirationDate')
                    })
        
        # Parse features
        features_section = elem.find(f'{ns}features')
        if features_section is not None:
            for feature in features_section.findall(f'{ns}feature'):
                feature_type = feature.find(f'{ns}type')
                value_elem = feature.find(f'{ns}value')
                
                if feature_type is not None and feature_type.text:
                    ft = feature_type.text.upper()
                    value = value_elem.text if value_elem is not None and value_elem.text else ''
                    
                    entity['features'].append({
                        'type': feature_type.text,
                        'value': value
                    })
                    
                    # Extract specific values
                    if 'DOB' in ft or ('DATE' in ft and 'BIRTH' in ft):
                        entity['dateOfBirth'] = value
                    elif 'POB' in ft or ('PLACE' in ft and 'BIRTH' in ft):
                        entity['placeOfBirth'] = value
                    elif 'NATIONAL' in ft:
                        entity['nationality'] = value
                        if value:
                            entity['countries'].append(value)
                    elif 'CITIZEN' in ft:
                        entity['citizenship'] = value
                        if value:
                            entity['countries'].append(value)
                    elif 'GENDER' in ft:
                        entity['gender'] = value
                    elif 'TITLE' in ft:
                        entity['title'] = value
                    elif 'IMO' in ft or 'VESSEL' in ft:
                        entity['vesselIMO'] = value
        
        # Parse addresses for countries
        addresses_section = elem.find(f'{ns}addresses')
        if addresses_section is not None:
            entity['addresses'] = []
            for addr in addresses_section.findall(f'{ns}address'):
                addr_dict = {}
                for field in ['addressLine1', 'city', 'stateProvince', 'postalCode', 'country']:
                    val = self._get_text(addr, f'{ns}{field}')
                    if val:
                        addr_dict[field] = val
                if addr_dict:
                    entity['addresses'].append(addr_dict)
                    if addr_dict.get('country'):
                        entity['countries'].append(addr_dict['country'])
        
        # Parse sanctions programs
        programs = elem.find(f'{ns}sanctionsPrograms')
        if programs is not None:
            program_list = [p.text for p in programs.findall(f'{ns}sanctionsProgram') if p.text]
            entity['program'] = '; '.join(program_list) if program_list else None
        
        entity['countries'] = list(set(entity['countries']))
        
        return entity
    
    def _get_text(self, elem: Any, path: str) -> Optional[str]:
        """Get text from element"""
        child = elem.find(path)
        if child is not None and child.text:
            return child.text.strip()
        return None
    
    def load_un(self) -> int:
        """Load UN entities from XML file
        
        Returns:
            Number of entities loaded
        """
        xml_file = self.data_dir / "un_consolidated.xml"
        if not xml_file.exists():
            logger.warning(f"⚠ UN file not found: {xml_file}")
            return 0
        
        # Use secure XML parsing to prevent XXE attacks
        tree, root = secure_parse(xml_file)
        count = 0
        
        # Parse individuals
        for individual in root.findall('.//INDIVIDUAL'):
            entity = self._parse_un_individual(individual)
            if entity:
                self.entities.append(entity)
                self._index_documents(entity)
                count += 1
        
        # Parse entities
        for entity_elem in root.findall('.//ENTITY'):
            entity = self._parse_un_entity(entity_elem)
            if entity:
                self.entities.append(entity)
                self._index_documents(entity)
                count += 1
        
        logger.info(f"✓ Loaded {count} UN entities")
        return count
    
    def _parse_un_individual(self, elem: Any) -> Optional[Dict[str, Any]]:
        """Parse UN individual element"""
        dataid_elem = elem.find('DATAID')
        if dataid_elem is None or not dataid_elem.text:
            return None
        
        first_name = self._get_un_text(elem, 'FIRST_NAME') or ''
        second_name = self._get_un_text(elem, 'SECOND_NAME') or ''
        third_name = self._get_un_text(elem, 'THIRD_NAME') or ''
        fourth_name = self._get_un_text(elem, 'FOURTH_NAME') or ''
        
        name_parts = [n for n in [first_name, second_name, third_name, fourth_name] if n]
        if not name_parts:
            return None
        
        primary_name = ' '.join(name_parts).strip()
        
        entity = {
            'id': dataid_elem.text,
            'source': 'UN',
            'type': 'individual',
            'name': primary_name,
            'all_names': [primary_name],
            'aliases': [],
            'firstName': first_name,
            'lastName': fourth_name or third_name or second_name,
            'countries': [],
            'identity_documents': [],
            'program': 'UN'
        }
        
        # Parse aliases
        for alias in elem.findall('.//INDIVIDUAL_ALIAS'):
            alias_name = self._get_un_text(alias, 'ALIAS_NAME')
            if alias_name:
                entity['aliases'].append(alias_name)
                entity['all_names'].append(alias_name)
        
        # DOB
        dob = self._get_un_text(elem, 'DATE_OF_BIRTH')
        if dob:
            entity['dateOfBirth'] = dob
        
        # Nationality
        for nat in elem.findall('.//NATIONALITY/VALUE'):
            if nat.text:
                entity['nationality'] = nat.text
                entity['countries'].append(nat.text)
                break
        
        # Documents
        for doc in elem.findall('.//INDIVIDUAL_DOCUMENT'):
            doc_type = self._get_un_text(doc, 'TYPE_OF_DOCUMENT')
            doc_number = self._get_un_text(doc, 'NUMBER')
            if doc_number:
                entity['identity_documents'].append({
                    'type': doc_type or 'Unknown',
                    'number': doc_number,
                    'issuingCountry': self._get_un_text(doc, 'ISSUING_COUNTRY')
                })
        
        entity['countries'] = list(set(entity['countries']))
        
        return entity
    
    def _parse_un_entity(self, elem: Any) -> Optional[Dict[str, Any]]:
        """Parse UN entity element"""
        dataid_elem = elem.find('DATAID')
        name_elem = elem.find('FIRST_NAME')
        
        if dataid_elem is None or name_elem is None:
            return None
        if not dataid_elem.text or not name_elem.text:
            return None
        
        entity = {
            'id': dataid_elem.text,
            'source': 'UN',
            'type': 'entity',
            'name': name_elem.text,
            'all_names': [name_elem.text],
            'aliases': [],
            'countries': [],
            'identity_documents': [],
            'program': 'UN'
        }
        
        # Aliases
        for alias in elem.findall('.//ENTITY_ALIAS'):
            alias_name = self._get_un_text(alias, 'ALIAS_NAME')
            if alias_name:
                entity['aliases'].append(alias_name)
                entity['all_names'].append(alias_name)
        
        return entity
    
    def _get_un_text(self, elem: Any, path: str) -> Optional[str]:
        """Get text from UN element"""
        child = elem.find(path)
        if child is not None and child.text:
            return child.text.strip()
        return None
    
    def _index_documents(self, entity: Dict[str, Any]) -> None:
        """Index entity documents for fast lookup"""
        for doc in entity.get('identity_documents', []):
            doc_number = doc.get('number')
            if doc_number:
                normalized = self._normalize_document(doc_number)
                if normalized not in self._document_index:
                    self._document_index[normalized] = []
                self._document_index[normalized].append(entity)
        
        # Also index vessel IMO numbers
        vessel_imo = entity.get('vesselIMO')
        if vessel_imo:
            normalized = self._normalize_document(vessel_imo)
            if normalized not in self._document_index:
                self._document_index[normalized] = []
            self._document_index[normalized].append(entity)
    
    def _normalize_name(self, name: str) -> str:
        """Normalize name for matching"""
        if not name:
            return ""
        # Remove accents
        name = ''.join(c for c in unicodedata.normalize('NFD', name)
                      if unicodedata.category(c) != 'Mn')
        # Remove special characters
        name = re.sub(r'[^\w\s]', ' ', name)
        name = re.sub(r'\s+', ' ', name)
        return name.upper().strip()
    
    def _normalize_document(self, doc_number: str) -> str:
        """Normalize document number for matching"""
        if not doc_number:
            return ""
        # Remove spaces, dashes, dots
        normalized = re.sub(r'[\s\-\.\,\/]', '', doc_number)
        return normalized.upper()
    
    def _detect_unicode_script(self, name: str) -> str:
        """Detect the primary Unicode script of a name
        
        Returns:
            Script category: 'chinese', 'arabic', 'cyrillic', 'latin', 'mixed'
        """
        chinese_count = 0
        arabic_count = 0
        cyrillic_count = 0
        latin_count = 0
        
        for char in name:
            if UNICODE_CJK_START <= char <= UNICODE_CJK_END:
                chinese_count += 1
            elif UNICODE_ARABIC_START <= char <= UNICODE_ARABIC_END:
                arabic_count += 1
            elif UNICODE_CYRILLIC_START <= char <= UNICODE_CYRILLIC_END:
                cyrillic_count += 1
            elif char.isalpha():  # Other letters (Latin, etc.)
                latin_count += 1
        
        total = chinese_count + arabic_count + cyrillic_count + latin_count
        if total == 0:
            return 'latin'  # Default
        
        # Determine dominant script (>50% of letters)
        if chinese_count / total > 0.5:
            return 'chinese'
        elif arabic_count / total > 0.5:
            return 'arabic'
        elif cyrillic_count / total > 0.5:
            return 'cyrillic'
        elif latin_count / total > 0.5:
            return 'latin'
        else:
            return 'mixed'
    
    def _is_latin_initials(self, name: str) -> bool:
        """Check if name appears to be Latin initials like 'J.D.' or 'A.B.C.'"""
        # Remove dots and spaces
        cleaned = name.replace('.', '').replace(' ', '')
        # Check if it's all uppercase and short
        return len(cleaned) <= 4 and cleaned.isupper() and cleaned.isalpha()
    
    def _get_adaptive_threshold(self, name: str) -> Tuple[int, str]:
        """Get adaptive threshold based on Unicode script detection
        
        Args:
            name: The name to check
            
        Returns:
            Tuple of (threshold, reason)
        """
        adaptive = self.config.matching.adaptive_thresholds
        
        if not adaptive.enabled:
            return self.config.matching.short_name_threshold, 'default'
        
        # First check for Latin initials (most suspicious)
        if self._is_latin_initials(name):
            return adaptive.latin_initials, 'latin_initials'
        
        # Detect primary script
        script = self._detect_unicode_script(name)
        
        if script == 'chinese':
            # Chinese 2-char names are valid and common
            return adaptive.chinese, 'chinese_name'
        elif script == 'arabic':
            # Arabic mononyms are valid
            return adaptive.arabic, 'arabic_name'
        elif script == 'cyrillic':
            return adaptive.cyrillic, 'cyrillic_name'
        else:
            # Default Latin behavior
            return self.config.matching.short_name_threshold, 'latin_default'
    
    def _is_short_name(self, name: str) -> bool:
        """Check if name is considered short (requires stricter matching)"""
        words = name.split()
        if len(words) <= 2 and len(name) < 10:
            return True
        if any(len(word) <= 2 for word in words):
            return True
        return False
    
    def _is_common_name(self, name: str) -> bool:
        """Check if name is in common names list"""
        normalized = self._normalize_name(name)
        return normalized in self._common_names
    
    def search_by_document(self, doc_number: str, doc_type: Optional[str] = None) -> List[MatchResult]:
        """Search for entity by document number (Layer 1: Exact Match)
        
        Args:
            doc_number: Document number to search
            doc_type: Optional document type filter
            
        Returns:
            List of matching results with 100% confidence
        """
        results = []
        normalized = self._normalize_document(doc_number)
        
        if normalized in self._document_index:
            for entity in self._document_index[normalized]:
                # Verify the match
                matched_doc = None
                for doc in entity.get('identity_documents', []):
                    if self._normalize_document(doc.get('number', '')) == normalized:
                        if doc_type is None or doc.get('type', '').upper() == doc_type.upper():
                            matched_doc = doc.get('number')
                            break
                
                # Also check vessel IMO
                if not matched_doc and entity.get('vesselIMO'):
                    if self._normalize_document(entity['vesselIMO']) == normalized:
                        matched_doc = entity['vesselIMO']
                
                if matched_doc:
                    confidence = ConfidenceBreakdown(
                        overall=100.0,
                        document_score=100.0,
                        name_score=100.0  # Implicit name match via document
                    )
                    
                    result = MatchResult(
                        entity=entity,
                        confidence=confidence,
                        flags=['DOCUMENT_EXACT_MATCH'],
                        recommendation='AUTO_ESCALATE',
                        match_layer=1,
                        matched_name=entity.get('name', ''),
                        matched_document=matched_doc
                    )
                    results.append(result)
        
        return results
    
    def search(self, input_data: ScreeningInput, limit: int = 10) -> List[MatchResult]:
        """Multi-layer search with comprehensive scoring
        
        Args:
            input_data: Screening input containing name and optional fields
            limit: Maximum results to return
            
        Returns:
            List of MatchResult objects sorted by confidence
            
        Raises:
            InputValidationError: If input validation fails
        """
        # Validate input for security (pass config for settings)
        validate_screening_input(input_data, self.config)
        
        # Log search with sanitized input
        logger.info("Searching for: %s", sanitize_for_logging(input_data.name))
        
        results = []
        
        # Layer 1: Document exact match (if provided)
        if input_data.document_number:
            doc_matches = self.search_by_document(
                input_data.document_number, 
                input_data.document_type
            )
            results.extend(doc_matches)
        
        # Layer 2-4: Name-based matching
        query_norm = self._normalize_name(input_data.name)
        
        if not query_norm:
            return results
        
        # Determine threshold based on name characteristics
        is_short = self._is_short_name(input_data.name)
        is_common = self._is_common_name(input_data.name)
        
        base_threshold = self.config.matching.name_threshold
        threshold_reason = 'default'
        
        if is_short:
            # Use adaptive threshold based on Unicode script
            base_threshold, threshold_reason = self._get_adaptive_threshold(input_data.name)
        
        weights = self.config.matching.weights
        layers = self.config.matching.layers
        
        seen_entity_ids = set(r.entity['id'] for r in results)
        
        for entity in self.entities:
            if entity['id'] in seen_entity_ids:
                continue
            
            # Calculate name score
            all_names = entity.get('all_names', [entity.get('name', '')])
            best_name_score = 0.0
            best_matched_name = ''
            
            for candidate_name in all_names:
                if not candidate_name:
                    continue
                candidate_norm = self._normalize_name(candidate_name)
                score = fuzz.token_sort_ratio(query_norm, candidate_norm)
                if score > best_name_score:
                    best_name_score = score
                    best_matched_name = candidate_name
            
            if best_name_score < layers['low_match']:
                continue
            
            # Calculate document score
            doc_score = 0.0
            matched_doc = None
            if input_data.document_number:
                input_doc_norm = self._normalize_document(input_data.document_number)
                for doc in entity.get('identity_documents', []):
                    if self._normalize_document(doc.get('number', '')) == input_doc_norm:
                        doc_score = 100.0
                        matched_doc = doc.get('number')
                        break
            
            # Calculate DOB score
            dob_score = 0.0
            if input_data.date_of_birth and entity.get('dateOfBirth'):
                dob_score = self._calculate_dob_score(
                    input_data.date_of_birth, 
                    entity['dateOfBirth']
                )
            
            # Nationality check - INFORMATIONAL FLAG ONLY (non-scoring)
            # This data point is solely for human review/analysis; it does NOT affect the score
            nat_flag = None  # Will be set to appropriate flag if match found
            if input_data.nationality or input_data.country:
                input_countries = []
                if input_data.nationality:
                    input_countries.append(input_data.nationality.upper())
                if input_data.country:
                    input_countries.append(input_data.country.upper())
                
                entity_countries = set(c.upper() for c in entity.get('countries', []))
                entity_nat = entity.get('nationality', '')
                entity_cit = entity.get('citizenship', '')
                
                if entity_nat:
                    entity_countries.add(entity_nat.upper())
                if entity_cit:
                    entity_countries.add(entity_cit.upper())
                
                # Check for any match - optimized using set intersection first
                input_countries_set = set(input_countries)
                if input_countries_set & entity_countries:
                    # Exact match found via set intersection
                    nat_flag = 'NATIONALITY_EXACT_MATCH_INFO'
                elif entity_countries:
                    # Check for meaningful substring matches only if no exact match
                    # Avoid false positives like USA matching JERUSALEM
                    # A substring match is only valid if:
                    # 1. The shorter string is at least 4 chars (to avoid false positives)
                    # 2. One is a prefix or suffix of the other (not just contained)
                    found_substring = False
                    for ic in input_countries:
                        for ec in entity_countries:
                            # Only consider substring matches for longer country names
                            # This avoids "USA" matching "JERUSALEM" (false positive)
                            min_len = min(len(ic), len(ec))
                            if min_len >= 4:  # Minimum length for substring match
                                # Check if one starts with or ends with the other
                                if ec.startswith(ic) or ec.endswith(ic):
                                    found_substring = True
                                    break
                                if ic.startswith(ec) or ic.endswith(ec):
                                    found_substring = True
                                    break
                        if found_substring:
                            break
                    if found_substring:
                        nat_flag = 'NATIONALITY_SUBSTRING_MATCH_INFO'
                    # NOTE: No penalty for nationality mismatch - this is informational only
            
            # Calculate overall score using weights
            # NOTE: nationality is now INFORMATIONAL ONLY and excluded from scoring
            # The weighted sum maintains consistency with original formula (without nat_score component)
            overall = (
                best_name_score * weights['name'] +
                doc_score * weights['document'] +
                dob_score * weights['dob']
                # nationality weight removed - it's informational only
            )
            # Note: With current weights (0.40 + 0.30 + 0.15 = 0.85), 
            # max possible score is 85. This is intentional - the remaining
            # 0.15 weight (0.10 nationality + 0.05 address) represents fields
            # that are informational-only or not used in scoring.
            
            confidence = ConfidenceBreakdown(
                overall=max(0, min(100, overall)),
                name_score=best_name_score,
                document_score=doc_score,
                dob_score=dob_score,
                nationality_score=0.0  # Not used for scoring anymore
            )
            
            # Determine layer and flags
            flags = []
            layer = 4
            
            if doc_score == 100:
                layer = 1
                flags.append('DOCUMENT_MATCH')
            elif best_name_score >= layers['high_confidence']:
                if nat_flag or dob_score >= 60:
                    layer = 2
                else:
                    layer = 3
            elif best_name_score >= layers['moderate_match']:
                layer = 3
            else:
                layer = 4
            
            # Add flags
            if is_short:
                flags.append('SHORT_NAME_QUERY')
                # Add adaptive threshold info flag
                if threshold_reason != 'default' and threshold_reason != 'latin_default':
                    flags.append(f'ADAPTIVE_THRESHOLD_{threshold_reason.upper()}')
            if is_common:
                flags.append('COMMON_NAME')
            # Add nationality info flag if match found (informational only)
            if nat_flag:
                flags.append(nat_flag)
            if doc_score == 0 and input_data.document_number:
                flags.append('NO_DOCUMENT_MATCH')
            if entity.get('type') == 'entity':
                flags.append('ENTITY_MATCH')
            
            # Determine recommendation
            thresholds = self.config.reporting.recommendation_thresholds
            if confidence.overall >= thresholds['auto_escalate']:
                recommendation = 'AUTO_ESCALATE'
            elif confidence.overall >= thresholds['manual_review']:
                recommendation = 'MANUAL_REVIEW'
            elif confidence.overall >= thresholds['auto_clear']:
                recommendation = 'LOW_CONFIDENCE_REVIEW'
            else:
                recommendation = 'AUTO_CLEAR'
            
            # For common names, always require review unless document matches
            if is_common and doc_score == 0:
                if recommendation == 'AUTO_ESCALATE':
                    recommendation = 'MANUAL_REVIEW'
                flags.append('COMMON_NAME_REQUIRES_SECONDARY_VALIDATION')
            
            # Check if meets threshold
            if confidence.overall >= base_threshold or doc_score == 100:
                result = MatchResult(
                    entity=entity,
                    confidence=confidence,
                    flags=flags,
                    recommendation=recommendation,
                    match_layer=layer,
                    matched_name=best_matched_name,
                    matched_document=matched_doc
                )
                results.append(result)
        
        # Sort by confidence
        results.sort(key=lambda x: x.confidence.overall, reverse=True)
        
        return results[:limit]
    
    def _calculate_dob_score(self, input_dob: str, entity_dob: str) -> float:
        """Calculate DOB similarity score
        
        Score = 100 - (years_difference * 20), capped at 0
        """
        try:
            # Try to parse years
            input_year = self._extract_year(input_dob)
            entity_year = self._extract_year(entity_dob)
            
            if input_year and entity_year:
                diff = abs(input_year - entity_year)
                return max(0, 100 - (diff * 20))
        except Exception:
            pass
        
        return 0.0
    
    def _extract_year(self, date_str: str) -> Optional[int]:
        """Extract year from date string"""
        if not date_str:
            return None
        
        # Try common formats
        patterns = [
            r'(\d{4})',  # Just year
            r'(\d{4})-\d{2}-\d{2}',  # ISO format
            r'\d{2}/\d{2}/(\d{4})',  # MM/DD/YYYY
            r'\d{2}-\d{2}-(\d{4})',  # DD-MM-YYYY
        ]
        
        for pattern in patterns:
            match = re.search(pattern, date_str)
            if match:
                return int(match.group(1))
        
        return None
    
    def screen_individual(self, 
                         name: str,
                         document: Optional[str] = None,
                         document_type: Optional[str] = None,
                         date_of_birth: Optional[str] = None,
                         nationality: Optional[str] = None,
                         country: Optional[str] = None,
                         analyst: Optional[str] = None,
                         generate_report: bool = True) -> Dict[str, Any]:
        """Screen an individual with comprehensive result
        
        Args:
            name: Name to screen
            document: Optional document number
            document_type: Optional document type
            date_of_birth: Optional DOB
            nationality: Optional nationality
            country: Optional country
            analyst: Optional analyst name
            generate_report: Whether to generate report files
            
        Returns:
            Complete screening result dictionary
        """
        screening_id = str(uuid.uuid4())
        screening_date = datetime.now()
        
        input_data = ScreeningInput(
            name=name,
            document_number=document,
            document_type=document_type,
            date_of_birth=date_of_birth,
            nationality=nationality,
            country=country
        )
        
        matches = self.search(input_data, limit=10)
        is_hit = len(matches) > 0
        
        result = {
            'screening_id': screening_id,
            'input': {
                'name': name,
                'document': document,
                'document_type': document_type,
                'date_of_birth': date_of_birth,
                'nationality': nationality,
                'country': country
            },
            'screening_date': screening_date.isoformat(),
            'is_hit': is_hit,
            'hit_count': len(matches),
            'matches': [m.to_dict() for m in matches],
            'analyst': analyst,
            'algorithm_version': self.config.algorithm.version,
            'thresholds_used': {
                'name': self.config.matching.name_threshold,
                'short_name': self.config.matching.short_name_threshold
            }
        }
        
        # Add to history with size limit to prevent memory issues
        self.screening_history.append(result)
        if len(self.screening_history) > self._max_history_size:
            # Remove oldest entries when limit exceeded
            self.screening_history = self.screening_history[-self._max_history_size:]
        
        # Generate reports if requested
        if generate_report:
            result['report_files'] = self._generate_reports(result, matches)
        
        return result
    
    def _generate_reports(self, result: Dict[str, Any], matches: List[MatchResult]) -> Dict[str, str]:
        """Generate report files"""
        report_files = {}
        
        try:
            from report_generator import (
                ConstanciaReportGenerator, ScreeningResult,
                ScreeningMatch, ReportMetadataCollector
            )
            
            # Convert matches
            screening_matches = []
            for m in matches:
                entity = m.entity
                screening_matches.append(ScreeningMatch(
                    matched_name=m.matched_name,
                    match_score=m.confidence.overall,
                    entity_id=entity.get('id', ''),
                    source=entity.get('source', ''),
                    entity_type=entity.get('type', ''),
                    program=entity.get('program', ''),
                    countries=entity.get('countries', []),
                    all_names=entity.get('all_names', []),
                    last_name=entity.get('lastName'),
                    first_name=entity.get('firstName'),
                    nationality=entity.get('nationality'),
                    title=entity.get('title'),
                    citizenship=entity.get('citizenship'),
                    date_of_birth=entity.get('dateOfBirth'),
                    place_of_birth=entity.get('placeOfBirth'),
                    gender=entity.get('gender'),
                    identifications=entity.get('identity_documents', []),
                    addresses=entity.get('addresses', [])
                ))
            
            screening_result = ScreeningResult(
                input_name=result['input']['name'],
                input_document=result['input'].get('document', ''),
                input_country=result['input'].get('country', ''),
                screening_date=datetime.fromisoformat(result['screening_date']),
                matches=screening_matches,
                is_hit=result['is_hit'],
                analyst_name=result.get('analyst')
            )
            
            generator = ConstanciaReportGenerator(self.reports_dir)
            metadata = ReportMetadataCollector(self.data_dir).collect_all_metadata()
            
            report_files['html'] = generator.generate_html_report(screening_result, metadata)
            report_files['json'] = generator.generate_json_report(screening_result, metadata)
            
        except ImportError as e:
            logger.warning(f"Report generation skipped: {e}")
        except Exception as e:
            logger.error(f"Error generating reports: {e}")
        
        return report_files
    
    def bulk_screen(self, csv_file: str,
                   analyst: Optional[str] = None,
                   generate_individual_reports: bool = False) -> Dict[str, Any]:
        """Bulk screening from CSV file
        
        Args:
            csv_file: Path to CSV file with columns: nombre,cedula,pais
            analyst: Analyst name
            generate_individual_reports: Generate individual reports
            
        Returns:
            Summary of bulk screening
        """
        results = []
        hits = []
        
        logger.info(f"\n{'='*60}")
        logger.info(f"BULK SCREENING - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        logger.info(f"{'='*60}\n")
        
        with open(csv_file, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            rows = list(reader)
            total = len(rows)
            
            for idx, row in enumerate(rows, 1):
                nombre = row.get('nombre', '').strip()
                cedula = row.get('cedula', '').strip()
                pais = row.get('pais', '').strip()
                
                if not nombre:
                    continue
                
                logger.info(f"[{idx}/{total}] Screening: {nombre}...")
                
                result = self.screen_individual(
                    name=nombre,
                    document=cedula if cedula else None,
                    country=pais if pais else None,
                    analyst=analyst,
                    generate_report=generate_individual_reports
                )
                
                results.append(result)
                
                if result['is_hit']:
                    hits.append(result)
                    logger.info(f"  ⚠️  HIT - {result['hit_count']} matches")
                else:
                    logger.info(f"  ✓ Clear")
        
        # Save summary
        summary = {
            'screening_info': {
                'date': datetime.now().isoformat(),
                'analyst': analyst,
                'total_screened': len(results),
                'total_hits': len(hits),
                'hit_rate': f"{len(hits)/len(results)*100:.2f}%" if results else "0%",
                'algorithm_version': self.config.algorithm.version
            },
            'results': results,
            'hits_only': hits
        }
        
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        summary_file = self.reports_dir / f"bulk_screening_{timestamp}.json"
        
        with open(summary_file, 'w', encoding='utf-8') as f:
            json.dump(summary, f, indent=2, ensure_ascii=False)
        
        logger.info(f"\n{'='*60}")
        logger.info(f"SCREENING SUMMARY")
        logger.info(f"{'='*60}")
        logger.info(f"Total screened: {len(results)}")
        logger.info(f"Hits: {len(hits)}")
        logger.info(f"Hit rate: {len(hits)/len(results)*100:.2f}%" if results else "0%")
        logger.info(f"\n✓ Summary saved: {summary_file}")
        
        return summary


def main():
    """Main entry point"""
    print("=== Enhanced Sanctions Screener v2.0 ===\n")
    
    screener = EnhancedSanctionsScreener()
    screener.load_ofac()
    screener.load_un()
    
    print(f"\nTotal entities loaded: {len(screener.entities)}")
    print(f"Documents indexed: {len(screener._document_index)}")
    
    # Example: Bulk screening
    csv_path = Path("input.csv")
    if csv_path.exists():
        print(f"\nStarting bulk screening from {csv_path}...")
        summary = screener.bulk_screen(
            csv_file=str(csv_path),
            analyst=None,
            generate_individual_reports=True
        )


if __name__ == "__main__":
    main()
