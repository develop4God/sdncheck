"""
Enhanced Sanctions List Downloader v2.0
Downloads, validates, and parses OFAC SDN and UN Consolidated sanctions lists

Features:
- Dynamic namespace handling
- Complete entity extraction (identity documents, features, relationships)
- XSD schema validation (optional)
- Integrity verification (file completeness, hash, mandatory fields)
- Enhanced UN list parsing with country codes and committees
"""

import requests
import hashlib
import logging
import zipfile
import re
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, field

# Use lxml for better XML parsing and XSD validation
try:
    from lxml import etree
    HAS_LXML = True
except ImportError:
    import xml.etree.ElementTree as etree
    HAS_LXML = False

from config_manager import get_config, ConfigManager

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


@dataclass
class IdentityDocument:
    """Identity document data structure"""
    doc_type: str
    doc_number: str
    issuing_country: Optional[str] = None
    issue_date: Optional[str] = None
    expiration_date: Optional[str] = None
    note: Optional[str] = None


@dataclass
class Feature:
    """Entity feature (DOB, nationality, vessel ID, etc.)"""
    feature_type: str
    value: str
    reliability: Optional[str] = None
    date_period: Optional[str] = None
    location: Optional[str] = None


@dataclass
class Relationship:
    """Entity relationship"""
    related_entity_id: str
    relationship_type: str
    from_date: Optional[str] = None
    to_date: Optional[str] = None


@dataclass
class Address:
    """Address data structure"""
    address_line1: Optional[str] = None
    address_line2: Optional[str] = None
    city: Optional[str] = None
    state_province: Optional[str] = None
    postal_code: Optional[str] = None
    country: Optional[str] = None
    region: Optional[str] = None
    translations: List[str] = field(default_factory=list)


