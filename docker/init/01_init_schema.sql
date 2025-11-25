-- ============================================
-- SDNCheck Database Schema Initialization
-- Version: 1.0.0
-- 
-- This script creates the complete database schema
-- for the SDNCheck Sanctions Screening System.
-- 
-- Run this script on a fresh PostgreSQL database
-- or use with docker-compose init scripts.
-- ============================================

-- Enable required extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pg_trgm";  -- For fuzzy text search

-- ============================================
-- ENUM TYPES
-- ============================================

-- Entity type enum
DO $$ BEGIN
    CREATE TYPE entity_type AS ENUM (
        'individual',
        'entity',
        'vessel',
        'aircraft'
    );
EXCEPTION
    WHEN duplicate_object THEN null;
END $$;

-- Data source type enum
DO $$ BEGIN
    CREATE TYPE data_source_type AS ENUM (
        'OFAC',
        'UN',
        'EU',
        'UK',
        'OTHER'
    );
EXCEPTION
    WHEN duplicate_object THEN null;
END $$;

-- Screening status enum
DO $$ BEGIN
    CREATE TYPE screening_status AS ENUM (
        'pending',
        'processing',
        'completed',
        'failed'
    );
EXCEPTION
    WHEN duplicate_object THEN null;
END $$;

-- Recommendation type enum
DO $$ BEGIN
    CREATE TYPE recommendation_type AS ENUM (
        'AUTO_ESCALATE',
        'MANUAL_REVIEW',
        'LOW_CONFIDENCE_REVIEW',
        'AUTO_CLEAR'
    );
EXCEPTION
    WHEN duplicate_object THEN null;
END $$;

-- Audit action enum
DO $$ BEGIN
    CREATE TYPE audit_action AS ENUM (
        'CREATE',
        'READ',
        'UPDATE',
        'DELETE',
        'SCREEN',
        'BULK_SCREEN',
        'DATA_UPDATE',
        'LOGIN',
        'LOGOUT',
        'CONFIG_CHANGE'
    );
EXCEPTION
    WHEN duplicate_object THEN null;
END $$;


-- ============================================
-- CORE ENTITY TABLES
-- ============================================

-- Sanctioned entities (main table)
CREATE TABLE IF NOT EXISTS sanctioned_entities (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    external_id VARCHAR(100) NOT NULL,
    source data_source_type NOT NULL,
    entity_type entity_type NOT NULL,
    
    -- Names
    primary_name VARCHAR(500) NOT NULL,
    normalized_name VARCHAR(500) NOT NULL,
    first_name VARCHAR(200),
    last_name VARCHAR(200),
    middle_name VARCHAR(200),
    
    -- Biographical data
    date_of_birth VARCHAR(50),
    place_of_birth VARCHAR(200),
    nationality VARCHAR(100),
    citizenship VARCHAR(100),
    gender VARCHAR(20),
    title VARCHAR(200),
    
    -- Vessel-specific fields
    vessel_type VARCHAR(100),
    vessel_flag VARCHAR(100),
    vessel_tonnage VARCHAR(50),
    vessel_imo VARCHAR(50),
    vessel_mmsi VARCHAR(50),
    vessel_call_sign VARCHAR(50),
    
    -- Raw data storage
    raw_data JSONB,
    
    -- Full-text search
    search_vector TSVECTOR,
    
    -- Soft delete
    is_deleted BOOLEAN NOT NULL DEFAULT FALSE,
    deleted_at TIMESTAMP WITH TIME ZONE,
    
    -- Versioning
    version INTEGER NOT NULL DEFAULT 1,
    
    -- Timestamps
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    
    -- Constraints
    CONSTRAINT uq_entity_external_source UNIQUE (external_id, source)
);

-- Entity aliases
CREATE TABLE IF NOT EXISTS entity_aliases (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    entity_id UUID NOT NULL REFERENCES sanctioned_entities(id) ON DELETE CASCADE,
    
    alias_name VARCHAR(500) NOT NULL,
    normalized_alias VARCHAR(500) NOT NULL,
    alias_type VARCHAR(50),
    alias_quality VARCHAR(20),
    language VARCHAR(50),
    is_primary BOOLEAN NOT NULL DEFAULT FALSE,
    
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);

