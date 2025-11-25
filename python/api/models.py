"""
Pydantic request/response schemas for FastAPI Sanctions Screening API

Transforms existing types from screener.py to Pydantic models for API validation.
"""

from typing import List, Optional, Dict, Any

from pydantic import BaseModel, Field, field_validator


class ScreeningRequest(BaseModel):
    """Request schema for individual screening.
    
    Validation matches input_validation config from config.yaml.
    """
    name: str = Field(
        ...,
        min_length=2,
        max_length=200,
        description="Name to screen (minimum 2 characters)"
    )
    document_number: Optional[str] = Field(
        default=None,
        max_length=50,
        description="Document number (passport, ID, etc.)"
    )
    document_type: Optional[str] = Field(
        default=None,
        description="Type of document (e.g., 'Passport', 'National ID')"
    )
    date_of_birth: Optional[str] = Field(
        default=None,
        description="Date of birth in ISO 8601 format (YYYY, YYYY-MM, or YYYY-MM-DD)"
    )
    nationality: Optional[str] = Field(
        default=None,
        description="Nationality"
    )
    country: Optional[str] = Field(
        default=None,
        description="Country of residence"
    )
    analyst: Optional[str] = Field(
        default=None,
        description="Analyst name for audit trail"
    )
    
    @field_validator('date_of_birth')
    @classmethod
    def validate_dob_format(cls, v: Optional[str]) -> Optional[str]:
        """Validate DOB is in ISO 8601 format."""
        if v is None:
            return v
        import re
        if not re.match(r'^\d{4}(-\d{2}(-\d{2})?)?$', v):
            raise ValueError(
                "DOB must be in ISO 8601 format: YYYY, YYYY-MM, or YYYY-MM-DD"
            )
        return v


class ConfidenceBreakdownResponse(BaseModel):
    """Confidence score breakdown per matching dimension."""
    overall: float = Field(..., description="Overall confidence score (0-100)")
    name: float = Field(default=0.0, description="Name match score (0-100)")
    document: float = Field(default=0.0, description="Document match score (0-100)")
    dob: float = Field(default=0.0, description="DOB match score (0-100)")
    nationality: float = Field(default=0.0, description="Nationality score (0-100)")
    address: float = Field(default=0.0, description="Address match score (0-100)")


class EntityDetail(BaseModel):
    """Sanctioned entity details."""
    id: str = Field(..., description="Entity ID")
    source: str = Field(..., description="Source list (OFAC, UN)")
    type: str = Field(..., description="Entity type (individual, entity, vessel)")
    name: str = Field(..., description="Primary name")
    all_names: List[str] = Field(default_factory=list, description="All known names/aliases")
    aliases: List[str] = Field(default_factory=list, description="Known aliases")
    first_name: Optional[str] = Field(default=None, alias="firstName")
    last_name: Optional[str] = Field(default=None, alias="lastName")
    countries: List[str] = Field(default_factory=list, description="Associated countries")
    identity_documents: List[Dict[str, Any]] = Field(
        default_factory=list, 
        description="Identity documents"
    )
    program: Optional[str] = Field(default=None, description="Sanctions program")
    date_of_birth: Optional[str] = Field(default=None, alias="dateOfBirth")
    nationality: Optional[str] = Field(default=None)
    
    model_config = {"populate_by_name": True}


class MatchDetail(BaseModel):
    """Individual match result from screening.
    
    Transforms screener.py:MatchResult.to_dict() output.
    """
    entity: EntityDetail = Field(..., description="Matched entity details")
    confidence: ConfidenceBreakdownResponse = Field(..., description="Confidence scores")
    flags: List[str] = Field(default_factory=list, description="Quality flags")
    recommendation: str = Field(
        ..., 
        description="Recommendation: AUTO_ESCALATE, MANUAL_REVIEW, LOW_CONFIDENCE_REVIEW, AUTO_CLEAR"
    )
    match_layer: int = Field(
        ..., 
        ge=1, 
        le=4, 
        description="Match layer (1=exact, 2=high, 3=moderate, 4=low)"
    )
    matched_name: str = Field(..., description="Name that matched the query")
    matched_document: Optional[str] = Field(
        default=None, 
        description="Document number that matched (if any)"
    )


class ScreeningResponse(BaseModel):
    """Response schema for individual screening."""
    screening_id: str = Field(..., description="Unique screening identifier (UUID)")
    screening_date: str = Field(..., description="Screening timestamp (ISO 8601)")
    is_hit: bool = Field(..., description="Whether any matches were found")
    hit_count: int = Field(..., ge=0, description="Number of matches found")
    matches: List[MatchDetail] = Field(default_factory=list, description="Match details")
    processing_time_ms: int = Field(..., ge=0, description="Processing time in milliseconds")
    algorithm_version: str = Field(..., description="Algorithm version used")


class BulkScreeningItem(BaseModel):
    """Single item result in bulk screening response."""
    screening_id: str
    input: Dict[str, Any]
    is_hit: bool
    hit_count: int
    matches: List[MatchDetail]


class BulkScreeningResponse(BaseModel):
    """Response schema for bulk CSV screening."""
    screening_id: str = Field(..., description="Bulk screening job identifier")
    total_processed: int = Field(..., ge=0, description="Total records processed")
    hits: int = Field(..., ge=0, description="Number of records with matches")
    hit_rate: str = Field(..., description="Hit rate as percentage string")
    results: List[BulkScreeningItem] = Field(
        default_factory=list, 
        description="Individual screening results"
    )
    processing_time_ms: int = Field(..., ge=0, description="Total processing time in milliseconds")


class DataFileInfo(BaseModel):
    """Information about a data file."""
    filename: str
    last_modified: Optional[str] = None
    size_bytes: Optional[int] = None


class HealthResponse(BaseModel):
    """Response schema for health check endpoint."""
    status: str = Field(default="healthy", description="Service status")
    entities_loaded: int = Field(..., ge=0, description="Number of entities loaded")
    data_files: List[DataFileInfo] = Field(
        default_factory=list, 
        description="Data file information"
    )
    data_age_days: Optional[int] = Field(
        default=None, 
        description="Age of data in days (based on oldest file)"
    )
    algorithm_version: str = Field(..., description="Algorithm version")
    memory_usage_mb: Optional[float] = Field(
        default=None, 
        description="Current memory usage in MB"
    )
    uptime_seconds: Optional[int] = Field(
        default=None, 
        description="Server uptime in seconds"
    )


class DataUpdateResponse(BaseModel):
    """Response schema for data update endpoint."""
    success: bool = Field(..., description="Whether update succeeded")
    ofac_entities: int = Field(default=0, description="OFAC entities loaded")
    un_entities: int = Field(default=0, description="UN entities loaded")
    total_entities: int = Field(..., ge=0, description="Total entities after update")
    validation_errors: List[str] = Field(
        default_factory=list, 
        description="Validation errors encountered"
    )
    validation_warnings: List[str] = Field(
        default_factory=list, 
        description="Validation warnings"
    )
    processing_time_ms: int = Field(..., ge=0, description="Processing time in milliseconds")


class ErrorDetail(BaseModel):
    """Detailed error information."""
    code: str = Field(..., description="Error code for programmatic handling")
    message: str = Field(..., description="Human-readable error message")
    field: Optional[str] = Field(default=None, description="Field that caused error")
    suggestion: Optional[str] = Field(default=None, description="How to fix the error")
    timestamp: str = Field(..., description="Error timestamp (ISO 8601)")


class ErrorResponse(BaseModel):
    """Standardized error response format."""
    error: ErrorDetail
