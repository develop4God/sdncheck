"""
SQLAlchemy ORM Models for SDNCheck Sanctions Screening System

This module defines the complete database schema following senior architect best practices:
- Normalized table design (3NF)
- Proper indexing for query performance
- Audit trail support
- Soft delete capability
- Full-text search support
- UUID primary keys for distributed systems compatibility
- Proper foreign key constraints with cascading
- Timestamps for all records (created_at, updated_at)

Tables:
1. sanctioned_entities - Core entity table (individuals, organizations, vessels)
2. entity_aliases - Alternative names for entities (many-to-one)
3. identity_documents - Documents (passports, IDs) linked to entities
4. entity_addresses - Physical addresses for entities
5. entity_features - Key-value pairs for additional entity data (DOB, nationality)
6. sanctions_programs - Master list of sanctions programs (SDGT, OFAC, UN)
7. entity_programs - Junction table linking entities to programs (many-to-many)
8. screening_requests - API screening request log
9. screening_results - Results from screening operations
10. screening_matches - Individual matches found in screenings
11. audit_logs - System-wide audit trail
12. data_sources - Configuration for data sources (OFAC, UN)
13. data_updates - Log of data refresh operations
"""

import uuid
from datetime import datetime, timezone
from enum import Enum as PyEnum
from typing import List, Optional

from sqlalchemy import (
    Column, String, Integer, Float, Boolean, DateTime, Text, 
    ForeignKey, Index, CheckConstraint, UniqueConstraint, Enum,
    JSON, event
)
from sqlalchemy.dialects.postgresql import UUID, TSVECTOR, JSONB, ARRAY
from sqlalchemy.orm import relationship, declarative_base, Mapped, mapped_column
from sqlalchemy.sql import func

# Base class for all models
Base = declarative_base()


# ============================================
# ENUMS
# ============================================

class EntityType(str, PyEnum):
    """Type of sanctioned entity"""
    INDIVIDUAL = "individual"
    ENTITY = "entity"  # Organization/Company
    VESSEL = "vessel"
    AIRCRAFT = "aircraft"


class DataSourceType(str, PyEnum):
    """Source of sanctions data"""
    OFAC = "OFAC"
    UN = "UN"
    EU = "EU"
    UK = "UK"
    OTHER = "OTHER"


class DocumentType(str, PyEnum):
    """Type of identity document"""
    PASSPORT = "Passport"
    NATIONAL_ID = "National ID"
    TAX_ID = "Tax ID"
    CEDULA = "Cedula"
    DRIVERS_LICENSE = "Driver's License"
    SSN = "SSN"
    IMO = "IMO Number"
    MMSI = "MMSI"
    OTHER = "Other"


class ScreeningStatus(str, PyEnum):
    """Status of a screening request"""
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class RecommendationType(str, PyEnum):
    """Recommendation from screening result"""
    AUTO_ESCALATE = "AUTO_ESCALATE"
    MANUAL_REVIEW = "MANUAL_REVIEW"
    LOW_CONFIDENCE_REVIEW = "LOW_CONFIDENCE_REVIEW"
    AUTO_CLEAR = "AUTO_CLEAR"


class AuditAction(str, PyEnum):
    """Type of audit action"""
    CREATE = "CREATE"
    READ = "READ"
    UPDATE = "UPDATE"
    DELETE = "DELETE"
    SCREEN = "SCREEN"
    BULK_SCREEN = "BULK_SCREEN"
    DATA_UPDATE = "DATA_UPDATE"
    LOGIN = "LOGIN"
    LOGOUT = "LOGOUT"
    CONFIG_CHANGE = "CONFIG_CHANGE"


# ============================================
# MIXIN CLASSES
# ============================================

class TimestampMixin:
    """Mixin for created_at and updated_at timestamps"""
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False
    )


class SoftDeleteMixin:
    """Mixin for soft delete support"""
    is_deleted: Mapped[bool] = mapped_column(
        Boolean, 
        default=False, 
        nullable=False,
        index=True
    )
    deleted_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True
    )


# ============================================
# CORE ENTITY MODELS
# ============================================