-- Identity documents
CREATE TABLE IF NOT EXISTS identity_documents (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    entity_id UUID NOT NULL REFERENCES sanctioned_entities(id) ON DELETE CASCADE,
    
    document_type VARCHAR(100) NOT NULL,
    document_number VARCHAR(100) NOT NULL,
    normalized_number VARCHAR(100) NOT NULL,
    
    issuing_country VARCHAR(100),
    issuing_authority VARCHAR(200),
    issue_date VARCHAR(50),
    expiration_date VARCHAR(50),
    notes TEXT,
    
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);

-- Entity addresses
CREATE TABLE IF NOT EXISTS entity_addresses (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    entity_id UUID NOT NULL REFERENCES sanctioned_entities(id) ON DELETE CASCADE,
    
    address_line1 VARCHAR(500),
    address_line2 VARCHAR(500),
    city VARCHAR(200),
    state_province VARCHAR(200),
    postal_code VARCHAR(50),
    country VARCHAR(100),
    full_address TEXT,
    address_type VARCHAR(50),
    is_primary BOOLEAN NOT NULL DEFAULT FALSE,
    
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);

-- Entity features (key-value pairs)
CREATE TABLE IF NOT EXISTS entity_features (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    entity_id UUID NOT NULL REFERENCES sanctioned_entities(id) ON DELETE CASCADE,
    
    feature_type VARCHAR(100) NOT NULL,
    feature_value TEXT NOT NULL,
    normalized_value VARCHAR(500),
    
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);


-- ============================================
-- SANCTIONS PROGRAMS
-- ============================================

-- Sanctions programs master table
CREATE TABLE IF NOT EXISTS sanctions_programs (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    code VARCHAR(50) NOT NULL UNIQUE,
    name VARCHAR(500) NOT NULL,
    description TEXT,
    authority VARCHAR(100),
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);

-- Entity-program junction table
CREATE TABLE IF NOT EXISTS entity_programs (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    entity_id UUID NOT NULL REFERENCES sanctioned_entities(id) ON DELETE CASCADE,
    program_id UUID NOT NULL REFERENCES sanctions_programs(id) ON DELETE CASCADE,
    
    listed_date TIMESTAMP WITH TIME ZONE,
    listing_reason TEXT,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    
    CONSTRAINT uq_entity_program UNIQUE (entity_id, program_id)
);


-- ============================================
-- SCREENING TABLES
-- ============================================

-- Screening requests
CREATE TABLE IF NOT EXISTS screening_requests (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    request_type VARCHAR(20) NOT NULL DEFAULT 'single',
    status screening_status NOT NULL DEFAULT 'pending',
    
    input_data JSONB NOT NULL,
    screened_name VARCHAR(500),
    screened_document VARCHAR(100),
    
    analyst_name VARCHAR(200),
    analyst_id VARCHAR(100),
    api_key_id VARCHAR(100),
    ip_address VARCHAR(50),
    user_agent VARCHAR(500),
    
    processing_start TIMESTAMP WITH TIME ZONE,
    processing_end TIMESTAMP WITH TIME ZONE,
    processing_time_ms INTEGER,
    
    error_message TEXT,
    error_code VARCHAR(50),
    
    algorithm_version VARCHAR(20),
    thresholds_used JSONB,
    
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);

-- Screening results
CREATE TABLE IF NOT EXISTS screening_results (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    request_id UUID NOT NULL REFERENCES screening_requests(id) ON DELETE CASCADE,
    
    input_name VARCHAR(500) NOT NULL,
    input_document VARCHAR(100),
    input_country VARCHAR(100),
    
    is_hit BOOLEAN NOT NULL,
    hit_count INTEGER NOT NULL DEFAULT 0,
    max_confidence FLOAT,
    recommendation recommendation_type,
    flags VARCHAR(100)[],
    
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);

-- Screening matches
CREATE TABLE IF NOT EXISTS screening_matches (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    result_id UUID NOT NULL REFERENCES screening_results(id) ON DELETE CASCADE,
    entity_id UUID REFERENCES sanctioned_entities(id) ON DELETE SET NULL,
    
    matched_name VARCHAR(500) NOT NULL,
    matched_document VARCHAR(100),
    match_layer INTEGER NOT NULL CHECK (match_layer >= 1 AND match_layer <= 4),
    
    overall_confidence FLOAT NOT NULL CHECK (overall_confidence >= 0 AND overall_confidence <= 100),
    name_confidence FLOAT NOT NULL DEFAULT 0.0,
    document_confidence FLOAT NOT NULL DEFAULT 0.0,
    dob_confidence FLOAT NOT NULL DEFAULT 0.0,
    nationality_confidence FLOAT NOT NULL DEFAULT 0.0,
    address_confidence FLOAT NOT NULL DEFAULT 0.0,
    
    flags VARCHAR(100)[],
    recommendation recommendation_type NOT NULL,
    entity_snapshot JSONB,
    
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);


