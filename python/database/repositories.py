"""
Repository Pattern for SDNCheck Database Operations

Provides clean data access layer with proper typing and error handling.
Implements the Repository pattern for separation of concerns.
"""

import logging
from typing import List, Optional, Dict, Any, Tuple
from uuid import UUID
from datetime import datetime, timezone

from sqlalchemy import select, func, text, and_, or_
from sqlalchemy.orm import Session, joinedload
from sqlalchemy.exc import SQLAlchemyError, IntegrityError

from database.models import (
    SanctionedEntity,
    EntityAlias,
    IdentityDocument,
    EntityAddress,
    EntityFeature,
    SanctionsProgram,
    EntityProgram,
    ScreeningRequest,
    ScreeningResult,
    ScreeningMatch,
    AuditLog,
    DataSource,
    DataUpdate,
    DataSourceType,
    EntityType,
    ScreeningStatus,
    RecommendationType,
    AuditAction,
    normalize_name,
    normalize_document
)

logger = logging.getLogger(__name__)


class RepositoryError(Exception):
    """Base exception for repository errors."""
    pass


class EntityNotFoundError(RepositoryError):
    """Raised when an entity is not found."""
    pass


class DuplicateEntityError(RepositoryError):
    """Raised when attempting to create a duplicate entity."""
    pass


# ============================================
# ENTITY REPOSITORY
# ============================================

