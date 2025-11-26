#!/usr/bin/env python3
"""
Initial Data Loading Script for SDNCheck

Loads initial reference data into the database including:
- Data sources (OFAC, UN)
- Sanctions programs
- Sample entities (optional, for development)

Usage:
    python load_initial_data.py [--with-samples]
"""

import sys
import argparse
import logging
from pathlib import Path

# Add parent to path
sys.path.insert(0, str(Path(__file__).parent))

from database.connection import init_db, close_db
from database.models import (
    DataSource, SanctionsProgram, SanctionedEntity, EntityAlias,
    DataSourceType, EntityType
)

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


def load_data_sources(session):
    """Load default data sources."""
    sources = [
        {
            "code": "OFAC",
            "name": "OFAC SDN Enhanced List",
            "source_type": DataSourceType.OFAC,
            "download_url": "https://sanctionslistservice.ofac.treas.gov/api/PublicationPreview/exports/SDN_ENHANCED.ZIP",
            "file_format": "xml",
            "is_active": True,
            "update_frequency_days": 1,
            "validate_xsd": True
        },
        {
            "code": "UN",
            "name": "UN Consolidated List",
            "source_type": DataSourceType.UN,
            "download_url": "https://scsanctions.un.org/resources/xml/en/consolidated.xml",
            "file_format": "xml",
            "is_active": True,
            "update_frequency_days": 1,
            "validate_xsd": True
        },
        {
            "code": "EU",
            "name": "EU Consolidated List",
            "source_type": DataSourceType.EU,
            "download_url": "https://webgate.ec.europa.eu/fsd/fsf/public/files/xmlFullSanctionsList/content",
            "file_format": "xml",
            "is_active": False,
            "update_frequency_days": 7
        },
        {
            "code": "UK",
            "name": "UK Consolidated List",
            "source_type": DataSourceType.UK,
            "download_url": "https://ofsistorage.blob.core.windows.net/publishlive/ConList.xml",
            "file_format": "xml",
            "is_active": False,
            "update_frequency_days": 7
        }
    ]
    
    created = 0
    for source_data in sources:
        existing = session.query(DataSource).filter_by(code=source_data["code"]).first()
        if not existing:
            source = DataSource(**source_data)
            session.add(source)
            created += 1
            logger.info(f"Created data source: {source_data['code']}")
        else:
            logger.info(f"Data source already exists: {source_data['code']}")
    
    return created


def load_sanctions_programs(session):
    """Load default sanctions programs."""
    programs = [
        {"code": "SDGT", "name": "Specially Designated Global Terrorist", "authority": "OFAC", "description": "Persons who commit, threaten to commit, or support terrorism"},
        {"code": "SDNTK", "name": "Specially Designated Narcotics Trafficker Kingpin Act", "authority": "OFAC", "description": "Foreign drug kingpins and their organizations"},
        {"code": "SDN", "name": "Specially Designated Nationals and Blocked Persons", "authority": "OFAC", "description": "General OFAC sanctions list"},
        {"code": "CYBER2", "name": "Malicious Cyber-Enabled Activities", "authority": "OFAC", "description": "Cyber-related sanctions"},
        {"code": "IRAN", "name": "Iran Sanctions", "authority": "OFAC", "description": "Iran-related sanctions"},
        {"code": "RUSSIA", "name": "Russia Sanctions", "authority": "OFAC", "description": "Russia-related sanctions"},
        {"code": "SYRIA", "name": "Syria Sanctions", "authority": "OFAC", "description": "Syria-related sanctions"},
        {"code": "VENEZUELA", "name": "Venezuela Sanctions", "authority": "OFAC", "description": "Venezuela-related sanctions"},
        {"code": "CUBA", "name": "Cuba Sanctions", "authority": "OFAC", "description": "Cuba-related sanctions"},
        {"code": "DPRK", "name": "North Korea Sanctions", "authority": "OFAC", "description": "North Korea-related sanctions"},
        {"code": "UN-CONSOLIDATED", "name": "UN Consolidated Sanctions", "authority": "UN", "description": "United Nations consolidated sanctions list"},
        {"code": "UN-TALIBAN", "name": "UN Taliban Sanctions", "authority": "UN", "description": "Taliban and Al-Qaeda sanctions"},
        {"code": "UN-ISIL", "name": "UN ISIL/Da'esh Sanctions", "authority": "UN", "description": "ISIL/Da'esh and Al-Qaeda sanctions"},
    ]
    
    created = 0
    for prog_data in programs:
        existing = session.query(SanctionsProgram).filter_by(code=prog_data["code"]).first()
        if not existing:
            # Create program with explicit field assignment to avoid key conflicts
            program = SanctionsProgram(
                code=prog_data["code"],
                name=prog_data["name"],
                authority=prog_data.get("authority"),
                description=prog_data.get("description"),
                is_active=True
            )
            session.add(program)
            created += 1
            logger.info(f"Created sanctions program: {prog_data['code']}")
        else:
            logger.info(f"Sanctions program already exists: {prog_data['code']}")
    
    return created