-- ============================================
-- AUDIT AND SYSTEM TABLES
-- ============================================

-- Audit logs (immutable)
CREATE TABLE IF NOT EXISTS audit_logs (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    timestamp TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    
    action audit_action NOT NULL,
    resource_type VARCHAR(100) NOT NULL,
    resource_id VARCHAR(100),
    
    actor_id VARCHAR(100),
    actor_name VARCHAR(200),
    actor_ip VARCHAR(50),
    
    details JSONB,
    old_value JSONB,
    new_value JSONB,
    
    success BOOLEAN NOT NULL DEFAULT TRUE,
    error_message TEXT
);

-- Data sources configuration
CREATE TABLE IF NOT EXISTS data_sources (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    code VARCHAR(20) NOT NULL UNIQUE,
    name VARCHAR(200) NOT NULL,
    source_type data_source_type NOT NULL,
    
    download_url VARCHAR(1000) NOT NULL,
    file_format VARCHAR(20) NOT NULL DEFAULT 'xml',
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    update_frequency_days INTEGER NOT NULL DEFAULT 7,
    
    last_update TIMESTAMP WITH TIME ZONE,
    last_update_status VARCHAR(50),
    last_entity_count INTEGER,
    
    validate_xsd BOOLEAN NOT NULL DEFAULT TRUE,
    xsd_url VARCHAR(1000),
    expected_hash VARCHAR(128),
    
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);

-- Data update history
CREATE TABLE IF NOT EXISTS data_updates (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    source_id UUID NOT NULL REFERENCES data_sources(id) ON DELETE CASCADE,
    
    started_at TIMESTAMP WITH TIME ZONE NOT NULL,
    completed_at TIMESTAMP WITH TIME ZONE,
    status VARCHAR(50) NOT NULL DEFAULT 'in_progress',
    
    entities_added INTEGER NOT NULL DEFAULT 0,
    entities_updated INTEGER NOT NULL DEFAULT 0,
    entities_removed INTEGER NOT NULL DEFAULT 0,
    total_entities INTEGER NOT NULL DEFAULT 0,
    
    validation_errors INTEGER NOT NULL DEFAULT 0,
    validation_warnings INTEGER NOT NULL DEFAULT 0,
    validation_details JSONB,
    
    file_hash VARCHAR(128),
    file_size_bytes INTEGER,
    error_message TEXT,
    
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);


-- ============================================
-- INDEXES
-- ============================================

-- Sanctioned entities indexes
CREATE INDEX IF NOT EXISTS ix_entity_external_id ON sanctioned_entities(external_id);
CREATE INDEX IF NOT EXISTS ix_entity_source ON sanctioned_entities(source);
CREATE INDEX IF NOT EXISTS ix_entity_type ON sanctioned_entities(entity_type);
CREATE INDEX IF NOT EXISTS ix_entity_primary_name ON sanctioned_entities(primary_name);
CREATE INDEX IF NOT EXISTS ix_entity_normalized_name ON sanctioned_entities(normalized_name);
CREATE INDEX IF NOT EXISTS ix_entity_nationality ON sanctioned_entities(nationality);
CREATE INDEX IF NOT EXISTS ix_entity_vessel_imo ON sanctioned_entities(vessel_imo) WHERE vessel_imo IS NOT NULL;
CREATE INDEX IF NOT EXISTS ix_entity_is_deleted ON sanctioned_entities(is_deleted);
CREATE INDEX IF NOT EXISTS ix_entity_source_type ON sanctioned_entities(source, entity_type);
CREATE INDEX IF NOT EXISTS ix_entity_name_source ON sanctioned_entities(normalized_name, source);
CREATE INDEX IF NOT EXISTS ix_entity_search_vector ON sanctioned_entities USING GIN(search_vector);
CREATE INDEX IF NOT EXISTS ix_entity_active ON sanctioned_entities(id) WHERE is_deleted = FALSE;

-- Trigram index for fuzzy name search
CREATE INDEX IF NOT EXISTS ix_entity_name_trgm ON sanctioned_entities USING GIN(normalized_name gin_trgm_ops);