class SanctionedEntity(Base, TimestampMixin, SoftDeleteMixin):
    """
    Main table for sanctioned individuals, entities, vessels, and aircraft.
    
    This is the core entity that all other entity-related tables reference.
    Uses UUID for primary key to support distributed systems and data imports.
    """
    __tablename__ = "sanctioned_entities"
    
    # Primary Key
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), 
        primary_key=True, 
        default=uuid.uuid4
    )
    
    # External ID from source system (OFAC ID, UN ID, etc.)
    external_id: Mapped[str] = mapped_column(
        String(100), 
        nullable=False,
        index=True
    )
    
    # Source of the data (OFAC, UN, etc.)
    source: Mapped[DataSourceType] = mapped_column(
        Enum(DataSourceType),
        nullable=False,
        index=True
    )
    
    # Type of entity
    entity_type: Mapped[EntityType] = mapped_column(
        Enum(EntityType),
        nullable=False,
        index=True
    )
    
    # Primary name (denormalized for quick access)
    primary_name: Mapped[str] = mapped_column(
        String(500),
        nullable=False,
        index=True
    )
    
    # Normalized name for searching (uppercase, no accents)
    normalized_name: Mapped[str] = mapped_column(
        String(500),
        nullable=False,
        index=True
    )
    
    # Name parts for individuals
    first_name: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    last_name: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    middle_name: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    
    # Biographical data
    date_of_birth: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    place_of_birth: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    nationality: Mapped[Optional[str]] = mapped_column(String(100), nullable=True, index=True)
    citizenship: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    gender: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    title: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    
    # Vessel-specific fields
    vessel_type: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    vessel_flag: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    vessel_tonnage: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    vessel_imo: Mapped[Optional[str]] = mapped_column(String(50), nullable=True, index=True)
    vessel_mmsi: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    vessel_call_sign: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    
    # Raw data from source (for debugging/auditing)
    raw_data: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    
    # Full-text search vector (PostgreSQL specific)
    search_vector: Mapped[Optional[str]] = mapped_column(TSVECTOR, nullable=True)
    
    # Version for optimistic locking
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    
    # Relationships
    aliases: Mapped[List["EntityAlias"]] = relationship(
        "EntityAlias",
        back_populates="entity",
        cascade="all, delete-orphan",
        lazy="selectin"
    )
    documents: Mapped[List["IdentityDocument"]] = relationship(
        "IdentityDocument",
        back_populates="entity",
        cascade="all, delete-orphan",
        lazy="selectin"
    )
    addresses: Mapped[List["EntityAddress"]] = relationship(
        "EntityAddress",
        back_populates="entity",
        cascade="all, delete-orphan",
        lazy="selectin"
    )
    features: Mapped[List["EntityFeature"]] = relationship(
        "EntityFeature",
        back_populates="entity",
        cascade="all, delete-orphan",
        lazy="selectin"
    )
    programs: Mapped[List["EntityProgram"]] = relationship(
        "EntityProgram",
        back_populates="entity",
        cascade="all, delete-orphan",
        lazy="selectin"
    )
    matches: Mapped[List["ScreeningMatch"]] = relationship(
        "ScreeningMatch",
        back_populates="matched_entity",
        lazy="dynamic"
    )
    
    # Table constraints and indexes
    __table_args__ = (
        # Unique constraint on external_id + source combination
        UniqueConstraint('external_id', 'source', name='uq_entity_external_source'),
        # Composite index for common queries
        Index('ix_entity_source_type', 'source', 'entity_type'),
        Index('ix_entity_name_source', 'normalized_name', 'source'),
        # GIN index for full-text search
        Index('ix_entity_search_vector', 'search_vector', postgresql_using='gin'),
        # Partial index for non-deleted records
        Index('ix_entity_active', 'id', postgresql_where=(Column('is_deleted') == False)),
    )
    
    def __repr__(self) -> str:
        return f"<SanctionedEntity(id={self.id}, name='{self.primary_name}', source={self.source})>"


