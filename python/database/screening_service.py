"""
Database-backed Screening Service for SDNCheck

This module provides the screening functionality using PostgreSQL as the data source
instead of loading XML files directly. It follows dependency injection patterns
for improved testability and maintainability.

Key Features:
- PostgreSQL-backed entity search using trigram similarity
- Document-based exact match searching
- Multi-layer matching with confidence scoring
- Compatible with the existing EnhancedSanctionsScreener interface
- FastAPI Dependency Injection support

Usage:
    # With FastAPI
    @app.get("/screen")
    def screen(
        name: str,
        screening_service: DatabaseScreeningService = Depends(get_screening_service)
    ):
        return screening_service.search_by_name(name)

    # Standalone
    with db_provider.session_scope() as session:
        service = DatabaseScreeningService(session, config)
        results = service.search_by_name("John Doe")
"""

import logging
import uuid
import re
import unicodedata
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass, field

from sqlalchemy import select, text, and_, func
from sqlalchemy.orm import Session, joinedload

from database.models import (
    SanctionedEntity,
    IdentityDocument,
    EntityAlias,
    EntityAddress,
    EntityFeature,
    DataSourceType,
    normalize_name,
    normalize_document,
)
from database.repositories import SanctionedEntityRepository

logger = logging.getLogger(__name__)


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
            "overall": round(self.overall, 2),
            "name": round(self.name_score, 2),
            "document": round(self.document_score, 2),
            "dob": round(self.dob_score, 2),
            "nationality": round(self.nationality_score, 2),
            "address": round(self.address_score, 2),
        }


@dataclass
class MatchResult:
    """Complete match result with confidence breakdown and flags"""
    entity: Dict[str, Any]
    confidence: ConfidenceBreakdown
    flags: List[str] = field(default_factory=list)
    recommendation: str = "MANUAL_REVIEW"
    match_layer: int = 4
    matched_name: str = ""
    matched_document: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "entity": self.entity,
            "confidence": self.confidence.to_dict(),
            "flags": self.flags,
            "recommendation": self.recommendation,
            "match_layer": self.match_layer,
            "matched_name": self.matched_name,
            "matched_document": self.matched_document,
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