-- Alias indexes
CREATE INDEX IF NOT EXISTS ix_alias_entity_id ON entity_aliases(entity_id);
CREATE INDEX IF NOT EXISTS ix_alias_normalized ON entity_aliases(normalized_alias);
CREATE INDEX IF NOT EXISTS ix_alias_entity_primary ON entity_aliases(entity_id, is_primary);
CREATE INDEX IF NOT EXISTS ix_alias_name_trgm ON entity_aliases USING GIN(normalized_alias gin_trgm_ops);

-- Document indexes
CREATE INDEX IF NOT EXISTS ix_document_entity_id ON identity_documents(entity_id);
CREATE INDEX IF NOT EXISTS ix_document_type ON identity_documents(document_type);
CREATE INDEX IF NOT EXISTS ix_document_normalized_number ON identity_documents(normalized_number);
CREATE INDEX IF NOT EXISTS ix_document_number_type ON identity_documents(normalized_number, document_type);
CREATE INDEX IF NOT EXISTS ix_document_country ON identity_documents(issuing_country);

-- Address indexes
CREATE INDEX IF NOT EXISTS ix_address_entity_id ON entity_addresses(entity_id);
CREATE INDEX IF NOT EXISTS ix_address_country ON entity_addresses(country);
CREATE INDEX IF NOT EXISTS ix_address_city ON entity_addresses(city);
CREATE INDEX IF NOT EXISTS ix_address_country_city ON entity_addresses(country, city);

-- Feature indexes
CREATE INDEX IF NOT EXISTS ix_feature_entity_id ON entity_features(entity_id);
CREATE INDEX IF NOT EXISTS ix_feature_type ON entity_features(feature_type);
CREATE INDEX IF NOT EXISTS ix_feature_type_value ON entity_features(feature_type, normalized_value);

-- Screening indexes
CREATE INDEX IF NOT EXISTS ix_screening_request_date ON screening_requests(created_at);
CREATE INDEX IF NOT EXISTS ix_screening_request_status ON screening_requests(status);
CREATE INDEX IF NOT EXISTS ix_screening_request_status_date ON screening_requests(status, created_at);
CREATE INDEX IF NOT EXISTS ix_screening_request_analyst ON screening_requests(analyst_id, created_at);
CREATE INDEX IF NOT EXISTS ix_screening_request_name ON screening_requests(screened_name);
CREATE INDEX IF NOT EXISTS ix_screening_request_document ON screening_requests(screened_document);

CREATE INDEX IF NOT EXISTS ix_screening_result_request_id ON screening_results(request_id);
CREATE INDEX IF NOT EXISTS ix_screening_result_hit ON screening_results(is_hit, created_at);
CREATE INDEX IF NOT EXISTS ix_screening_result_confidence ON screening_results(max_confidence);

CREATE INDEX IF NOT EXISTS ix_screening_match_result_id ON screening_matches(result_id);
CREATE INDEX IF NOT EXISTS ix_screening_match_entity_id ON screening_matches(entity_id);
CREATE INDEX IF NOT EXISTS ix_screening_match_confidence ON screening_matches(overall_confidence);
CREATE INDEX IF NOT EXISTS ix_screening_match_layer ON screening_matches(match_layer);

-- Audit indexes
CREATE INDEX IF NOT EXISTS ix_audit_timestamp ON audit_logs(timestamp);
CREATE INDEX IF NOT EXISTS ix_audit_action ON audit_logs(action);
CREATE INDEX IF NOT EXISTS ix_audit_timestamp_action ON audit_logs(timestamp, action);
CREATE INDEX IF NOT EXISTS ix_audit_resource ON audit_logs(resource_type, resource_id);
CREATE INDEX IF NOT EXISTS ix_audit_actor ON audit_logs(actor_id, timestamp);

-- Data source indexes
CREATE INDEX IF NOT EXISTS ix_data_update_source_id ON data_updates(source_id);
CREATE INDEX IF NOT EXISTS ix_data_update_source_date ON data_updates(source_id, started_at);
CREATE INDEX IF NOT EXISTS ix_data_update_status ON data_updates(status);


-- ============================================
-- FUNCTIONS AND TRIGGERS
-- ============================================