class SanctionedEntityRepository:
    """Repository for sanctioned entity operations."""
    
    def __init__(self, session: Session):
        self.session = session
    
    def create(self, entity_data: Dict[str, Any]) -> SanctionedEntity:
        """
        Create a new sanctioned entity.
        
        Args:
            entity_data: Dictionary containing entity fields
            
        Returns:
            Created SanctionedEntity instance
            
        Raises:
            DuplicateEntityError: If entity with same external_id/source exists
        """
        try:
            # Normalize name
            primary_name = entity_data.get('primary_name', '')
            entity_data['normalized_name'] = normalize_name(primary_name)
            
            entity = SanctionedEntity(**entity_data)
            self.session.add(entity)
            self.session.flush()
            
            logger.debug(f"Created entity: {entity.id} ({entity.primary_name})")
            return entity
            
        except IntegrityError as e:
            self.session.rollback()
            raise DuplicateEntityError(f"Entity already exists: {e}")
    
    def get_by_id(self, entity_id: UUID, include_deleted: bool = False) -> Optional[SanctionedEntity]:
        """
        Get entity by ID.
        
        Args:
            entity_id: UUID of the entity
            include_deleted: If True, include soft-deleted entities
            
        Returns:
            SanctionedEntity or None
        """
        query = select(SanctionedEntity).where(SanctionedEntity.id == entity_id)
        
        if not include_deleted:
            query = query.where(SanctionedEntity.is_deleted == False)
        
        query = query.options(
            joinedload(SanctionedEntity.aliases),
            joinedload(SanctionedEntity.documents),
            joinedload(SanctionedEntity.addresses)
        )
        
        result = self.session.execute(query)
        return result.unique().scalar_one_or_none()
    
    def get_by_external_id(
        self, 
        external_id: str, 
        source: DataSourceType
    ) -> Optional[SanctionedEntity]:
        """
        Get entity by external ID and source.
        
        Args:
            external_id: External ID from source system
            source: Data source type (OFAC, UN, etc.)
            
        Returns:
            SanctionedEntity or None
        """
        query = select(SanctionedEntity).where(
            and_(
                SanctionedEntity.external_id == external_id,
                SanctionedEntity.source == source,
                SanctionedEntity.is_deleted == False
            )
        )
        result = self.session.execute(query)
        return result.unique().scalar_one_or_none()
    
    def search_by_name(
        self,
        name: str,
        threshold: float = 0.3,
        limit: int = 100
    ) -> List[Tuple[SanctionedEntity, float]]:
        """
        Search entities by name using trigram similarity.
        
        Uses a single query with eager loading to avoid N+1 queries.
        
        Args:
            name: Name to search for
            threshold: Minimum similarity threshold (0.0-1.0)
            limit: Maximum results to return
            
        Returns:
            List of tuples (entity, similarity_score)
        """
        normalized = normalize_name(name)
        
        # First, get the IDs and similarity scores using raw SQL for trigram
        id_query = text("""
            SELECT 
                e.id,
                similarity(e.normalized_name, :name) as sim_score
            FROM sanctioned_entities e
            WHERE 
                e.is_deleted = false
                AND similarity(e.normalized_name, :name) > :threshold
            ORDER BY sim_score DESC
            LIMIT :limit
        """)
        
        id_result = self.session.execute(
            id_query,
            {"name": normalized, "threshold": threshold, "limit": limit}
        )
        
        # Collect IDs and scores
        id_score_map = {}
        entity_ids = []
        for row in id_result.mappings():
            entity_id = row['id']
            entity_ids.append(entity_id)
            id_score_map[entity_id] = row['sim_score']
        
        if not entity_ids:
            return []
        
        # Single query with eager loading for all related data
        # This fixes the N+1 query problem
        entity_query = select(SanctionedEntity).where(
            SanctionedEntity.id.in_(entity_ids)
        ).options(
            joinedload(SanctionedEntity.aliases),
            joinedload(SanctionedEntity.documents),
            joinedload(SanctionedEntity.addresses),
            joinedload(SanctionedEntity.features)
        )
        
        result = self.session.execute(entity_query)
        entities_by_id = {e.id: e for e in result.scalars().unique()}
        
        # Build result list maintaining the original order and scores
        entities = []
        for entity_id in entity_ids:
            entity = entities_by_id.get(entity_id)
            if entity:
                entities.append((entity, id_score_map[entity_id]))
        
        return entities
    
    def search_by_document(
        self,
        document_number: str,
        document_type: Optional[str] = None
    ) -> List[SanctionedEntity]:
        """
        Search entities by document number.
        
        Args:
            document_number: Document number to search
            document_type: Optional document type filter
            
        Returns:
            List of matching entities
        """
        normalized = normalize_document(document_number)
        
        query = select(SanctionedEntity).join(
            IdentityDocument
        ).where(
            and_(
                IdentityDocument.normalized_number == normalized,
                SanctionedEntity.is_deleted == False
            )
        )
        
        if document_type:
            query = query.where(IdentityDocument.document_type == document_type)
        
        result = self.session.execute(query.distinct())
        return list(result.scalars().all())
    
    def list_by_source(
        self,
        source: DataSourceType,
        entity_type: Optional[EntityType] = None,
        offset: int = 0,
        limit: int = 100
    ) -> Tuple[List[SanctionedEntity], int]:
        """
        List entities by source with pagination.
        
        Args:
            source: Data source type
            entity_type: Optional entity type filter
            offset: Pagination offset
            limit: Maximum results
            
        Returns:
            Tuple of (entities list, total count)
        """
        conditions = [
            SanctionedEntity.source == source,
            SanctionedEntity.is_deleted == False
        ]
        
        if entity_type:
            conditions.append(SanctionedEntity.entity_type == entity_type)
        
        # Count query
        count_query = select(func.count()).select_from(SanctionedEntity).where(
            and_(*conditions)
        )
        total = self.session.execute(count_query).scalar_one()
        
        # Data query
        query = select(SanctionedEntity).where(
            and_(*conditions)
        ).offset(offset).limit(limit).order_by(SanctionedEntity.primary_name)
        
        result = self.session.execute(query)
        entities = list(result.scalars().all())
        
        return entities, total
    
    def update(
        self,
        entity_id: UUID,
        updates: Dict[str, Any]
    ) -> SanctionedEntity:
        """
        Update an entity.
        
        Args:
            entity_id: UUID of entity to update
            updates: Dictionary of fields to update
            
        Returns:
            Updated entity
            
        Raises:
            EntityNotFoundError: If entity not found
        """
        entity = self.get_by_id(entity_id)
        if not entity:
            raise EntityNotFoundError(f"Entity not found: {entity_id}")
        
        # Update normalized name if primary name changed
        if 'primary_name' in updates:
            updates['normalized_name'] = normalize_name(updates['primary_name'])
        
        # Increment version for optimistic locking
        updates['version'] = entity.version + 1
        
        for key, value in updates.items():
            if hasattr(entity, key):
                setattr(entity, key, value)
        
        self.session.flush()
        return entity
    
    def soft_delete(self, entity_id: UUID) -> bool:
        """
        Soft delete an entity.
        
        Args:
            entity_id: UUID of entity to delete
            
        Returns:
            True if deleted, False if not found
        """
        entity = self.get_by_id(entity_id)
        if not entity:
            return False
        
        entity.is_deleted = True
        entity.deleted_at = datetime.now(timezone.utc)
        self.session.flush()
        return True
    
    def count_by_source(self, source: Optional[DataSourceType] = None) -> Dict[str, int]:
        """
        Get entity counts by source.
        
        Args:
            source: Optional source filter
            
        Returns:
            Dictionary with counts by source
        """
        query = select(
            SanctionedEntity.source,
            func.count(SanctionedEntity.id)
        ).where(
            SanctionedEntity.is_deleted == False
        ).group_by(SanctionedEntity.source)
        
        if source:
            query = query.where(SanctionedEntity.source == source)
        
        result = self.session.execute(query)
        return {str(row[0].value): row[1] for row in result}