class EntityAlias(Base, TimestampMixin):
    """
    Alternative names/aliases for sanctioned entities.
    
    One entity can have multiple aliases (original name in different scripts,
    transliterations, known aliases, etc.)
    """
    __tablename__ = "entity_aliases"
    
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), 
        primary_key=True, 
        default=uuid.uuid4
    )
    entity_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("sanctioned_entities.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    
    # Alias name
    alias_name: Mapped[str] = mapped_column(String(500), nullable=False)
    normalized_alias: Mapped[str] = mapped_column(String(500), nullable=False, index=True)
    
    # Type of alias (AKA, FKA, DBA, etc.)
    alias_type: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    
    # Quality indicator (Strong, Weak, Low)
    alias_quality: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    
    # Language/script of alias
    language: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    
    # Is this the primary name?
    is_primary: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    
    # Relationship
    entity: Mapped["SanctionedEntity"] = relationship(
        "SanctionedEntity",
        back_populates="aliases"
    )
    
    __table_args__ = (
        Index('ix_alias_normalized', 'normalized_alias'),
        Index('ix_alias_entity_primary', 'entity_id', 'is_primary'),
    )
    
    def __repr__(self) -> str:
        return f"<EntityAlias(entity_id={self.entity_id}, alias='{self.alias_name}')>"


class IdentityDocument(Base, TimestampMixin):
    """
    Identity documents associated with sanctioned entities.
    
    Stores passports, national IDs, tax IDs, vessel registration numbers, etc.
    """
    __tablename__ = "identity_documents"
    
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), 
        primary_key=True, 
        default=uuid.uuid4
    )
    entity_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("sanctioned_entities.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    
    # Document details
    document_type: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    document_number: Mapped[str] = mapped_column(String(100), nullable=False)
    normalized_number: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    
    # Issuing information
    issuing_country: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    issuing_authority: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    issue_date: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    expiration_date: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    
    # Additional notes
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    # Relationship
    entity: Mapped["SanctionedEntity"] = relationship(
        "SanctionedEntity",
        back_populates="documents"
    )
    
    __table_args__ = (
        Index('ix_document_number_type', 'normalized_number', 'document_type'),
        Index('ix_document_country', 'issuing_country'),
    )
    
    def __repr__(self) -> str:
        return f"<IdentityDocument(entity_id={self.entity_id}, type='{self.document_type}', number='{self.document_number}')>"


class EntityAddress(Base, TimestampMixin):
    """
    Physical addresses associated with sanctioned entities.
    """
    __tablename__ = "entity_addresses"
    
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), 
        primary_key=True, 
        default=uuid.uuid4
    )
    entity_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("sanctioned_entities.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    
    # Address components
    address_line1: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    address_line2: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    city: Mapped[Optional[str]] = mapped_column(String(200), nullable=True, index=True)
    state_province: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    postal_code: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    country: Mapped[Optional[str]] = mapped_column(String(100), nullable=True, index=True)
    
    # Full address for display
    full_address: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    # Type of address (Residential, Business, Registered, etc.)
    address_type: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    
    # Is this the primary address?
    is_primary: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    
    # Relationship
    entity: Mapped["SanctionedEntity"] = relationship(
        "SanctionedEntity",
        back_populates="addresses"
    )
    
    __table_args__ = (
        Index('ix_address_country_city', 'country', 'city'),
    )
    
    def __repr__(self) -> str:
        return f"<EntityAddress(entity_id={self.entity_id}, country='{self.country}')>"


class EntityFeature(Base, TimestampMixin):
    """
    Key-value pairs for additional entity features.
    
    Flexible storage for attributes that don't fit in the main entity table.
    Examples: eye color, height, weight, known associates, etc.
    """
    __tablename__ = "entity_features"
    
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), 
        primary_key=True, 
        default=uuid.uuid4
    )
    entity_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("sanctioned_entities.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    
    # Feature key-value
    feature_type: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    feature_value: Mapped[str] = mapped_column(Text, nullable=False)
    
    # Normalized value for searching
    normalized_value: Mapped[Optional[str]] = mapped_column(String(500), nullable=True, index=True)
    
    # Relationship
    entity: Mapped["SanctionedEntity"] = relationship(
        "SanctionedEntity",
        back_populates="features"
    )
    
    __table_args__ = (
        Index('ix_feature_type_value', 'feature_type', 'normalized_value'),
    )
    
    def __repr__(self) -> str:
        return f"<EntityFeature(entity_id={self.entity_id}, type='{self.feature_type}')>"


# ============================================
# SANCTIONS PROGRAMS
# ============================================

class SanctionsProgram(Base, TimestampMixin):
    """
    Master table for sanctions programs.
    
    Examples: SDGT (Specially Designated Global Terrorists), 
    SDNTK (Specially Designated Narcotics Traffickers Kingpin Act), etc.
    """
    __tablename__ = "sanctions_programs"
    
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), 
        primary_key=True, 
        default=uuid.uuid4
    )
    
    # Program code (SDGT, SDNTK, etc.)
    code: Mapped[str] = mapped_column(String(50), nullable=False, unique=True)
    
    # Full name
    name: Mapped[str] = mapped_column(String(500), nullable=False)
    
    # Description
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    # Source authority (OFAC, UN, EU, etc.)
    authority: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    
    # Is this program currently active?
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    
    # Relationships
    entities: Mapped[List["EntityProgram"]] = relationship(
        "EntityProgram",
        back_populates="program",
        lazy="dynamic"
    )
    
    def __repr__(self) -> str:
        return f"<SanctionsProgram(code='{self.code}', name='{self.name}')>"