def load_sample_entities(session):
    """Load sample entities for development/testing."""
    from database.models import normalize_name
    
    samples = [
        {
            "external_id": "SAMPLE-001",
            "source": DataSourceType.OTHER,
            "entity_type": EntityType.INDIVIDUAL,
            "primary_name": "Sample Test Person",
            "first_name": "Sample",
            "last_name": "Person",
            "nationality": "United States",
            "date_of_birth": "1980-01-15"
        },
        {
            "external_id": "SAMPLE-002",
            "source": DataSourceType.OTHER,
            "entity_type": EntityType.ENTITY,
            "primary_name": "Sample Test Corporation Ltd",
            "nationality": "Panama"
        },
        {
            "external_id": "SAMPLE-003",
            "source": DataSourceType.OTHER,
            "entity_type": EntityType.VESSEL,
            "primary_name": "MV Sample Vessel",
            "vessel_type": "Cargo",
            "vessel_flag": "Panama",
            "vessel_imo": "9999999"
        }
    ]
    
    created = 0
    for entity_data in samples:
        existing = session.query(SanctionedEntity).filter_by(
            external_id=entity_data["external_id"],
            source=entity_data["source"]
        ).first()
        
        if not existing:
            entity_data["normalized_name"] = normalize_name(entity_data["primary_name"])
            entity = SanctionedEntity(**entity_data)
            session.add(entity)
            created += 1
            logger.info(f"Created sample entity: {entity_data['primary_name']}")
        else:
            logger.info(f"Sample entity already exists: {entity_data['primary_name']}")
    
    return created


def main():
    parser = argparse.ArgumentParser(description="Load initial data into SDNCheck database")
    parser.add_argument("--with-samples", action="store_true", help="Include sample entities for development")
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose output")
    args = parser.parse_args()
    
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    
    logger.info("=" * 50)
    logger.info("SDNCheck Initial Data Loading")
    logger.info("=" * 50)
    
    try:
        # Initialize database
        db = init_db()
        
        with db.session_scope() as session:
            # Load data sources
            logger.info("\n[1/3] Loading data sources...")
            sources_created = load_data_sources(session)
            logger.info(f"Data sources created: {sources_created}")
            
            # Load sanctions programs
            logger.info("\n[2/3] Loading sanctions programs...")
            programs_created = load_sanctions_programs(session)
            logger.info(f"Sanctions programs created: {programs_created}")
            
            # Load sample entities (optional)
            if args.with_samples:
                logger.info("\n[3/3] Loading sample entities...")
                samples_created = load_sample_entities(session)
                logger.info(f"Sample entities created: {samples_created}")
            else:
                logger.info("\n[3/3] Skipping sample entities (use --with-samples to include)")
            
            session.commit()
        
        logger.info("\n" + "=" * 50)
        logger.info("Initial data loading complete!")
        logger.info("=" * 50)
    except Exception as e:
        logger.error(f"Error loading initial data: {e}")
        if 'session' in locals():
            session.rollback()
        raise
    finally:
        close_db()


if __name__ == "__main__":
    main()