# ============================================
# SCREENING REPOSITORY
# ============================================

class ScreeningRepository:
    """Repository for screening operations."""
    
    def __init__(self, session: Session):
        self.session = session
    
    def create_request(
        self,
        input_data: Dict[str, Any],
        request_type: str = "single",
        analyst_name: Optional[str] = None,
        analyst_id: Optional[str] = None,
        api_key_id: Optional[str] = None,
        ip_address: Optional[str] = None
    ) -> ScreeningRequest:
        """
        Create a new screening request.
        
        Args:
            input_data: Input data for screening
            request_type: "single" or "bulk"
            analyst_name: Name of analyst
            analyst_id: ID of analyst
            api_key_id: API key used
            ip_address: Client IP address
            
        Returns:
            Created ScreeningRequest
        """
        request = ScreeningRequest(
            request_type=request_type,
            status=ScreeningStatus.PENDING,
            input_data=input_data,
            screened_name=input_data.get('name'),
            screened_document=input_data.get('document'),
            analyst_name=analyst_name,
            analyst_id=analyst_id,
            api_key_id=api_key_id,
            ip_address=ip_address,
            processing_start=datetime.now(timezone.utc)
        )
        
        self.session.add(request)
        self.session.flush()
        return request
    
    def add_result(
        self,
        request_id: UUID,
        input_name: str,
        is_hit: bool,
        hit_count: int = 0,
        max_confidence: Optional[float] = None,
        recommendation: Optional[RecommendationType] = None,
        flags: Optional[List[str]] = None,
        input_document: Optional[str] = None,
        input_country: Optional[str] = None
    ) -> ScreeningResult:
        """
        Add a result to a screening request.
        
        Args:
            request_id: UUID of the request
            input_name: Name that was screened
            is_hit: Whether matches were found
            hit_count: Number of matches
            max_confidence: Highest confidence score
            recommendation: Overall recommendation
            flags: Quality flags
            input_document: Document number screened
            input_country: Country provided
            
        Returns:
            Created ScreeningResult
        """
        result = ScreeningResult(
            request_id=request_id,
            input_name=input_name,
            input_document=input_document,
            input_country=input_country,
            is_hit=is_hit,
            hit_count=hit_count,
            max_confidence=max_confidence,
            recommendation=recommendation,
            flags=flags
        )
        
        self.session.add(result)
        self.session.flush()
        return result
    
    def add_match(
        self,
        result_id: UUID,
        matched_name: str,
        match_layer: int,
        overall_confidence: float,
        recommendation: RecommendationType,
        entity_id: Optional[UUID] = None,
        matched_document: Optional[str] = None,
        name_confidence: float = 0.0,
        document_confidence: float = 0.0,
        dob_confidence: float = 0.0,
        nationality_confidence: float = 0.0,
        address_confidence: float = 0.0,
        flags: Optional[List[str]] = None,
        entity_snapshot: Optional[Dict[str, Any]] = None
    ) -> ScreeningMatch:
        """
        Add a match to a screening result.
        
        Args:
            result_id: UUID of the result
            matched_name: Name of matched entity
            match_layer: Match layer (1-4)
            overall_confidence: Overall confidence score
            recommendation: Match recommendation
            entity_id: UUID of matched entity (if in DB)
            matched_document: Document that matched
            *_confidence: Individual confidence scores
            flags: Quality flags
            entity_snapshot: Snapshot of entity data
            
        Returns:
            Created ScreeningMatch
        """
        match = ScreeningMatch(
            result_id=result_id,
            entity_id=entity_id,
            matched_name=matched_name,
            matched_document=matched_document,
            match_layer=match_layer,
            overall_confidence=overall_confidence,
            name_confidence=name_confidence,
            document_confidence=document_confidence,
            dob_confidence=dob_confidence,
            nationality_confidence=nationality_confidence,
            address_confidence=address_confidence,
            flags=flags,
            recommendation=recommendation,
            entity_snapshot=entity_snapshot
        )
        
        self.session.add(match)
        self.session.flush()
        return match
    
    def complete_request(
        self,
        request_id: UUID,
        algorithm_version: Optional[str] = None,
        thresholds_used: Optional[Dict[str, Any]] = None
    ) -> ScreeningRequest:
        """
        Mark a request as completed.
        
        Args:
            request_id: UUID of the request
            algorithm_version: Version of algorithm used
            thresholds_used: Thresholds applied
            
        Returns:
            Updated ScreeningRequest
        """
        query = select(ScreeningRequest).where(ScreeningRequest.id == request_id)
        result = self.session.execute(query)
        request = result.unique().scalar_one_or_none()
        
        if not request:
            raise EntityNotFoundError(f"Request not found: {request_id}")
        
        request.status = ScreeningStatus.COMPLETED
        request.processing_end = datetime.now(timezone.utc)
        
        if request.processing_start:
            delta = request.processing_end - request.processing_start
            request.processing_time_ms = int(delta.total_seconds() * 1000)
        
        request.algorithm_version = algorithm_version
        request.thresholds_used = thresholds_used
        
        self.session.flush()
        return request
    
    def fail_request(
        self,
        request_id: UUID,
        error_message: str,
        error_code: Optional[str] = None
    ) -> ScreeningRequest:
        """
        Mark a request as failed.
        
        Args:
            request_id: UUID of the request
            error_message: Error description
            error_code: Error code
            
        Returns:
            Updated ScreeningRequest
        """
        query = select(ScreeningRequest).where(ScreeningRequest.id == request_id)
        result = self.session.execute(query)
        request = result.unique().scalar_one_or_none()
        
        if not request:
            raise EntityNotFoundError(f"Request not found: {request_id}")
        
        request.status = ScreeningStatus.FAILED
        request.processing_end = datetime.now(timezone.utc)
        request.error_message = error_message
        request.error_code = error_code
        
        self.session.flush()
        return request
    
    def get_request_with_results(self, request_id: UUID) -> Optional[ScreeningRequest]:
        """
        Get a screening request with all results and matches.
        
        Args:
            request_id: UUID of the request
            
        Returns:
            ScreeningRequest with loaded relationships or None
        """
        query = select(ScreeningRequest).where(
            ScreeningRequest.id == request_id
        ).options(
            joinedload(ScreeningRequest.results).joinedload(ScreeningResult.matches)
        )
        
        result = self.session.execute(query)
        return result.unique().scalar_one_or_none()
    
    def get_screening_stats(
        self,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None
    ) -> Dict[str, Any]:
        """
        Get screening statistics for a date range.
        
        Args:
            start_date: Start of date range
            end_date: End of date range
            
        Returns:
            Dictionary with statistics
        """
        conditions = []
        if start_date:
            conditions.append(ScreeningRequest.created_at >= start_date)
        if end_date:
            conditions.append(ScreeningRequest.created_at <= end_date)
        
        # Total requests
        total_query = select(func.count()).select_from(ScreeningRequest)
        if conditions:
            total_query = total_query.where(and_(*conditions))
        total = self.session.execute(total_query).scalar_one()
        
        # Status breakdown
        status_query = select(
            ScreeningRequest.status,
            func.count()
        ).group_by(ScreeningRequest.status)
        if conditions:
            status_query = status_query.where(and_(*conditions))
        status_result = self.session.execute(status_query)
        status_counts = {str(row[0].value): row[1] for row in status_result}
        
        # Hit rate
        hit_query = select(func.count()).select_from(ScreeningResult).where(
            ScreeningResult.is_hit == True
        )
        if conditions:
            hit_query = hit_query.join(ScreeningRequest).where(and_(*conditions))
        hits = self.session.execute(hit_query).scalar_one()
        
        total_results_query = select(func.count()).select_from(ScreeningResult)
        if conditions:
            total_results_query = total_results_query.join(ScreeningRequest).where(
                and_(*conditions)
            )
        total_results = self.session.execute(total_results_query).scalar_one()
        
        hit_rate = (hits / total_results * 100) if total_results > 0 else 0.0
        
        return {
            'total_requests': total,
            'status_breakdown': status_counts,
            'total_results': total_results,
            'total_hits': hits,
            'hit_rate_percent': round(hit_rate, 2)
        }