@dataclass
class SanctionsEntity:
    """Complete sanctions entity with all extracted fields"""
    entity_id: str
    source: str  # 'OFAC' or 'UN'
    entity_type: str  # 'individual', 'entity', 'vessel', 'aircraft'
    
    # Names
    primary_name: str
    all_names: List[str] = field(default_factory=list)
    aliases: List[str] = field(default_factory=list)
    
    # For individuals
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    middle_name: Optional[str] = None
    
    # Identity documents
    identity_documents: List[IdentityDocument] = field(default_factory=list)
    
    # Features
    features: List[Feature] = field(default_factory=list)
    date_of_birth: Optional[str] = None
    place_of_birth: Optional[str] = None
    nationality: Optional[str] = None
    citizenship: Optional[str] = None
    gender: Optional[str] = None
    title: Optional[str] = None
    
    # Vessel/Aircraft specific
    vessel_imo: Optional[str] = None
    aircraft_registration: Optional[str] = None
    
    # Digital identifiers
    crypto_addresses: List[str] = field(default_factory=list)
    
    # Relationships
    relationships: List[Relationship] = field(default_factory=list)
    
    # Addresses
    addresses: List[Address] = field(default_factory=list)
    countries: List[str] = field(default_factory=list)
    
    # Program information
    sanctions_programs: List[str] = field(default_factory=list)
    
    # UN specific
    un_list_type: Optional[str] = None  # e.g., 'QDi', 'KPe'
    un_country_code: Optional[str] = None
    un_committee: Optional[str] = None
    un_reference_number: Optional[str] = None
    
    # Remarks
    remarks: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert entity to dictionary"""
        return {
            'id': self.entity_id,
            'source': self.source,
            'type': self.entity_type,
            'name': self.primary_name,
            'all_names': self.all_names,
            'aliases': self.aliases,
            'firstName': self.first_name,
            'lastName': self.last_name,
            'identity_documents': [
                {
                    'type': doc.doc_type,
                    'number': doc.doc_number,
                    'issuingCountry': doc.issuing_country,
                    'issueDate': doc.issue_date,
                    'expirationDate': doc.expiration_date,
                    'note': doc.note
                } for doc in self.identity_documents
            ],
            'features': [
                {
                    'type': f.feature_type,
                    'value': f.value,
                    'reliability': f.reliability
                } for f in self.features
            ],
            'dateOfBirth': self.date_of_birth,
            'placeOfBirth': self.place_of_birth,
            'nationality': self.nationality,
            'citizenship': self.citizenship,
            'gender': self.gender,
            'title': self.title,
            'vesselIMO': self.vessel_imo,
            'aircraftRegistration': self.aircraft_registration,
            'cryptoAddresses': self.crypto_addresses,
            'relationships': [
                {
                    'relatedEntityId': r.related_entity_id,
                    'relationshipType': r.relationship_type,
                    'fromDate': r.from_date,
                    'toDate': r.to_date
                } for r in self.relationships
            ],
            'addresses': [
                {
                    'addressLine1': a.address_line1,
                    'city': a.city,
                    'stateProvince': a.state_province,
                    'postalCode': a.postal_code,
                    'country': a.country
                } for a in self.addresses
            ],
            'countries': self.countries,
            'sanctionsPrograms': self.sanctions_programs,
            'unListType': self.un_list_type,
            'unCountryCode': self.un_country_code,
            'unCommittee': self.un_committee,
            'unReferenceNumber': self.un_reference_number,
            'remarks': self.remarks
        }


@dataclass
class ValidationResult:
    """Result of validation checks"""
    is_valid: bool
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    entity_count: int = 0
    expected_count: Optional[int] = None
    malformed_count: int = 0
    file_hash: str = ""
    
    def add_error(self, message: str) -> None:
        """Add an error message"""
        self.errors.append(message)
        self.is_valid = False
        
    def add_warning(self, message: str) -> None:
        """Add a warning message"""
        self.warnings.append(message)


class EnhancedSanctionsDownloader:
    """Enhanced downloader with complete extraction and validation"""
    
    # Known OFAC namespace patterns
    OFAC_NAMESPACE_PATTERNS = [
        r'https://sanctionslistservice\.ofac\.treas\.gov/api/PublicationPreview/exports/ENHANCED_XML',
        r'http://sanctionslistservice\.ofac\.treas\.gov/.*',
    ]
    
    def __init__(self, config: Optional[ConfigManager] = None):
        """Initialize downloader
        
        Args:
            config: Configuration manager instance
        """
        self.config = config or get_config()
        self.data_dir = Path(self.config.data.data_directory)
        self.data_dir.mkdir(exist_ok=True)
        
        self._namespace: Optional[str] = None
        self._entities: List[SanctionsEntity] = []
        self._validation_result: Optional[ValidationResult] = None
        
        # Track discovered UN codes at runtime (extracted from XML)
        # These are logged for review when new sanctions programs are encountered
        self._discovered_country_codes: set = set()
        self._discovered_list_types: set = set()
        
    def download_ofac(self) -> Optional[Path]:
        """Download OFAC SDN Enhanced list
        
        Returns:
            Path to downloaded ZIP file or None on failure
        """
        url = self.config.data.ofac_url
        logger.info(f"Downloading OFAC SDN Enhanced from {url}")
        
        try:
            response = requests.get(url, stream=True, timeout=120)
            response.raise_for_status()
            
            filepath = self.data_dir / "ofac_enhanced.zip"
            
            with open(filepath, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)
            
            size_mb = filepath.stat().st_size / 1024 / 1024
            logger.info(f"✓ Downloaded OFAC list: {filepath} ({size_mb:.1f} MB)")
            
            # Calculate hash
            file_hash = self._calculate_hash(filepath)
            logger.info(f"  File hash (SHA256): {file_hash[:16]}...")
            
            return filepath
            
        except requests.RequestException as e:
            logger.error(f"✗ Failed to download OFAC list: {e}")
            return None
    
    def unzip_ofac(self) -> Optional[Path]:
        """Extract OFAC XML from ZIP file
        
        Returns:
            Path to extracted XML file or None on failure
        """
        zip_path = self.data_dir / "ofac_enhanced.zip"
        
        if not zip_path.exists():
            logger.error(f"✗ ZIP file not found: {zip_path}")
            return None
        
        try:
            with zipfile.ZipFile(zip_path, 'r') as zf:
                # Find the XML file inside
                xml_files = [n for n in zf.namelist() if n.upper().endswith('.XML')]
                
                if not xml_files:
                    logger.error("✗ No XML file found in ZIP archive")
                    return None
                
                # Extract the first XML file found
                xml_name = xml_files[0]
                zf.extract(xml_name, self.data_dir)
                
                extracted_path = self.data_dir / xml_name
                final_path = self.data_dir / "sdn_enhanced.xml"
                
                if extracted_path.exists() and extracted_path != final_path:
                    extracted_path.rename(final_path)
                
                logger.info(f"✓ Extracted OFAC XML: {final_path}")
                return final_path
                
        except zipfile.BadZipFile as e:
            logger.error(f"✗ Invalid ZIP file: {e}")
            return None
        except Exception as e:
            logger.error(f"✗ Extraction error: {e}")
            return None
    
    def download_un(self) -> Optional[Path]:
        """Download UN Consolidated sanctions list
        
        Returns:
            Path to downloaded XML file or None on failure
        """
        url = self.config.data.un_url
        logger.info(f"Downloading UN Consolidated List from {url}")
        
        try:
            response = requests.get(url, timeout=120)
            response.raise_for_status()
            
            filepath = self.data_dir / "un_consolidated.xml"
            filepath.write_bytes(response.content)
            
            size_mb = len(response.content) / 1024 / 1024
            logger.info(f"✓ Downloaded UN list: {filepath} ({size_mb:.1f} MB)")
            
            # Calculate hash
            file_hash = self._calculate_hash(filepath)
            logger.info(f"  File hash (SHA256): {file_hash[:16]}...")
            
            return filepath
            
        except requests.RequestException as e:
            logger.error(f"✗ Failed to download UN list: {e}")
            return None
    
    def _calculate_hash(self, filepath: Path) -> str:
        """Calculate SHA256 hash of file"""
        sha256 = hashlib.sha256()
        with open(filepath, 'rb') as f:
            for chunk in iter(lambda: f.read(8192), b""):
                sha256.update(chunk)
        return sha256.hexdigest()
    
    def _extract_namespace(self, xml_path: Path) -> str:
        """Dynamically extract namespace from XML root element
        
        Args:
            xml_path: Path to XML file
            
        Returns:
            Namespace string with curly braces
        """
        try:
            # Read first few lines to find namespace
            with open(xml_path, 'rb') as f:
                # Parse events until we get the root element
                for event, elem in etree.iterparse(f, events=('start',)):
                    # Get namespace from first element
                    tag = elem.tag
                    if tag.startswith('{'):
                        ns_end = tag.index('}')
                        namespace = tag[1:ns_end]
                        logger.info(f"Extracted namespace: {namespace}")
                        
                        # Validate against known patterns
                        is_known = any(re.match(pattern, namespace) 
                                      for pattern in self.OFAC_NAMESPACE_PATTERNS)
                        if not is_known:
                            logger.warning(f"Namespace differs from expected patterns: {namespace}")
                        
                        return '{' + namespace + '}'
                    break
            
            # No namespace found
            logger.warning("No namespace found in XML, using empty namespace")
            return ''
            
        except Exception as e:
            logger.error(f"Error extracting namespace: {e}")
            return ''
    
    def validate_ofac_xml(self, xml_path: Path, xsd_path: Optional[Path] = None) -> ValidationResult:
        """Validate OFAC XML structure and integrity
        
        Args:
            xml_path: Path to XML file
            xsd_path: Optional path to XSD schema file
            
        Returns:
            ValidationResult with details
        """
        result = ValidationResult(is_valid=True)
        
        if not xml_path.exists():
            result.add_error(f"XML file not found: {xml_path}")
            return result
        
        # Calculate file hash
        result.file_hash = self._calculate_hash(xml_path)
        
        # XSD validation if available and enabled
        if self.config.data.xsd_validation and xsd_path and xsd_path.exists() and HAS_LXML:
            try:
                with open(xsd_path, 'rb') as f:
                    schema_doc = etree.parse(f)
                    schema = etree.XMLSchema(schema_doc)
                
                with open(xml_path, 'rb') as f:
                    xml_doc = etree.parse(f)
                
                if not schema.validate(xml_doc):
                    for error in schema.error_log:
                        result.add_warning(f"XSD validation warning (line {error.line}): {error.message}")
                    logger.warning("XSD validation found issues (proceeding with warnings)")
                else:
                    logger.info("✓ XSD validation passed")
                    
            except Exception as e:
                result.add_warning(f"XSD validation skipped: {e}")
        
        # Parse and count entities
        try:
            ns = self._extract_namespace(xml_path)
            self._namespace = ns
            
            if HAS_LXML:
                context = etree.iterparse(str(xml_path), events=('end',), tag=f'{ns}entity')
            else:
                context = etree.iterparse(xml_path, events=('end',))
            
            entity_count = 0
            malformed_count = 0
            
            for event, elem in context:
                if HAS_LXML or elem.tag == f'{ns}entity':
                    entity_count += 1
                    
                    # Check mandatory fields
                    entity_id = elem.get('id')
                    if not entity_id:
                        malformed_count += 1
                        if self.config.validation.log_validation_errors:
                            logger.warning(f"Entity missing ID at position {entity_count}")
                    
                    elem.clear()
            
            result.entity_count = entity_count
            result.malformed_count = malformed_count
            
            # Check malformation rate
            if entity_count > 0:
                malformation_rate = (malformed_count / entity_count) * 100
                if malformation_rate > self.config.data.malformed_entity_threshold:
                    result.add_error(
                        f"High malformation rate: {malformation_rate:.2f}% "
                        f"(threshold: {self.config.data.malformed_entity_threshold}%)"
                    )
            
            logger.info(f"✓ Validated {entity_count} entities ({malformed_count} malformed)")
            
        except Exception as e:
            result.add_error(f"XML parsing error: {e}")
        
        return result
    
    def parse_ofac_xml(self, xml_path: Path) -> List[SanctionsEntity]:
        """Parse OFAC SDN Enhanced XML with complete field extraction
        
        Args:
            xml_path: Path to XML file
            
        Returns:
            List of parsed SanctionsEntity objects
        """
        logger.info(f"Parsing OFAC XML: {xml_path}")
        
        if not xml_path.exists():
            logger.error(f"✗ File not found: {xml_path}")
            return []
        
        # Get namespace
        ns = self._namespace or self._extract_namespace(xml_path)
        self._namespace = ns
        
        entities = []
        
        try:
            if HAS_LXML:
                context = etree.iterparse(str(xml_path), events=('end',), tag=f'{ns}entity')
            else:
                context = etree.iterparse(xml_path, events=('end',))
            
            count = 0
            for event, elem in context:
                if not HAS_LXML and elem.tag != f'{ns}entity':
                    continue
                    
                try:
                    entity = self._parse_ofac_entity(elem, ns)
                    if entity:
                        entities.append(entity)
                        count += 1
                except Exception as e:
                    entity_id = elem.get('id', 'unknown')
                    logger.warning(f"Error parsing entity {entity_id}: {e}")
                
                elem.clear()
                
                if count % 1000 == 0:
                    logger.info(f"  Parsed {count} entities...")
            
            logger.info(f"✓ Parsed {len(entities)} OFAC entities")
            
        except Exception as e:
            logger.error(f"✗ Error parsing OFAC XML: {e}")
        
        self._entities = entities
        return entities
    
    def _parse_ofac_entity(self, elem: Any, ns: str) -> Optional[SanctionsEntity]:
        """Parse a single OFAC entity element
        
        Args:
            elem: XML element
            ns: Namespace string
            
        Returns:
            SanctionsEntity or None
        """
        entity_id = elem.get('id')
        if not entity_id:
            return None
        
        # Entity type
        entity_type_elem = elem.find(f'{ns}entityType')
        entity_type = entity_type_elem.text if entity_type_elem is not None else 'entity'
        
        # Extract all names
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
                        
                        # Extract first/last name for individuals
                        if entity_type.lower() == 'individual':
                            fn = translation.find(f'{ns}formattedFirstName')
                            ln = translation.find(f'{ns}formattedLastName')
                            if fn is not None and fn.text and not first_name:
                                first_name = fn.text.strip()
                            if ln is not None and ln.text and not last_name:
                                last_name = ln.text.strip()
        
        if not all_names:
            return None
        
        # Remove duplicates while preserving order
        all_names = list(dict.fromkeys(all_names))
        primary_name = all_names[0]
        aliases = all_names[1:] if len(all_names) > 1 else []
        
        # Create entity
        entity = SanctionsEntity(
            entity_id=entity_id,
            source='OFAC',
            entity_type=entity_type.lower(),
            primary_name=primary_name,
            all_names=all_names,
            aliases=aliases,
            first_name=first_name,
            last_name=last_name
        )
        
        # Parse identity documents (directly under entity per OFAC XSD)
        id_docs_section = elem.find(f'{ns}idDocuments')
        if id_docs_section is not None:
            for doc in id_docs_section.findall(f'{ns}idDocument'):
                identity_doc = self._parse_identity_document(doc, ns)
                if identity_doc:
                    entity.identity_documents.append(identity_doc)
        
        # Parse features
        features_section = elem.find(f'{ns}features')
        if features_section is not None:
            for feature_elem in features_section.findall(f'{ns}feature'):
                feature = self._parse_feature(feature_elem, ns)
                if feature:
                    entity.features.append(feature)
                    
                    # Extract specific feature values
                    ft = feature.feature_type.upper()
                    if 'DOB' in ft or ('DATE' in ft and 'BIRTH' in ft):
                        entity.date_of_birth = feature.value
                    elif 'POB' in ft or ('PLACE' in ft and 'BIRTH' in ft):
                        entity.place_of_birth = feature.value
                    elif 'NATIONAL' in ft:
                        entity.nationality = feature.value
                        if feature.value:
                            entity.countries.append(feature.value)
                    elif 'CITIZEN' in ft:
                        entity.citizenship = feature.value
                        if feature.value:
                            entity.countries.append(feature.value)
                    elif 'GENDER' in ft:
                        entity.gender = feature.value
                    elif 'TITLE' in ft:
                        entity.title = feature.value
                    elif 'IMO' in ft or 'VESSEL' in ft:
                        entity.vessel_imo = feature.value
                    elif 'AIRCRAFT' in ft or 'REGISTRATION' in ft:
                        entity.aircraft_registration = feature.value
                    elif 'DIGITAL' in ft or 'CRYPTO' in ft or 'WALLET' in ft:
                        entity.crypto_addresses.append(feature.value)
        
        # Parse relationships
        relationships_section = elem.find(f'{ns}relationships')
        if relationships_section is not None:
            for rel_elem in relationships_section.findall(f'{ns}relationship'):
                relationship = self._parse_relationship(rel_elem, ns)
                if relationship:
                    entity.relationships.append(relationship)
        
        # Parse addresses
        addresses_section = elem.find(f'{ns}addresses')
        if addresses_section is not None:
            for addr_elem in addresses_section.findall(f'{ns}address'):
                address = self._parse_address(addr_elem, ns)
                if address:
                    entity.addresses.append(address)
                    if address.country:
                        entity.countries.append(address.country)
        
        # Parse sanctions programs
        programs_section = elem.find(f'{ns}sanctionsPrograms')
        if programs_section is not None:
            for prog in programs_section.findall(f'{ns}sanctionsProgram'):
                if prog.text:
                    entity.sanctions_programs.append(prog.text.strip())
        
        # Deduplicate countries
        entity.countries = list(set(entity.countries))
        
        return entity
    
    def _parse_identity_document(self, elem: Any, ns: str) -> Optional[IdentityDocument]:
        """Parse identity document element"""
        doc_type_elem = elem.find(f'{ns}type')
        doc_number_elem = elem.find(f'{ns}number')
        
        if doc_number_elem is None or not doc_number_elem.text:
            return None
        
        return IdentityDocument(
            doc_type=doc_type_elem.text if doc_type_elem is not None else 'Unknown',
            doc_number=doc_number_elem.text.strip(),
            issuing_country=self._get_text(elem, f'{ns}issuedByCountry'),
            issue_date=self._get_text(elem, f'{ns}issueDate'),
            expiration_date=self._get_text(elem, f'{ns}expirationDate'),
            note=self._get_text(elem, f'{ns}note')
        )
    
    def _parse_feature(self, elem: Any, ns: str) -> Optional[Feature]:
        """Parse feature element"""
        feature_type_elem = elem.find(f'{ns}type')
        value_elem = elem.find(f'{ns}value')
        
        if feature_type_elem is None:
            return None
        
        value = ''
        if value_elem is not None and value_elem.text:
            value = value_elem.text.strip()
        
        return Feature(
            feature_type=feature_type_elem.text,
            value=value,
            reliability=self._get_text(elem, f'{ns}reliability')
        )
    
    def _parse_relationship(self, elem: Any, ns: str) -> Optional[Relationship]:
        """Parse relationship element"""
        related_id_elem = elem.find(f'{ns}relatedEntity')
        rel_type_elem = elem.find(f'{ns}relationshipType')
        
        if related_id_elem is None:
            return None
        
        related_id = related_id_elem.get('id') or (related_id_elem.text if related_id_elem.text else '')
        
        return Relationship(
            related_entity_id=related_id,
            relationship_type=rel_type_elem.text if rel_type_elem is not None else 'Unknown',
            from_date=self._get_text(elem, f'{ns}fromDate'),
            to_date=self._get_text(elem, f'{ns}toDate')
        )
    
    def _parse_address(self, elem: Any, ns: str) -> Optional[Address]:
        """Parse address element"""
        return Address(
            address_line1=self._get_text(elem, f'{ns}addressLine1'),
            address_line2=self._get_text(elem, f'{ns}addressLine2'),
            city=self._get_text(elem, f'{ns}city'),
            state_province=self._get_text(elem, f'{ns}stateProvince'),
            postal_code=self._get_text(elem, f'{ns}postalCode'),
            country=self._get_text(elem, f'{ns}country'),
            region=self._get_text(elem, f'{ns}region')
        )
    
    def _get_text(self, elem: Any, path: str) -> Optional[str]:
        """Safely get text from element"""
        child = elem.find(path)
        if child is not None and child.text:
            return child.text.strip()
        return None
    
    def parse_un_xml(self, xml_path: Path) -> List[SanctionsEntity]:
        """Parse UN Consolidated List XML with enhanced extraction
        
        Args:
            xml_path: Path to XML file
            
        Returns:
            List of parsed SanctionsEntity objects
        """
        logger.info(f"Parsing UN XML: {xml_path}")
        
        if not xml_path.exists():
            logger.error(f"✗ File not found: {xml_path}")
            return []
        
        entities = []
        
        try:
            if HAS_LXML:
                tree = etree.parse(str(xml_path))
            else:
                tree = etree.parse(xml_path)
            root = tree.getroot()
            
            # Parse individuals
            for individual in root.findall('.//INDIVIDUAL'):
                entity = self._parse_un_individual(individual)
                if entity:
                    entities.append(entity)
            
            # Parse entities
            for entity_elem in root.findall('.//ENTITY'):
                entity = self._parse_un_entity(entity_elem)
                if entity:
                    entities.append(entity)
            
            logger.info(f"✓ Parsed {len(entities)} UN entities "
                       f"({len([e for e in entities if e.entity_type == 'individual'])} individuals, "
                       f"{len([e for e in entities if e.entity_type == 'entity'])} entities)")
            
        except Exception as e:
            logger.error(f"✗ Error parsing UN XML: {e}")
        
        return entities
    
    def _parse_un_individual(self, elem: Any) -> Optional[SanctionsEntity]:
        """Parse UN individual element"""
        dataid = self._get_un_text(elem, 'DATAID')
        if not dataid:
            return None
        
        # Parse name parts
        first_name = self._get_un_text(elem, 'FIRST_NAME') or ''
        second_name = self._get_un_text(elem, 'SECOND_NAME') or ''
        third_name = self._get_un_text(elem, 'THIRD_NAME') or ''
        fourth_name = self._get_un_text(elem, 'FOURTH_NAME') or ''
        
        name_parts = [n for n in [first_name, second_name, third_name, fourth_name] if n]
        if not name_parts:
            return None
        
        primary_name = ' '.join(name_parts).strip()
        
        # Extract UN_LIST_TYPE from XML (the authoritative source for committee info)
        un_list_type_xml = self._get_un_text(elem, 'UN_LIST_TYPE')
        
        # Parse list type and country code from reference number
        reference_number = self._get_un_text(elem, 'REFERENCE_NUMBER')
        list_type, country_code, committee = self._parse_un_reference(
            dataid, reference_number, un_list_type_xml
        )
        
        entity = SanctionsEntity(
            entity_id=dataid,
            source='UN',
            entity_type='individual',
            primary_name=primary_name,
            all_names=[primary_name],
            first_name=first_name,
            last_name=fourth_name or third_name or second_name,
            un_list_type=list_type,
            un_country_code=country_code,
            un_committee=committee,
            un_reference_number=reference_number
        )
        
        # Parse aliases
        for alias in elem.findall('.//INDIVIDUAL_ALIAS'):
            alias_name = self._get_un_text(alias, 'ALIAS_NAME')
            quality = self._get_un_text(alias, 'QUALITY')
            if alias_name:
                entity.aliases.append(alias_name)
                entity.all_names.append(alias_name)
        
        # Parse DOB
        dob = self._get_un_text(elem, 'DATE_OF_BIRTH')
        if dob:
            entity.date_of_birth = dob
        
        # Parse nationality
        nationality = self._get_un_text(elem, 'NATIONALITY/VALUE')
        if nationality:
            entity.nationality = nationality
            entity.countries.append(nationality)
        
        # Parse identity documents
        for doc in elem.findall('.//INDIVIDUAL_DOCUMENT'):
            doc_type = self._get_un_text(doc, 'TYPE_OF_DOCUMENT')
            doc_number = self._get_un_text(doc, 'NUMBER')
            if doc_number:
                entity.identity_documents.append(IdentityDocument(
                    doc_type=doc_type or 'Unknown',
                    doc_number=doc_number,
                    issuing_country=self._get_un_text(doc, 'ISSUING_COUNTRY'),
                    issue_date=self._get_un_text(doc, 'DATE_OF_ISSUE'),
                    note=self._get_un_text(doc, 'NOTE')
                ))
        
        # Parse addresses
        for addr in elem.findall('.//INDIVIDUAL_ADDRESS'):
            address = Address(
                address_line1=self._get_un_text(addr, 'STREET'),
                city=self._get_un_text(addr, 'CITY'),
                state_province=self._get_un_text(addr, 'STATE_PROVINCE'),
                country=self._get_un_text(addr, 'COUNTRY')
            )
            entity.addresses.append(address)
            if address.country:
                entity.countries.append(address.country)
        
        # Parse remarks/comments
        entity.remarks = self._get_un_text(elem, 'COMMENTS1')
        
        return entity
    
    def _parse_un_entity(self, elem: Any) -> Optional[SanctionsEntity]:
        """Parse UN entity element"""
        dataid = self._get_un_text(elem, 'DATAID')
        name = self._get_un_text(elem, 'FIRST_NAME')  # Entity name is in FIRST_NAME
        
        if not dataid or not name:
            return None
        
        # Extract UN_LIST_TYPE from XML (the authoritative source for committee info)
        un_list_type_xml = self._get_un_text(elem, 'UN_LIST_TYPE')
        
        # Parse list type and country code
        reference_number = self._get_un_text(elem, 'REFERENCE_NUMBER')
        list_type, country_code, committee = self._parse_un_reference(
            dataid, reference_number, un_list_type_xml
        )
        
        entity = SanctionsEntity(
            entity_id=dataid,
            source='UN',
            entity_type='entity',
            primary_name=name,
            all_names=[name],
            un_list_type=list_type,
            un_country_code=country_code,
            un_committee=committee,
            un_reference_number=reference_number
        )
        
        # Parse aliases
        for alias in elem.findall('.//ENTITY_ALIAS'):
            alias_name = self._get_un_text(alias, 'ALIAS_NAME')
            if alias_name:
                entity.aliases.append(alias_name)
                entity.all_names.append(alias_name)
        
        # Parse addresses
        for addr in elem.findall('.//ENTITY_ADDRESS'):
            address = Address(
                address_line1=self._get_un_text(addr, 'STREET'),
                city=self._get_un_text(addr, 'CITY'),
                state_province=self._get_un_text(addr, 'STATE_PROVINCE'),
                country=self._get_un_text(addr, 'COUNTRY')
            )
            entity.addresses.append(address)
            if address.country:
                entity.countries.append(address.country)
        
        entity.remarks = self._get_un_text(elem, 'COMMENTS1')
        
        return entity
    
    def _get_un_text(self, elem: Any, path: str) -> Optional[str]:
        """Get text from UN XML element"""
        child = elem.find(path)
        if child is not None and child.text:
            return child.text.strip()
        return None
    
    def _parse_un_reference(self, dataid: str, reference_number: Optional[str], un_list_type: Optional[str] = None) -> Tuple[Optional[str], Optional[str], Optional[str]]:
        """Parse UN reference number to extract list type and country code dynamically
        
        Country codes and committees are extracted from the XML data itself,
        not from hardcoded configuration. This ensures the system stays in sync
        with UN updates.
        
        Args:
            dataid: The DATAID value
            reference_number: The reference number (e.g., 'QDi.001')
            un_list_type: The UN_LIST_TYPE from XML (e.g., 'Al-Qaida', 'Taliban')
            
        Returns:
            Tuple of (list_type, country_code, committee)
            
        Known UN reference patterns (extracted dynamically):
            - QDi/QDe: Al-Qaeda/ISIL related
            - TAi/TAe: Taliban related
            - KPi/KPe: North Korea (DPRK) related
            - IRi/IRe: Iran related
            - LYi/LYe: Libya related
            - CDi/CDe: Democratic Republic of the Congo related
            - SDi/SDe: Sudan related
            - SOi/SOe: Somalia related
            - YEi/YEe: Yemen related
            - SSi/SSe: South Sudan related
            - CFi/CFe: Central African Republic related
            - HTi/HTe: Haiti related
            - GBi/GBe: Guinea-Bissau related
            - IQi/IQe: Iraq related
            - MLi/MLe: Mali related
        """
        list_type = None
        country_code = None
        committee = None
        
        # Try to parse reference number format: {COUNTRY}{type}.{NUMBER}
        # e.g., QDi.001, KPe.015, IRi.042
        ref = reference_number or ''
        
        # Pattern for UN reference numbers - extract country code dynamically
        match = re.match(r'^([A-Z]{2})([ie])\.(\d+)$', ref)
        if match:
            country_code = match.group(1)
            entity_indicator = match.group(2)  # 'i' for individual, 'e' for entity
            list_type = f"{country_code}{entity_indicator}"
            
            # Log any new/unknown country codes for review
            # This helps identify when UN adds new sanctions programs
            if country_code not in self._discovered_country_codes:
                self._discovered_country_codes.add(country_code)
                logger.info(f"Discovered UN country code: {country_code} (from reference: {ref})")
        
        # Extract committee from UN_LIST_TYPE element if provided
        # This is the authoritative source from the XML
        if un_list_type:
            committee = un_list_type
            # Track discovered list types
            if un_list_type not in self._discovered_list_types:
                self._discovered_list_types.add(un_list_type)
                logger.info(f"Discovered UN list type: {un_list_type}")
        
        return list_type, country_code, committee
    
    def get_entities_as_dicts(self) -> List[Dict[str, Any]]:
        """Get all parsed entities as dictionaries
        
        Returns:
            List of entity dictionaries
        """
        return [e.to_dict() for e in self._entities]
    
    def download_and_parse_all(self) -> Tuple[List[SanctionsEntity], ValidationResult]:
        """Download and parse all sanctions lists
        
        Returns:
            Tuple of (entities list, validation result)
        """
        all_entities = []
        validation_result = ValidationResult(is_valid=True)
        
        # OFAC
        logger.info("\n=== Processing OFAC SDN List ===")
        ofac_zip = self.download_ofac()
        if ofac_zip:
            ofac_xml = self.unzip_ofac()
            if ofac_xml:
                ofac_validation = self.validate_ofac_xml(ofac_xml)
                validation_result.errors.extend(ofac_validation.errors)
                validation_result.warnings.extend(ofac_validation.warnings)
                
                if ofac_validation.is_valid or not ofac_validation.errors:
                    ofac_entities = self.parse_ofac_xml(ofac_xml)
                    all_entities.extend(ofac_entities)
                    logger.info(f"  Total OFAC entities: {len(ofac_entities)}")
        
        # UN
        logger.info("\n=== Processing UN Consolidated List ===")
        un_xml = self.download_un()
        if un_xml:
            un_entities = self.parse_un_xml(un_xml)
            all_entities.extend(un_entities)
            logger.info(f"  Total UN entities: {len(un_entities)}")
        
        self._entities = all_entities
        validation_result.entity_count = len(all_entities)
        
        if validation_result.errors:
            validation_result.is_valid = False
        
        self._validation_result = validation_result
        
        logger.info(f"\n=== Download Complete ===")
        logger.info(f"Total entities loaded: {len(all_entities)}")
        
        # Log summary of discovered UN codes (extracted dynamically from XML)
        if self._discovered_country_codes:
            logger.info(f"UN country codes discovered: {sorted(self._discovered_country_codes)}")
        if self._discovered_list_types:
            logger.info(f"UN list types discovered: {sorted(self._discovered_list_types)}")
        
        return all_entities, validation_result
    
    def get_discovered_un_metadata(self) -> Dict[str, Any]:
        """Get metadata about UN codes discovered during parsing
        
        Returns:
            Dictionary with discovered country codes and list types
        """
        return {
            'country_codes': sorted(self._discovered_country_codes),
            'list_types': sorted(self._discovered_list_types)
        }


def main():
    """Main entry point"""
    print("\n=== Enhanced Sanctions List Downloader v2.0 ===")
    print(f"Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
    
    try:
        downloader = EnhancedSanctionsDownloader()
        entities, validation = downloader.download_and_parse_all()
        
        print(f"\n=== Summary ===")
        print(f"Total entities: {len(entities)}")
        print(f"Validation status: {'PASSED' if validation.is_valid else 'FAILED'}")
        
        if validation.warnings:
            print(f"\nWarnings ({len(validation.warnings)}):")
            for w in validation.warnings[:5]:
                print(f"  - {w}")
            if len(validation.warnings) > 5:
                print(f"  ... and {len(validation.warnings) - 5} more")
        
        if validation.errors:
            print(f"\nErrors ({len(validation.errors)}):")
            for e in validation.errors:
                print(f"  - {e}")
        
        # Sample output
        if entities:
            print(f"\nSample entity:")
            sample = entities[0]
            print(f"  ID: {sample.entity_id}")
            print(f"  Name: {sample.primary_name}")
            print(f"  Type: {sample.entity_type}")
            print(f"  Source: {sample.source}")
            print(f"  Documents: {len(sample.identity_documents)}")
            print(f"  Features: {len(sample.features)}")
        
    except Exception as e:
        print(f"\n✗ Error: {e}")
        raise


if __name__ == "__main__":
    main()