-- Function to update search vector
CREATE OR REPLACE FUNCTION update_entity_search_vector()
RETURNS TRIGGER AS $$
BEGIN
    NEW.search_vector := 
        setweight(to_tsvector('simple', COALESCE(NEW.primary_name, '')), 'A') ||
        setweight(to_tsvector('simple', COALESCE(NEW.normalized_name, '')), 'A') ||
        setweight(to_tsvector('simple', COALESCE(NEW.first_name, '')), 'B') ||
        setweight(to_tsvector('simple', COALESCE(NEW.last_name, '')), 'B') ||
        setweight(to_tsvector('simple', COALESCE(NEW.nationality, '')), 'C') ||
        setweight(to_tsvector('simple', COALESCE(NEW.date_of_birth, '')), 'D');
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Trigger to automatically update search vector
DROP TRIGGER IF EXISTS trg_update_entity_search_vector ON sanctioned_entities;
CREATE TRIGGER trg_update_entity_search_vector
    BEFORE INSERT OR UPDATE ON sanctioned_entities
    FOR EACH ROW
    EXECUTE FUNCTION update_entity_search_vector();

-- Function to update updated_at timestamp
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Apply updated_at trigger to all tables
DO $$
DECLARE
    t text;
BEGIN
    FOR t IN 
        SELECT table_name 
        FROM information_schema.columns 
        WHERE column_name = 'updated_at' 
        AND table_schema = 'public'
    LOOP
        EXECUTE format('
            DROP TRIGGER IF EXISTS trg_update_%I_updated_at ON %I;
            CREATE TRIGGER trg_update_%I_updated_at
                BEFORE UPDATE ON %I
                FOR EACH ROW
                EXECUTE FUNCTION update_updated_at_column();
        ', t, t, t, t);
    END LOOP;
END;
$$;


-- ============================================
-- INITIAL DATA
-- ============================================

-- Insert default data sources
INSERT INTO data_sources (code, name, source_type, download_url, file_format, is_active)
VALUES 
    ('OFAC', 'OFAC SDN Enhanced', 'OFAC', 
     'https://sanctionslistservice.ofac.treas.gov/api/PublicationPreview/exports/SDN_ENHANCED.ZIP',
     'xml', TRUE),
    ('UN', 'UN Consolidated List', 'UN',
     'https://scsanctions.un.org/resources/xml/en/consolidated.xml',
     'xml', TRUE)
ON CONFLICT (code) DO NOTHING;

-- Insert common sanctions programs
INSERT INTO sanctions_programs (code, name, description, authority, is_active)
VALUES 
    ('SDGT', 'Specially Designated Global Terrorist', 
     'Individuals and entities associated with terrorism', 'OFAC', TRUE),
    ('SDNTK', 'Specially Designated Narcotics Trafficker Kingpin Act',
     'Foreign persons engaged in narcotics trafficking', 'OFAC', TRUE),
    ('SDN', 'Specially Designated Nationals',
     'OFAC SDN list entities', 'OFAC', TRUE),
    ('FSE', 'Foreign Sanctions Evaders',
     'Foreign persons involved in sanctions evasion', 'OFAC', TRUE),
    ('SSI', 'Sectoral Sanctions Identifications',
     'Russian sectoral sanctions', 'OFAC', TRUE),
    ('UN-ISIL', 'UN Security Council - ISIL/Al-Qaida Sanctions',
     'UN ISIL/Al-Qaida sanctions regime', 'UN', TRUE),
    ('UN-1718', 'UN Security Council Resolution 1718',
     'UN DPRK sanctions regime', 'UN', TRUE),
    ('UN-CONSOLIDATED', 'UN Consolidated List',
     'UN consolidated sanctions list', 'UN', TRUE)
ON CONFLICT (code) DO NOTHING;


-- ============================================
-- GRANTS (for application user)
-- ============================================

-- Create application role if needed (uncomment and modify as needed)
-- DO $$
-- BEGIN
--     IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = 'sdn_app') THEN
--         CREATE ROLE sdn_app WITH LOGIN PASSWORD 'app_password';
--     END IF;
-- END
-- $$;

-- Grant permissions (uncomment and modify as needed)
-- GRANT USAGE ON SCHEMA public TO sdn_app;
-- GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO sdn_app;
-- GRANT USAGE ON ALL SEQUENCES IN SCHEMA public TO sdn_app;


-- ============================================
-- COMPLETION MESSAGE
-- ============================================

DO $$
BEGIN
    RAISE NOTICE 'SDNCheck database schema initialized successfully!';
    RAISE NOTICE 'Tables created: sanctioned_entities, entity_aliases, identity_documents, entity_addresses, entity_features, sanctions_programs, entity_programs, screening_requests, screening_results, screening_matches, audit_logs, data_sources, data_updates';
    RAISE NOTICE 'Default data sources: OFAC, UN';
    RAISE NOTICE 'Default sanctions programs: SDGT, SDNTK, SDN, FSE, SSI, UN-ISIL, UN-1718, UN-CONSOLIDATED';
END
$$;