# ============================================
# AUDIT REPOSITORY
# ============================================

class AuditRepository:
    """Repository for audit log operations."""
    
    def __init__(self, session: Session):
        self.session = session
    
    def log(
        self,
        action: AuditAction,
        resource_type: str,
        resource_id: Optional[str] = None,
        actor_id: Optional[str] = None,
        actor_name: Optional[str] = None,
        actor_ip: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
        old_value: Optional[Dict[str, Any]] = None,
        new_value: Optional[Dict[str, Any]] = None,
        success: bool = True,
        error_message: Optional[str] = None
    ) -> AuditLog:
        """
        Create an audit log entry.
        
        Args:
            action: Type of action
            resource_type: Type of resource affected
            resource_id: ID of resource
            actor_*: Actor information
            details: Additional details
            old_value: Value before change
            new_value: Value after change
            success: Whether action succeeded
            error_message: Error if failed
            
        Returns:
            Created AuditLog
        """
        log = AuditLog(
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            actor_id=actor_id,
            actor_name=actor_name,
            actor_ip=actor_ip,
            details=details,
            old_value=old_value,
            new_value=new_value,
            success=success,
            error_message=error_message
        )
        
        self.session.add(log)
        self.session.flush()
        return log
    
    def search(
        self,
        action: Optional[AuditAction] = None,
        resource_type: Optional[str] = None,
        actor_id: Optional[str] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        offset: int = 0,
        limit: int = 100
    ) -> Tuple[List[AuditLog], int]:
        """
        Search audit logs with filters.
        
        Args:
            action: Filter by action type
            resource_type: Filter by resource type
            actor_id: Filter by actor
            start_date: Start of date range
            end_date: End of date range
            offset: Pagination offset
            limit: Maximum results
            
        Returns:
            Tuple of (logs list, total count)
        """
        conditions = []
        
        if action:
            conditions.append(AuditLog.action == action)
        if resource_type:
            conditions.append(AuditLog.resource_type == resource_type)
        if actor_id:
            conditions.append(AuditLog.actor_id == actor_id)
        if start_date:
            conditions.append(AuditLog.timestamp >= start_date)
        if end_date:
            conditions.append(AuditLog.timestamp <= end_date)
        
        # Count query
        count_query = select(func.count()).select_from(AuditLog)
        if conditions:
            count_query = count_query.where(and_(*conditions))
        total = self.session.execute(count_query).scalar_one()
        
        # Data query
        query = select(AuditLog)
        if conditions:
            query = query.where(and_(*conditions))
        query = query.order_by(AuditLog.timestamp.desc()).offset(offset).limit(limit)
        
        result = self.session.execute(query)
        logs = list(result.scalars().all())
        
        return logs, total