class EntityProgram(Base, TimestampMixin):
    """
    Junction table linking entities to sanctions programs.
    
    Many-to-many relationship with additional metadata about the listing.
    """
    __tablename__ = "entity_programs"
    
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), 
        primary_key=True, 
        default=uuid.uuid4
    )
    entity_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("sanctioned_entities.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    program_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("sanctions_programs.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    
    # When entity was added to this program
    listed_date: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True
    )
    
    # Reason for listing
    listing_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    # Is currently active under this program?
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    
    # Relationships
    entity: Mapped["SanctionedEntity"] = relationship(
        "SanctionedEntity",
        back_populates="programs"
    )
    program: Mapped["SanctionsProgram"] = relationship(
        "SanctionsProgram",
        back_populates="entities"
    )
    
    __table_args__ = (
        UniqueConstraint('entity_id', 'program_id', name='uq_entity_program'),
    )
    
    def __repr__(self) -> str:
        return f"<EntityProgram(entity_id={self.entity_id}, program_id={self.program_id})>"


# ============================================
# SCREENING MODELS
# ============================================

class ScreeningRequest(Base, TimestampMixin):
    """
    Log of all screening requests made to the system.
    
    Captures input data, request metadata, and links to results.
    """
    __tablename__ = "screening_requests"
    
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), 
        primary_key=True, 
        default=uuid.uuid4
    )
    
    # Request type (single, bulk)
    request_type: Mapped[str] = mapped_column(String(20), nullable=False, default="single")
    
    # Status
    status: Mapped[ScreeningStatus] = mapped_column(
        Enum(ScreeningStatus),
        nullable=False,
        default=ScreeningStatus.PENDING,
        index=True
    )
    
    # Input data (stored as JSON for flexibility)
    input_data: Mapped[dict] = mapped_column(JSONB, nullable=False)
    
    # Primary name being screened (denormalized for quick search)
    screened_name: Mapped[Optional[str]] = mapped_column(String(500), nullable=True, index=True)
    
    # Document number if provided
    screened_document: Mapped[Optional[str]] = mapped_column(String(100), nullable=True, index=True)
    
    # Analyst information
    analyst_name: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    analyst_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True, index=True)
    
    # API metadata
    api_key_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True, index=True)
    ip_address: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    user_agent: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    
    # Processing metrics
    processing_start: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    processing_end: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    processing_time_ms: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    
    # Error information (if failed)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    error_code: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    
    # Algorithm version used
    algorithm_version: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    
    # Thresholds used for this screening
    thresholds_used: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    
    # Relationships
    results: Mapped[List["ScreeningResult"]] = relationship(
        "ScreeningResult",
        back_populates="request",
        cascade="all, delete-orphan",
        lazy="selectin"
    )
    
    __table_args__ = (
        Index('ix_screening_request_date', 'created_at'),
        Index('ix_screening_request_status_date', 'status', 'created_at'),
        Index('ix_screening_request_analyst', 'analyst_id', 'created_at'),
    )
    
    def __repr__(self) -> str:
        return f"<ScreeningRequest(id={self.id}, name='{self.screened_name}', status={self.status})>"