class DatabaseScreeningService:
    """
    Database-backed screening service using PostgreSQL.
    
    This service provides screening functionality by querying entities
    directly from the PostgreSQL database, supporting:
    - Trigram similarity search for names
    - Exact match for documents
    - Multi-layer confidence scoring
    
    Follows the dependency injection pattern for testability.
    """

    def __init__(self, session: Session, config: Optional[Any] = None):
        """
        Initialize the screening service.
        
        Args:
            session: SQLAlchemy database session
            config: Optional ConfigManager instance
        """
        self.session = session
        self.config = config
        self._entity_repo = SanctionedEntityRepository(session)
        
        # Default thresholds (can be overridden by config)
        self._name_threshold = 75
        self._short_name_threshold = 75
        self._layers = {
            "exact_match": 100,
            "high_confidence": 85,
            "moderate_match": 70,
            "low_match": 60,
        }
        self._weights = {
            "name": 1.0,
            "document": 0.0,
            "dob": 0.0,
            "nationality": 0.0,
            "address": 0.0,
        }
        self._recommendation_thresholds = {
            "auto_clear": 60,
            "manual_review": 85,
            "auto_escalate": 95,
        }
        
        # Apply config if provided
        if config:
            self._apply_config(config)
    
    def _apply_config(self, config) -> None:
        """Apply configuration settings."""
        if hasattr(config, 'matching'):
            self._name_threshold = config.matching.name_threshold
            self._short_name_threshold = config.matching.short_name_threshold
            if config.matching.weights:
                self._weights = config.matching.weights
            if config.matching.layers:
                self._layers = config.matching.layers
        
        if hasattr(config, 'reporting') and config.reporting.recommendation_thresholds:
            self._recommendation_thresholds = config.reporting.recommendation_thresholds
    
    def get_entity_count(self) -> int:
        """Get total number of active entities in database."""
        query = select(func.count(SanctionedEntity.id)).where(
            SanctionedEntity.is_deleted == False
        )
        return self.session.execute(query).scalar_one()
    
    def get_entity_count_by_source(self) -> Dict[str, int]:
        """Get entity counts grouped by source."""
        return self._entity_repo.count_by_source()
    
    def search_by_document(
        self,
        doc_number: str,
        doc_type: Optional[str] = None
    ) -> List[MatchResult]:
        """
        Search for entity by document number (Layer 1: Exact Match).
        
        Args:
            doc_number: Document number to search
            doc_type: Optional document type filter
            
        Returns:
            List of matching results with 100% confidence
        """
        results = []
        entities = self._entity_repo.search_by_document(doc_number, doc_type)
        
        for entity in entities:
            entity_dict = self._entity_to_dict(entity)
            
            # Find the matched document
            matched_doc = None
            normalized = normalize_document(doc_number)
            for doc in entity.documents:
                if doc.normalized_number == normalized:
                    if doc_type is None or doc.document_type.upper() == doc_type.upper():
                        matched_doc = doc.document_number
                        break
            
            confidence = ConfidenceBreakdown(
                overall=100.0,
                document_score=100.0,
                name_score=100.0,
            )
            
            result = MatchResult(
                entity=entity_dict,
                confidence=confidence,
                flags=["DOCUMENT_EXACT_MATCH"],
                recommendation="AUTO_ESCALATE",
                match_layer=1,
                matched_name=entity.primary_name,
                matched_document=matched_doc,
            )
            results.append(result)
        
        return results
    
    def search_by_name(
        self,
        name: str,
        threshold: Optional[float] = None,
        limit: int = 100
    ) -> List[Tuple[SanctionedEntity, float]]:
        """
        Search entities by name using trigram similarity.
        
        Args:
            name: Name to search for
            threshold: Minimum similarity threshold (0.0-1.0)
            limit: Maximum results to return
            
        Returns:
            List of tuples (entity, similarity_score)
        """
        if threshold is None:
            threshold = self._name_threshold / 100.0
        
        return self._entity_repo.search_by_name(name, threshold, limit)
    
    def search(
        self,
        input_data: ScreeningInput,
        limit: int = 10
    ) -> List[MatchResult]:
        """
        Multi-layer search with comprehensive scoring.
        
        Args:
            input_data: Screening input containing name and optional fields
            limit: Maximum results to return
            
        Returns:
            List of MatchResult objects sorted by confidence
        """
        results = []
        
        # Layer 1: Document exact match (if provided)
        if input_data.document_number:
            doc_matches = self.search_by_document(
                input_data.document_number,
                input_data.document_type
            )
            results.extend(doc_matches)
        
        # Determine threshold based on name characteristics
        is_short = self._is_short_name(input_data.name)
        base_threshold = (
            self._short_name_threshold if is_short else self._name_threshold
        )
        
        # Layer 2-4: Name-based matching using trigram similarity
        name_threshold = base_threshold / 100.0
        entity_scores = self.search_by_name(input_data.name, name_threshold, limit * 2)
        
        seen_entity_ids = {r.entity["id"] for r in results}
        
        for entity, similarity_score in entity_scores:
            if str(entity.id) in seen_entity_ids:
                continue
            
            # Convert similarity score (0-1) to percentage
            name_score = similarity_score * 100
            
            # Calculate document score
            doc_score = 0.0
            matched_doc = None
            if input_data.document_number:
                input_doc_norm = normalize_document(input_data.document_number)
                for doc in entity.documents:
                    if doc.normalized_number == input_doc_norm:
                        doc_score = 100.0
                        matched_doc = doc.document_number
                        break
            
            # Calculate DOB score
            dob_score = 0.0
            if input_data.date_of_birth and entity.date_of_birth:
                dob_score = self._calculate_dob_score(
                    input_data.date_of_birth,
                    entity.date_of_birth
                )
            
            # Calculate overall score using weights
            overall = (
                name_score * self._weights.get("name", 1.0) +
                doc_score * self._weights.get("document", 0.0) +
                dob_score * self._weights.get("dob", 0.0)
            )
            
            confidence = ConfidenceBreakdown(
                overall=max(0, min(100, overall)),
                name_score=name_score,
                document_score=doc_score,
                dob_score=dob_score,
            )
            
            # Determine layer and flags
            flags = []
            layer = 4
            
            if doc_score == 100:
                layer = 1
                flags.append("DOCUMENT_MATCH")
            elif name_score >= self._layers["high_confidence"]:
                layer = 2 if dob_score >= 60 else 3
            elif name_score >= self._layers["moderate_match"]:
                layer = 3
            else:
                layer = 4
            
            if is_short:
                flags.append("SHORT_NAME_QUERY")
            
            # Determine recommendation
            if confidence.overall >= self._recommendation_thresholds["auto_escalate"]:
                recommendation = "AUTO_ESCALATE"
            elif confidence.overall >= self._recommendation_thresholds["manual_review"]:
                recommendation = "MANUAL_REVIEW"
            elif confidence.overall >= self._recommendation_thresholds["auto_clear"]:
                recommendation = "LOW_CONFIDENCE_REVIEW"
            else:
                recommendation = "AUTO_CLEAR"
            
            # Check if meets threshold
            if confidence.overall >= base_threshold or doc_score == 100:
                entity_dict = self._entity_to_dict(entity)
                result = MatchResult(
                    entity=entity_dict,
                    confidence=confidence,
                    flags=flags,
                    recommendation=recommendation,
                    match_layer=layer,
                    matched_name=entity.primary_name,
                    matched_document=matched_doc,
                )
                results.append(result)
        
        # Sort by confidence
        results.sort(key=lambda x: x.confidence.overall, reverse=True)
        
        return results[:limit]
    
    def screen_individual(
        self,
        name: str,
        document: Optional[str] = None,
        document_type: Optional[str] = None,
        date_of_birth: Optional[str] = None,
        nationality: Optional[str] = None,
        country: Optional[str] = None,
        analyst: Optional[str] = None,
        generate_report: bool = False,
    ) -> Dict[str, Any]:
        """
        Screen an individual with comprehensive result.
        
        This method provides the same interface as EnhancedSanctionsScreener.screen_individual
        for compatibility.
        
        Args:
            name: Name to screen
            document: Optional document number
            document_type: Optional document type
            date_of_birth: Optional DOB
            nationality: Optional nationality
            country: Optional country
            analyst: Optional analyst name
            generate_report: Whether to generate report files (not supported in DB mode)
            
        Returns:
            Complete screening result dictionary
        """
        screening_id = str(uuid.uuid4())
        screening_date = datetime.now(timezone.utc)
        
        input_data = ScreeningInput(
            name=name,
            document_number=document,
            document_type=document_type,
            date_of_birth=date_of_birth,
            nationality=nationality,
            country=country,
        )
        
        matches = self.search(input_data, limit=10)
        is_hit = len(matches) > 0
        
        algorithm_version = "2.0.0"
        if self.config and hasattr(self.config, 'algorithm'):
            algorithm_version = self.config.algorithm.version
        
        result = {
            "screening_id": screening_id,
            "input": {
                "name": name,
                "document": document,
                "document_type": document_type,
                "date_of_birth": date_of_birth,
                "nationality": nationality,
                "country": country,
            },
            "screening_date": screening_date.isoformat(),
            "is_hit": is_hit,
            "hit_count": len(matches),
            "matches": [m.to_dict() for m in matches],
            "analyst": analyst,
            "algorithm_version": algorithm_version,
            "thresholds_used": {
                "name": self._name_threshold,
                "short_name": self._short_name_threshold,
            },
            "data_source": "database",
        }
        
        return result
    
    def _entity_to_dict(self, entity: SanctionedEntity) -> Dict[str, Any]:
        """Convert SQLAlchemy entity to dictionary format."""
        # Collect all names
        all_names = [entity.primary_name]
        aliases = []
        for alias in entity.aliases:
            if alias.alias_name not in all_names:
                all_names.append(alias.alias_name)
                aliases.append(alias.alias_name)
        
        # Collect countries
        countries = []
        if entity.nationality:
            countries.append(entity.nationality)
        if entity.citizenship and entity.citizenship not in countries:
            countries.append(entity.citizenship)
        for addr in entity.addresses:
            if addr.country and addr.country not in countries:
                countries.append(addr.country)
        
        # Collect identity documents
        identity_documents = []
        for doc in entity.documents:
            identity_documents.append({
                "type": doc.document_type,
                "number": doc.document_number,
                "issuingCountry": doc.issuing_country,
                "issueDate": doc.issue_date,
                "expirationDate": doc.expiration_date,
            })
        
        # Collect features
        features = []
        for feature in entity.features:
            features.append({
                "type": feature.feature_type,
                "value": feature.feature_value,
            })
        
        # Collect addresses
        addresses = []
        for addr in entity.addresses:
            addr_dict = {}
            if addr.address_line1:
                addr_dict["addressLine1"] = addr.address_line1
            if addr.city:
                addr_dict["city"] = addr.city
            if addr.state_province:
                addr_dict["stateProvince"] = addr.state_province
            if addr.postal_code:
                addr_dict["postalCode"] = addr.postal_code
            if addr.country:
                addr_dict["country"] = addr.country
            if addr_dict:
                addresses.append(addr_dict)
        
        return {
            "id": str(entity.id),
            "source": entity.source.value if hasattr(entity.source, 'value') else str(entity.source),
            "type": entity.entity_type.value if hasattr(entity.entity_type, 'value') else str(entity.entity_type),
            "name": entity.primary_name,
            "all_names": all_names,
            "aliases": aliases,
            "firstName": entity.first_name,
            "lastName": entity.last_name,
            "countries": countries,
            "identity_documents": identity_documents,
            "features": features,
            "addresses": addresses,
            "dateOfBirth": entity.date_of_birth,
            "placeOfBirth": entity.place_of_birth,
            "nationality": entity.nationality,
            "citizenship": entity.citizenship,
            "gender": entity.gender,
            "title": entity.title,
            "program": None,  # Would need to join programs table
        }
    
    def _is_short_name(self, name: str) -> bool:
        """Check if name is considered short (requires stricter matching)."""
        words = name.split()
        if len(words) <= 2 and len(name) < 10:
            return True
        if any(len(word) <= 2 for word in words):
            return True
        return False
    
    def _calculate_dob_score(self, input_dob: str, entity_dob: str) -> float:
        """Calculate DOB similarity score."""
        try:
            input_year = self._extract_year(input_dob)
            entity_year = self._extract_year(entity_dob)
            
            if input_year and entity_year:
                diff = abs(input_year - entity_year)
                return max(0, 100 - (diff * 20))
        except Exception:
            pass
        return 0.0
    
    def _extract_year(self, date_str: str) -> Optional[int]:
        """Extract year from date string."""
        if not date_str:
            return None
        
        patterns = [
            r"(\d{4})",
            r"(\d{4})-\d{2}-\d{2}",
            r"\d{2}/\d{2}/(\d{4})",
            r"\d{2}-\d{2}-(\d{4})",
        ]
        
        for pattern in patterns:
            match = re.search(pattern, date_str)
            if match:
                return int(match.group(1))
        
        return None


# FastAPI Dependency Injection Support
_screening_service_factory = None


def configure_screening_service(db_provider, config=None):
    """
    Configure the screening service factory for dependency injection.
    
    Call this during application startup.
    
    Args:
        db_provider: DatabaseSessionProvider instance
        config: Optional ConfigManager instance
    """
    global _screening_service_factory
    _screening_service_factory = (db_provider, config)


def get_screening_service():
    """
    FastAPI dependency for getting a DatabaseScreeningService.
    
    Usage:
        @app.get("/screen")
        def screen(
            name: str,
            service: DatabaseScreeningService = Depends(get_screening_service)
        ):
            return service.search_by_name(name)
    
    Yields:
        DatabaseScreeningService instance
        
    Raises:
        RuntimeError: If screening service not configured
    """
    global _screening_service_factory
    if _screening_service_factory is None:
        raise RuntimeError(
            "Screening service not configured. Call configure_screening_service() first."
        )
    
    db_provider, config = _screening_service_factory
    
    with db_provider.session_scope() as session:
        service = DatabaseScreeningService(session, config)
        yield service
