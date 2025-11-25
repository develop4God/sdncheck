#!/usr/bin/env python3
"""
Functional Test Script for SDNCheck Database Operations

This script validates that the API/services can read and write to the database.
Run this after setting up the database to verify everything works correctly.

Usage:
    python functional_test_db.py [--verbose]
"""

import sys
import argparse
import logging
from pathlib import Path
from datetime import datetime, timezone
import uuid

# Add parent to path
sys.path.insert(0, str(Path(__file__).parent))

# Module-level imports for clarity
from database.connection import init_db, close_db, get_db_provider
from database.repositories import (
    SanctionedEntityRepository,
    ScreeningRepository,
    AuditRepository,
    DataSourceRepository
)
from database.models import (
    DataSourceType, EntityType, AuditAction,
    SanctionedEntity, ScreeningRequest, AuditLog
)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def test_database_connection():
    """Test basic database connectivity."""
    logger.info("Testing database connection...")
    
    db = init_db()
    
    # Test health check
    health = db.health_check()
    if not health:
        raise Exception("Database health check failed")
    
    logger.info("✅ Database connection: OK")
    return True


def test_create_entity():
    """Test creating an entity."""
    logger.info("Testing entity creation...")
    
    provider = get_db_provider()
    
    with provider.session_scope() as session:
        repo = SanctionedEntityRepository(session)
        
        entity_data = {
            "external_id": f"FUNC-TEST-{uuid.uuid4()}",
            "source": DataSourceType.OTHER,
            "entity_type": EntityType.INDIVIDUAL,
            "primary_name": "Functional Test Entity",
            "nationality": "Panama"
        }
        
        entity = repo.create(entity_data)
        
        if not entity.id:
            raise Exception("Entity creation failed - no ID returned")
        
        logger.info(f"✅ Entity creation: OK (ID: {entity.id})")
        return entity.id


def test_read_entity(entity_id):
    """Test reading an entity."""
    logger.info("Testing entity read...")
    
    provider = get_db_provider()
    
    with provider.session_scope() as session:
        repo = SanctionedEntityRepository(session)
        
        entity = repo.get_by_id(entity_id)
        
        if not entity:
            raise Exception(f"Entity read failed - entity {entity_id} not found")
        
        if entity.primary_name != "Functional Test Entity":
            raise Exception("Entity data mismatch")
        
        logger.info(f"✅ Entity read: OK (Name: {entity.primary_name})")
        return True


def test_update_entity(entity_id):
    """Test updating an entity."""
    logger.info("Testing entity update...")
    
    provider = get_db_provider()
    
    with provider.session_scope() as session:
        repo = SanctionedEntityRepository(session)
        
        updated = repo.update(entity_id, {
            "primary_name": "Updated Functional Test Entity"
        })
        
        if updated.primary_name != "Updated Functional Test Entity":
            raise Exception("Entity update failed")
        
        logger.info(f"✅ Entity update: OK")
        return True


def test_search_entity():
    """Test searching for entities."""
    logger.info("Testing entity search...")
    
    provider = get_db_provider()
    
    with provider.session_scope() as session:
        repo = SanctionedEntityRepository(session)
        
        # Search by name
        results = repo.search_by_name("Functional Test")
        
        # Results may be empty if trigram extension not configured
        # But the query should not fail
        logger.info(f"✅ Entity search: OK (found {len(results)} results)")
        return True


def test_soft_delete_entity(entity_id):
    """Test soft-deleting an entity."""
    logger.info("Testing entity soft delete...")
    
    provider = get_db_provider()
    
    with provider.session_scope() as session:
        repo = SanctionedEntityRepository(session)
        
        deleted = repo.soft_delete(entity_id)
        
        if not deleted:
            raise Exception("Entity soft delete failed")
        
        # Verify entity is marked as deleted
        entity = repo.get_by_id(entity_id, include_deleted=True)
        if not entity.is_deleted:
            raise Exception("Entity not marked as deleted")
        
        logger.info(f"✅ Entity soft delete: OK")
        return True


def test_screening_workflow():
    """Test complete screening workflow."""
    logger.info("Testing screening workflow...")
    
    provider = get_db_provider()
    
    with provider.session_scope() as session:
        repo = ScreeningRepository(session)
        
        # Create screening request
        request = repo.create_request({
            "name": "Functional Test Screening",
            "document": "FT12345"
        })
        
        if not request.id:
            raise Exception("Screening request creation failed")
        
        # Add result
        result = repo.add_result(
            request_id=request.id,
            input_name="Functional Test Screening",
            is_hit=False,
            hit_count=0,
            recommendation=None
        )
        
        if not result.id:
            raise Exception("Screening result creation failed")
        
        # Complete request
        repo.complete_request(request.id)
        
        # Verify
        completed = repo.get_request_with_results(request.id)
        if completed.status.name != "COMPLETED":
            raise Exception("Screening request not completed")
        
        logger.info(f"✅ Screening workflow: OK")
        return True