class ScreeningResult(Base, TimestampMixin):
    """
    Results from a screening request.
    
    One request can have one result (for single screening) or many (for bulk).
    """
    __tablename__ = "screening_results"
    
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), 
        primary_key=True, 
        default=uuid.uuid4
    )
    request_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("screening_requests.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    
    # Input name for this specific result (in bulk screening)
    input_name: Mapped[str] = mapped_column(String(500), nullable=False)
    input_document: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    input_country: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    
    # Result summary
    is_hit: Mapped[bool] = mapped_column(Boolean, nullable=False, index=True)
    hit_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    
    # Highest confidence score among matches
    max_confidence: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    
    # Final recommendation
    recommendation: Mapped[Optional[RecommendationType]] = mapped_column(
        Enum(RecommendationType),
        nullable=True
    )
    
    # Flags from screening
    flags: Mapped[Optional[list]] = mapped_column(ARRAY(String), nullable=True)
    
    # Relationships
    request: Mapped["ScreeningRequest"] = relationship(
        "ScreeningRequest",
        back_populates="results"
    )
    matches: Mapped[List["ScreeningMatch"]] = relationship(
        "ScreeningMatch",
        back_populates="result",
        cascade="all, delete-orphan",
        lazy="selectin"
    )
    
    __table_args__ = (
        Index('ix_screening_result_hit', 'is_hit', 'created_at'),
        Index('ix_screening_result_confidence', 'max_confidence'),
    )
    
    def __repr__(self) -> str:
        return f"<ScreeningResult(id={self.id}, is_hit={self.is_hit}, count={self.hit_count})>"


class ScreeningMatch(Base, TimestampMixin):
    """
    Individual matches found during screening.
    
    Links a screening result to a matched sanctioned entity with confidence details.
    """
    __tablename__ = "screening_matches"
    
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), 
        primary_key=True, 
        default=uuid.uuid4
    )
    result_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("screening_results.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    entity_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("sanctioned_entities.id", ondelete="SET NULL"),
        nullable=True,
        index=True
    )
    
    # Match details
    matched_name: Mapped[str] = mapped_column(String(500), nullable=False)
    matched_document: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    
    # Match layer (1=exact, 2=high, 3=moderate, 4=low)
    match_layer: Mapped[int] = mapped_column(Integer, nullable=False)
    
    # Confidence scores
    overall_confidence: Mapped[float] = mapped_column(Float, nullable=False)
    name_confidence: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    document_confidence: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    dob_confidence: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    nationality_confidence: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    address_confidence: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    
    # Quality flags
    flags: Mapped[Optional[list]] = mapped_column(ARRAY(String), nullable=True)
    
    # Recommendation for this match
    recommendation: Mapped[RecommendationType] = mapped_column(
        Enum(RecommendationType),
        nullable=False
    )
    
    # Snapshot of entity data at match time (for audit trail)
    entity_snapshot: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    
    # Relationships
    result: Mapped["ScreeningResult"] = relationship(
        "ScreeningResult",
        back_populates="matches"
    )
    matched_entity: Mapped[Optional["SanctionedEntity"]] = relationship(
        "SanctionedEntity",
        back_populates="matches"
    )
    
    __table_args__ = (
        Index('ix_match_confidence', 'overall_confidence'),
        Index('ix_match_layer', 'match_layer'),
        CheckConstraint('overall_confidence >= 0 AND overall_confidence <= 100', name='ck_confidence_range'),
        CheckConstraint('match_layer >= 1 AND match_layer <= 4', name='ck_layer_range'),
    )
    
    def __repr__(self) -> str:
        return f"<ScreeningMatch(id={self.id}, name='{self.matched_name}', confidence={self.overall_confidence})>"


# ============================================
# AUDIT AND SYSTEM MODELS
# ============================================

class AuditLog(Base):
    """
    System-wide audit trail.
    
    Logs all significant actions for compliance and debugging.
    Immutable - no updates or deletes allowed.
    """
    __tablename__ = "audit_logs"
    
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), 
        primary_key=True, 
        default=uuid.uuid4
    )
    
    # Timestamp (no updated_at - audit logs are immutable)
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        index=True
    )
    
    # Action type
    action: Mapped[AuditAction] = mapped_column(
        Enum(AuditAction),
        nullable=False,
        index=True
    )
    
    # Resource being acted upon
    resource_type: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    resource_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    
    # Actor information
    actor_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True, index=True)
    actor_name: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    actor_ip: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    
    # Action details
    details: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    
    # Before/after state for updates
    old_value: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    new_value: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    
    # Result
    success: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    __table_args__ = (
        Index('ix_audit_timestamp_action', 'timestamp', 'action'),
        Index('ix_audit_resource', 'resource_type', 'resource_id'),
        Index('ix_audit_actor', 'actor_id', 'timestamp'),
    )
    
    def __repr__(self) -> str:
        return f"<AuditLog(id={self.id}, action={self.action}, resource='{self.resource_type}')>"