# ============================================
# DATA SOURCE REPOSITORY
# ============================================

class DataSourceRepository:
    """Repository for data source operations."""
    
    def __init__(self, session: Session):
        self.session = session
    
    def get_by_code(self, code: str) -> Optional[DataSource]:
        """Get data source by code."""
        query = select(DataSource).where(DataSource.code == code)
        result = self.session.execute(query)
        return result.scalar_one_or_none()
    
    def list_active(self) -> List[DataSource]:
        """List all active data sources."""
        query = select(DataSource).where(
            DataSource.is_active == True
        ).order_by(DataSource.code)
        result = self.session.execute(query)
        return list(result.scalars().all())
    
    def record_update(
        self,
        source_id: UUID,
        entities_added: int = 0,
        entities_updated: int = 0,
        entities_removed: int = 0,
        total_entities: int = 0,
        validation_errors: int = 0,
        validation_warnings: int = 0,
        validation_details: Optional[Dict[str, Any]] = None,
        file_hash: Optional[str] = None,
        file_size_bytes: Optional[int] = None
    ) -> DataUpdate:
        """
        Record a data update operation.
        
        Args:
            source_id: UUID of the data source
            entities_*: Entity counts
            validation_*: Validation results
            file_*: File information
            
        Returns:
            Created DataUpdate
        """
        update = DataUpdate(
            source_id=source_id,
            started_at=datetime.now(timezone.utc),
            status='in_progress',
            entities_added=entities_added,
            entities_updated=entities_updated,
            entities_removed=entities_removed,
            total_entities=total_entities,
            validation_errors=validation_errors,
            validation_warnings=validation_warnings,
            validation_details=validation_details,
            file_hash=file_hash,
            file_size_bytes=file_size_bytes
        )
        
        self.session.add(update)
        self.session.flush()
        return update
    
    def complete_update(
        self,
        update_id: UUID,
        status: str = 'completed',
        error_message: Optional[str] = None
    ) -> DataUpdate:
        """
        Complete a data update record.
        
        Args:
            update_id: UUID of the update
            status: Final status
            error_message: Error if failed
            
        Returns:
            Updated DataUpdate
        """
        query = select(DataUpdate).where(DataUpdate.id == update_id)
        result = self.session.execute(query)
        update = result.scalar_one_or_none()
        
        if not update:
            raise EntityNotFoundError(f"Update not found: {update_id}")
        
        update.completed_at = datetime.now(timezone.utc)
        update.status = status
        update.error_message = error_message
        
        # Update the source's last update info
        source_query = select(DataSource).where(DataSource.id == update.source_id)
        source_result = self.session.execute(source_query)
        source = source_result.scalar_one_or_none()
        
        if source:
            source.last_update = update.completed_at
            source.last_update_status = status
            source.last_entity_count = update.total_entities
        
        self.session.flush()
        return update