def test_audit_logging():
    """Test audit logging functionality."""
    logger.info("Testing audit logging...")
    
    provider = get_db_provider()
    
    with provider.session_scope() as session:
        repo = AuditRepository(session)
        
        # Create audit log
        log = repo.log(
            action=AuditAction.SCREEN,
            resource_type="functional_test",
            resource_id=f"test-{uuid.uuid4()}",
            actor_id="functional-test",
            actor_name="Functional Test Script",
            details={"test": "functional"}
        )
        
        if not log.id:
            raise Exception("Audit log creation failed")
        
        # Search for log
        logs, total = repo.search(actor_id="functional-test")
        
        if total < 1:
            raise Exception("Audit log search failed")
        
        logger.info(f"✅ Audit logging: OK")
        return True


def test_data_sources():
    """Test data source operations."""
    logger.info("Testing data sources...")
    
    provider = get_db_provider()
    
    with provider.session_scope() as session:
        repo = DataSourceRepository(session)
        
        # List active sources
        sources = repo.list_active()
        
        logger.info(f"✅ Data sources: OK (found {len(sources)} active sources)")
        return True


def test_unit_of_work():
    """Test Unit of Work pattern."""
    logger.info("Testing Unit of Work pattern...")
    
    provider = get_db_provider()
    
    with provider.get_unit_of_work() as uow:
        repo = SanctionedEntityRepository(uow.session)
        
        entity_data = {
            "external_id": f"UOW-TEST-{uuid.uuid4()}",
            "source": DataSourceType.OTHER,
            "entity_type": EntityType.ENTITY,
            "primary_name": "Unit of Work Test Entity"
        }
        
        entity = repo.create(entity_data)
        uow.commit()  # Explicit commit
        
        if not entity.id:
            raise Exception("Unit of Work test failed")
        
        logger.info(f"✅ Unit of Work: OK")
        return True


def cleanup_test_data():
    """Clean up test data."""
    logger.info("Cleaning up test data...")
    
    from sqlalchemy import or_
    
    provider = get_db_provider()
    
    with provider.session_scope() as session:
        # Delete test entities
        session.query(SanctionedEntity).filter(
            or_(
                SanctionedEntity.external_id.like("FUNC-TEST-%"),
                SanctionedEntity.external_id.like("UOW-TEST-%")
            )
        ).delete(synchronize_session=False)
        
        # Delete test screening requests
        session.query(ScreeningRequest).filter(
            ScreeningRequest.screened_name == "Functional Test Screening"
        ).delete(synchronize_session=False)
        
        # Delete test audit logs
        session.query(AuditLog).filter(
            AuditLog.actor_id == "functional-test"
        ).delete(synchronize_session=False)
        
        session.commit()
    
    logger.info("✅ Cleanup: OK")


def main():
    parser = argparse.ArgumentParser(description="Run functional tests for SDNCheck database")
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose output")
    parser.add_argument("--no-cleanup", action="store_true", help="Skip cleanup of test data")
    args = parser.parse_args()
    
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    
    print("=" * 60)
    print("  SDNCheck Functional Database Tests")
    print("=" * 60)
    
    tests_passed = 0
    tests_failed = 0
    entity_id = None
    
    tests = [
        ("Database Connection", test_database_connection),
        ("Create Entity", test_create_entity),
        ("Read Entity", lambda: test_read_entity(entity_id)),
        ("Update Entity", lambda: test_update_entity(entity_id)),
        ("Search Entity", test_search_entity),
        ("Soft Delete Entity", lambda: test_soft_delete_entity(entity_id)),
        ("Screening Workflow", test_screening_workflow),
        ("Audit Logging", test_audit_logging),
        ("Data Sources", test_data_sources),
        ("Unit of Work", test_unit_of_work),
    ]
    
    try:
        for name, test_func in tests:
            try:
                result = test_func()
                if name == "Create Entity":
                    entity_id = result
                tests_passed += 1
            except Exception as e:
                logger.error(f"❌ {name}: FAILED - {e}")
                tests_failed += 1
        
        if not args.no_cleanup:
            cleanup_test_data()
        
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        tests_failed += 1
    
    print("\n" + "=" * 60)
    print(f"  Results: {tests_passed} passed, {tests_failed} failed")
    print("=" * 60)
    
    if tests_failed > 0:
        sys.exit(1)
    
    print("\n🎉 All functional tests passed!")


if __name__ == "__main__":
    main()