class DataSource(Base, TimestampMixin):
    """
    Configuration for data sources.
    
    Stores URLs, authentication, and settings for each data source.
    """
    __tablename__ = "data_sources"
    
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), 
        primary_key=True, 
        default=uuid.uuid4
    )
    
    # Source identifier
    code: Mapped[str] = mapped_column(String(20), nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    
    # Source type
    source_type: Mapped[DataSourceType] = mapped_column(
        Enum(DataSourceType),
        nullable=False
    )
    
    # URL configuration
    download_url: Mapped[str] = mapped_column(String(1000), nullable=False)
    
    # File format
    file_format: Mapped[str] = mapped_column(String(20), nullable=False, default="xml")
    
    # Is this source active?
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    
    # Update schedule (cron expression or days)
    update_frequency_days: Mapped[int] = mapped_column(Integer, default=7, nullable=False)
    
    # Last update information
    last_update: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    last_update_status: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    last_entity_count: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    
    # Validation settings
    validate_xsd: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    xsd_url: Mapped[Optional[str]] = mapped_column(String(1000), nullable=True)
    
    # Hash verification
    expected_hash: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    
    # Relationships
    updates: Mapped[List["DataUpdate"]] = relationship(
        "DataUpdate",
        back_populates="source",
        lazy="dynamic"
    )
    
    def __repr__(self) -> str:
        return f"<DataSource(code='{self.code}', name='{self.name}')>"


class DataUpdate(Base, TimestampMixin):
    """
    Log of data refresh operations.
    
    Tracks each time sanctions data is downloaded and processed.
    """
    __tablename__ = "data_updates"
    
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), 
        primary_key=True, 
        default=uuid.uuid4
    )
    source_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("data_sources.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    
    # Update timing
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False
    )
    completed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True
    )
    
    # Status
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="in_progress")
    
    # Statistics
    entities_added: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    entities_updated: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    entities_removed: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_entities: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    
    # Validation results
    validation_errors: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    validation_warnings: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    validation_details: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    
    # File information
    file_hash: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    file_size_bytes: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    
    # Error information
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    # Relationship
    source: Mapped["DataSource"] = relationship(
        "DataSource",
        back_populates="updates"
    )
    
    __table_args__ = (
        Index('ix_data_update_source_date', 'source_id', 'started_at'),
        Index('ix_data_update_status', 'status'),
    )
    
    def __repr__(self) -> str:
        return f"<DataUpdate(id={self.id}, source_id={self.source_id}, status='{self.status}')>"


# ============================================
# HELPER FUNCTIONS
# ============================================

def normalize_name(name: str) -> str:
    """
    Normalize a name for consistent storage and searching.
    
    Removes accents, converts to uppercase, normalizes whitespace.
    
    Args:
        name: The name to normalize (can be None)
        
    Returns:
        Normalized name string, or empty string if name is None/empty
    """
    import unicodedata
    import re
    
    # Explicitly handle None input
    if name is None:
        return ""
    
    if not name:
        return ""
    
    # Normalize Unicode (decompose accents)
    normalized = unicodedata.normalize('NFD', name)
    # Remove accent marks
    normalized = ''.join(c for c in normalized if unicodedata.category(c) != 'Mn')
    # Remove special characters except spaces
    normalized = re.sub(r'[^\w\s]', ' ', normalized)
    # Normalize whitespace
    normalized = re.sub(r'\s+', ' ', normalized)
    # Convert to uppercase
    return normalized.upper().strip()


def normalize_document(doc_number: str) -> str:
    """
    Normalize a document number for consistent storage and searching.
    
    Removes spaces, dashes, dots, and converts to uppercase.
    
    Args:
        doc_number: The document number to normalize (can be None)
        
    Returns:
        Normalized document number string, or empty string if doc_number is None/empty
    """
    import re
    
    # Explicitly handle None input
    if doc_number is None:
        return ""
    
    if not doc_number:
        return ""
    
    # Remove common separators
    normalized = re.sub(r'[\s\-\.\,\/]', '', doc_number)
    return normalized.upper()
