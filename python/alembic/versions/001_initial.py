"""Initial schema - Baseline migration

Revision ID: 001_initial
Revises: 
Create Date: 2024-12-01 00:00:00.000000

This is the baseline migration that creates all tables for the SDNCheck system.
It corresponds to the schema defined in docker/init/01_init_schema.sql.
For existing databases, use `alembic stamp 001_initial` to mark as applied.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '001_initial'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create initial database schema."""
    
    # Enable required extensions
    op.execute('CREATE EXTENSION IF NOT EXISTS "uuid-ossp"')
    op.execute('CREATE EXTENSION IF NOT EXISTS "pg_trgm"')
    
    # Create enums
    entity_type = postgresql.ENUM(
        'individual', 'entity', 'vessel', 'aircraft',
        name='entity_type', create_type=True
    )
    entity_type.create(op.get_bind(), checkfirst=True)
    
    data_source_type = postgresql.ENUM(
        'OFAC', 'UN', 'EU', 'UK', 'OTHER',
        name='data_source_type', create_type=True
    )
    data_source_type.create(op.get_bind(), checkfirst=True)
    
    screening_status = postgresql.ENUM(
        'pending', 'processing', 'completed', 'failed',
        name='screening_status', create_type=True
    )
    screening_status.create(op.get_bind(), checkfirst=True)
    
    recommendation_type = postgresql.ENUM(
        'AUTO_ESCALATE', 'MANUAL_REVIEW', 'LOW_CONFIDENCE_REVIEW', 'AUTO_CLEAR',
        name='recommendation_type', create_type=True
    )
    recommendation_type.create(op.get_bind(), checkfirst=True)
    
    audit_action = postgresql.ENUM(
        'CREATE', 'READ', 'UPDATE', 'DELETE', 'SCREEN', 'BULK_SCREEN',
        'DATA_UPDATE', 'LOGIN', 'LOGOUT', 'CONFIG_CHANGE',
        name='audit_action', create_type=True
    )
    audit_action.create(op.get_bind(), checkfirst=True)
    
    # Create sanctioned_entities table
    op.create_table(
        'sanctioned_entities',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, 
                  server_default=sa.text('uuid_generate_v4()')),
        sa.Column('external_id', sa.String(100), nullable=False),
        sa.Column('source', sa.Enum('OFAC', 'UN', 'EU', 'UK', 'OTHER', 
                                    name='data_source_type'), nullable=False),
        sa.Column('entity_type', sa.Enum('individual', 'entity', 'vessel', 'aircraft',
                                         name='entity_type'), nullable=False),
        sa.Column('primary_name', sa.String(500), nullable=False),
        sa.Column('normalized_name', sa.String(500), nullable=False),
        sa.Column('first_name', sa.String(200)),
        sa.Column('last_name', sa.String(200)),
        sa.Column('middle_name', sa.String(200)),
        sa.Column('date_of_birth', sa.String(50)),
        sa.Column('place_of_birth', sa.String(200)),
        sa.Column('nationality', sa.String(100)),
        sa.Column('citizenship', sa.String(100)),
        sa.Column('gender', sa.String(20)),
        sa.Column('title', sa.String(200)),
        sa.Column('vessel_type', sa.String(100)),
        sa.Column('vessel_flag', sa.String(100)),
        sa.Column('vessel_tonnage', sa.String(50)),
        sa.Column('vessel_imo', sa.String(50)),
        sa.Column('vessel_mmsi', sa.String(50)),
        sa.Column('vessel_call_sign', sa.String(50)),
        sa.Column('raw_data', postgresql.JSONB),
        sa.Column('search_vector', postgresql.TSVECTOR),
        sa.Column('is_deleted', sa.Boolean, nullable=False, server_default='false'),
        sa.Column('deleted_at', sa.DateTime(timezone=True)),
        sa.Column('version', sa.Integer, nullable=False, server_default='1'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text('NOW()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text('NOW()')),
        sa.UniqueConstraint('external_id', 'source', name='uq_entity_external_source')
    )
    
    # Create entity_aliases table
    op.create_table(
        'entity_aliases',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text('uuid_generate_v4()')),
        sa.Column('entity_id', postgresql.UUID(as_uuid=True), 
                  sa.ForeignKey('sanctioned_entities.id', ondelete='CASCADE'), nullable=False),
        sa.Column('alias_name', sa.String(500), nullable=False),
        sa.Column('normalized_alias', sa.String(500), nullable=False),
        sa.Column('alias_type', sa.String(50)),
        sa.Column('alias_quality', sa.String(20)),
        sa.Column('language', sa.String(50)),
        sa.Column('is_primary', sa.Boolean, nullable=False, server_default='false'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text('NOW()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text('NOW()'))
    )
    
    # Create identity_documents table
    op.create_table(
        'identity_documents',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text('uuid_generate_v4()')),
        sa.Column('entity_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('sanctioned_entities.id', ondelete='CASCADE'), nullable=False),
        sa.Column('document_type', sa.String(100), nullable=False),
        sa.Column('document_number', sa.String(100), nullable=False),
        sa.Column('normalized_number', sa.String(100), nullable=False),
        sa.Column('issuing_country', sa.String(100)),
        sa.Column('issuing_authority', sa.String(200)),
        sa.Column('issue_date', sa.String(50)),
        sa.Column('expiration_date', sa.String(50)),
        sa.Column('notes', sa.Text),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text('NOW()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text('NOW()'))
    )
    
    # Create entity_addresses table
    op.create_table(
        'entity_addresses',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text('uuid_generate_v4()')),
        sa.Column('entity_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('sanctioned_entities.id', ondelete='CASCADE'), nullable=False),
        sa.Column('address_line1', sa.String(500)),
        sa.Column('address_line2', sa.String(500)),
        sa.Column('city', sa.String(200)),
        sa.Column('state_province', sa.String(200)),
        sa.Column('postal_code', sa.String(50)),
        sa.Column('country', sa.String(100)),
        sa.Column('full_address', sa.Text),
        sa.Column('address_type', sa.String(50)),
        sa.Column('is_primary', sa.Boolean, nullable=False, server_default='false'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text('NOW()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text('NOW()'))
    )
    
    # Create entity_features table
    op.create_table(
        'entity_features',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text('uuid_generate_v4()')),
        sa.Column('entity_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('sanctioned_entities.id', ondelete='CASCADE'), nullable=False),
        sa.Column('feature_type', sa.String(100), nullable=False),
        sa.Column('feature_value', sa.Text, nullable=False),
        sa.Column('normalized_value', sa.String(500)),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text('NOW()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text('NOW()'))
    )
    
    # Create sanctions_programs table
    op.create_table(
        'sanctions_programs',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text('uuid_generate_v4()')),
        sa.Column('code', sa.String(50), nullable=False, unique=True),
        sa.Column('name', sa.String(500), nullable=False),
        sa.Column('description', sa.Text),
        sa.Column('authority', sa.String(100)),
        sa.Column('is_active', sa.Boolean, nullable=False, server_default='true'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text('NOW()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text('NOW()'))
    )
    
    # Create entity_programs table
    op.create_table(
        'entity_programs',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text('uuid_generate_v4()')),
        sa.Column('entity_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('sanctioned_entities.id', ondelete='CASCADE'), nullable=False),
        sa.Column('program_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('sanctions_programs.id', ondelete='CASCADE'), nullable=False),
        sa.Column('listed_date', sa.DateTime(timezone=True)),
        sa.Column('listing_reason', sa.Text),
        sa.Column('is_active', sa.Boolean, nullable=False, server_default='true'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text('NOW()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text('NOW()')),
        sa.UniqueConstraint('entity_id', 'program_id', name='uq_entity_program')
    )
    
    # Create screening_requests table
    op.create_table(
        'screening_requests',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text('uuid_generate_v4()')),
        sa.Column('request_type', sa.String(20), nullable=False, server_default='single'),
        sa.Column('status', sa.Enum('pending', 'processing', 'completed', 'failed',
                                    name='screening_status'), nullable=False, server_default='pending'),
        sa.Column('input_data', postgresql.JSONB, nullable=False),
        sa.Column('screened_name', sa.String(500)),
        sa.Column('screened_document', sa.String(100)),
        sa.Column('analyst_name', sa.String(200)),
        sa.Column('analyst_id', sa.String(100)),
        sa.Column('api_key_id', sa.String(100)),
        sa.Column('ip_address', sa.String(50)),
        sa.Column('user_agent', sa.String(500)),
        sa.Column('processing_start', sa.DateTime(timezone=True)),
        sa.Column('processing_end', sa.DateTime(timezone=True)),
        sa.Column('processing_time_ms', sa.Integer),
        sa.Column('error_message', sa.Text),
        sa.Column('error_code', sa.String(50)),
        sa.Column('algorithm_version', sa.String(20)),
        sa.Column('thresholds_used', postgresql.JSONB),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text('NOW()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text('NOW()'))
    )
    
    # Create screening_results table
    op.create_table(
        'screening_results',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text('uuid_generate_v4()')),
        sa.Column('request_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('screening_requests.id', ondelete='CASCADE'), nullable=False),
        sa.Column('input_name', sa.String(500), nullable=False),
        sa.Column('input_document', sa.String(100)),
        sa.Column('input_country', sa.String(100)),
        sa.Column('is_hit', sa.Boolean, nullable=False),
        sa.Column('hit_count', sa.Integer, nullable=False, server_default='0'),
        sa.Column('max_confidence', sa.Float),
        sa.Column('recommendation', sa.Enum('AUTO_ESCALATE', 'MANUAL_REVIEW', 
                                           'LOW_CONFIDENCE_REVIEW', 'AUTO_CLEAR',
                                           name='recommendation_type')),
        sa.Column('flags', postgresql.ARRAY(sa.String)),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text('NOW()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text('NOW()'))
    )
    
    # Create screening_matches table
    op.create_table(
        'screening_matches',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text('uuid_generate_v4()')),
        sa.Column('result_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('screening_results.id', ondelete='CASCADE'), nullable=False),
        sa.Column('entity_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('sanctioned_entities.id', ondelete='SET NULL')),
        sa.Column('matched_name', sa.String(500), nullable=False),
        sa.Column('matched_document', sa.String(100)),
        sa.Column('match_layer', sa.Integer, nullable=False),
        sa.Column('overall_confidence', sa.Float, nullable=False),
        sa.Column('name_confidence', sa.Float, nullable=False, server_default='0.0'),
        sa.Column('document_confidence', sa.Float, nullable=False, server_default='0.0'),
        sa.Column('dob_confidence', sa.Float, nullable=False, server_default='0.0'),
        sa.Column('nationality_confidence', sa.Float, nullable=False, server_default='0.0'),
        sa.Column('address_confidence', sa.Float, nullable=False, server_default='0.0'),
        sa.Column('flags', postgresql.ARRAY(sa.String)),
        sa.Column('recommendation', sa.Enum('AUTO_ESCALATE', 'MANUAL_REVIEW',
                                           'LOW_CONFIDENCE_REVIEW', 'AUTO_CLEAR',
                                           name='recommendation_type'), nullable=False),
        sa.Column('entity_snapshot', postgresql.JSONB),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text('NOW()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text('NOW()')),
        sa.CheckConstraint('overall_confidence >= 0 AND overall_confidence <= 100',
                          name='ck_confidence_range'),
        sa.CheckConstraint('match_layer >= 1 AND match_layer <= 4', name='ck_layer_range')
    )
    
    # Create audit_logs table
    op.create_table(
        'audit_logs',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text('uuid_generate_v4()')),
        sa.Column('timestamp', sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text('NOW()')),
        sa.Column('action', sa.Enum('CREATE', 'READ', 'UPDATE', 'DELETE', 'SCREEN',
                                    'BULK_SCREEN', 'DATA_UPDATE', 'LOGIN', 'LOGOUT',
                                    'CONFIG_CHANGE', name='audit_action'), nullable=False),
        sa.Column('resource_type', sa.String(100), nullable=False),
        sa.Column('resource_id', sa.String(100)),
        sa.Column('actor_id', sa.String(100)),
        sa.Column('actor_name', sa.String(200)),
        sa.Column('actor_ip', sa.String(50)),
        sa.Column('details', postgresql.JSONB),
        sa.Column('old_value', postgresql.JSONB),
        sa.Column('new_value', postgresql.JSONB),
        sa.Column('success', sa.Boolean, nullable=False, server_default='true'),
        sa.Column('error_message', sa.Text)
    )
    
    # Create data_sources table
    op.create_table(
        'data_sources',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text('uuid_generate_v4()')),
        sa.Column('code', sa.String(20), nullable=False, unique=True),
        sa.Column('name', sa.String(200), nullable=False),
        sa.Column('source_type', sa.Enum('OFAC', 'UN', 'EU', 'UK', 'OTHER',
                                         name='data_source_type'), nullable=False),
        sa.Column('download_url', sa.String(1000), nullable=False),
        sa.Column('file_format', sa.String(20), nullable=False, server_default='xml'),
        sa.Column('is_active', sa.Boolean, nullable=False, server_default='true'),
        sa.Column('update_frequency_days', sa.Integer, nullable=False, server_default='7'),
        sa.Column('last_update', sa.DateTime(timezone=True)),
        sa.Column('last_update_status', sa.String(50)),
        sa.Column('last_entity_count', sa.Integer),
        sa.Column('validate_xsd', sa.Boolean, nullable=False, server_default='true'),
        sa.Column('xsd_url', sa.String(1000)),
        sa.Column('expected_hash', sa.String(128)),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text('NOW()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text('NOW()'))
    )
    
    # Create data_updates table
    op.create_table(
        'data_updates',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text('uuid_generate_v4()')),
        sa.Column('source_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('data_sources.id', ondelete='CASCADE'), nullable=False),
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('completed_at', sa.DateTime(timezone=True)),
        sa.Column('status', sa.String(50), nullable=False, server_default='in_progress'),
        sa.Column('entities_added', sa.Integer, nullable=False, server_default='0'),
        sa.Column('entities_updated', sa.Integer, nullable=False, server_default='0'),
        sa.Column('entities_removed', sa.Integer, nullable=False, server_default='0'),
        sa.Column('total_entities', sa.Integer, nullable=False, server_default='0'),
        sa.Column('validation_errors', sa.Integer, nullable=False, server_default='0'),
        sa.Column('validation_warnings', sa.Integer, nullable=False, server_default='0'),
        sa.Column('validation_details', postgresql.JSONB),
        sa.Column('file_hash', sa.String(128)),
        sa.Column('file_size_bytes', sa.Integer),
        sa.Column('error_message', sa.Text),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text('NOW()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text('NOW()'))
    )
    
    # Create indexes
    op.create_index('ix_entity_external_id', 'sanctioned_entities', ['external_id'])
    op.create_index('ix_entity_source', 'sanctioned_entities', ['source'])
    op.create_index('ix_entity_type', 'sanctioned_entities', ['entity_type'])
    op.create_index('ix_entity_primary_name', 'sanctioned_entities', ['primary_name'])
    op.create_index('ix_entity_normalized_name', 'sanctioned_entities', ['normalized_name'])
    op.create_index('ix_entity_nationality', 'sanctioned_entities', ['nationality'])
    op.create_index('ix_entity_is_deleted', 'sanctioned_entities', ['is_deleted'])
    op.create_index('ix_entity_name_trgm', 'sanctioned_entities', ['normalized_name'],
                    postgresql_using='gin', postgresql_ops={'normalized_name': 'gin_trgm_ops'})
    
    op.create_index('ix_alias_entity_id', 'entity_aliases', ['entity_id'])
    op.create_index('ix_alias_normalized', 'entity_aliases', ['normalized_alias'])
    
    op.create_index('ix_document_entity_id', 'identity_documents', ['entity_id'])
    op.create_index('ix_document_normalized_number', 'identity_documents', ['normalized_number'])
    
    op.create_index('ix_address_entity_id', 'entity_addresses', ['entity_id'])
    op.create_index('ix_address_country', 'entity_addresses', ['country'])
    
    op.create_index('ix_feature_entity_id', 'entity_features', ['entity_id'])
    op.create_index('ix_feature_type', 'entity_features', ['feature_type'])
    
    op.create_index('ix_screening_request_date', 'screening_requests', ['created_at'])
    op.create_index('ix_screening_request_status', 'screening_requests', ['status'])
    
    op.create_index('ix_screening_result_request_id', 'screening_results', ['request_id'])
    op.create_index('ix_screening_result_hit', 'screening_results', ['is_hit'])
    
    op.create_index('ix_screening_match_result_id', 'screening_matches', ['result_id'])
    op.create_index('ix_screening_match_entity_id', 'screening_matches', ['entity_id'])
    
    op.create_index('ix_audit_timestamp', 'audit_logs', ['timestamp'])
    op.create_index('ix_audit_action', 'audit_logs', ['action'])
    
    op.create_index('ix_data_update_source_id', 'data_updates', ['source_id'])
    
    # Insert default data sources
    op.execute("""
        INSERT INTO data_sources (code, name, source_type, download_url)
        VALUES 
            ('OFAC', 'OFAC SDN Enhanced', 'OFAC', 
             'https://sanctionslistservice.ofac.treas.gov/api/PublicationPreview/exports/SDN_ENHANCED.ZIP'),
            ('UN', 'UN Consolidated List', 'UN',
             'https://scsanctions.un.org/resources/xml/en/consolidated.xml')
        ON CONFLICT (code) DO NOTHING
    """)
    
    # Insert default sanctions programs
    op.execute("""
        INSERT INTO sanctions_programs (code, name, authority, is_active)
        VALUES 
            ('SDGT', 'Specially Designated Global Terrorist', 'OFAC', true),
            ('SDNTK', 'Specially Designated Narcotics Trafficker Kingpin Act', 'OFAC', true),
            ('SDN', 'Specially Designated Nationals', 'OFAC', true),
            ('UN-CONSOLIDATED', 'UN Consolidated List', 'UN', true)
        ON CONFLICT (code) DO NOTHING
    """)


def downgrade() -> None:
    """Drop all tables and types."""
    # Drop tables in reverse order
    op.drop_table('data_updates')
    op.drop_table('data_sources')
    op.drop_table('audit_logs')
    op.drop_table('screening_matches')
    op.drop_table('screening_results')
    op.drop_table('screening_requests')
    op.drop_table('entity_programs')
    op.drop_table('sanctions_programs')
    op.drop_table('entity_features')
    op.drop_table('entity_addresses')
    op.drop_table('identity_documents')
    op.drop_table('entity_aliases')
    op.drop_table('sanctioned_entities')
    
    # Drop enums
    op.execute('DROP TYPE IF EXISTS audit_action')
    op.execute('DROP TYPE IF EXISTS recommendation_type')
    op.execute('DROP TYPE IF EXISTS screening_status')
    op.execute('DROP TYPE IF EXISTS data_source_type')
    op.execute('DROP TYPE IF EXISTS entity_type')
