"""
Tests de integración y comportamiento real para los repositorios principales.
Valida casos de uso reales de usuario: creación, búsqueda, actualización, borrado lógico, screening y auditoría.
"""
import pytest
import uuid
from datetime import datetime, timezone
from database.connection import DatabaseSessionProvider, DatabaseSettings
from database.repositories import (
    SanctionedEntityRepository,
    ScreeningRepository,
    AuditRepository,
    DataSourceRepository
)
from database.models import (
    DataSourceType, EntityType, AuditAction
)

@pytest.fixture(scope="module")
def db_provider():
    settings = DatabaseSettings(
        host="localhost",
        port=5432,
        database="sdn_test_database",
        user="sdn_user",
        password="sdn_password",
        pool_size=2,
        max_overflow=5,
        echo=False
    )
    provider = DatabaseSessionProvider(settings=settings)
    provider.init()
    yield provider
    provider.close()

@pytest.fixture
def session(db_provider):
    with db_provider.session_scope() as session:
        yield session

@pytest.mark.skip(reason="Deshabilitado temporalmente: problemas con la base de datos de test")
def test_create_and_search_entity(session):
    repo = SanctionedEntityRepository(session)
    entity_data = {
        "external_id": f"TEST-{uuid.uuid4()}",
        "source": DataSourceType.OFAC,
        "entity_type": EntityType.INDIVIDUAL,
        "primary_name": "John Doe"
    }
    entity = repo.create(entity_data)
    assert entity.id is not None
    found = repo.get_by_id(entity.id)
    assert found is not None
    assert found.primary_name == "John Doe"
    # Búsqueda por nombre
    results = repo.search_by_name("John Doe")
    assert any(e.id == entity.id for e, _ in results)

@pytest.mark.skip(reason="Deshabilitado temporalmente: problemas con la base de datos de test")
def test_update_and_soft_delete_entity(session):
    repo = SanctionedEntityRepository(session)
    entity_data = {
        "external_id": f"TEST-{uuid.uuid4()}",
        "source": DataSourceType.UN,
        "entity_type": EntityType.ENTITY,
        "primary_name": "Acme Corp"
    }
    entity = repo.create(entity_data)
    updated = repo.update(entity.id, {"primary_name": "Acme Corporation"})
    assert updated.primary_name == "Acme Corporation"
    deleted = repo.soft_delete(entity.id)
    assert deleted is True
    assert repo.get_by_id(entity.id, include_deleted=True).is_deleted

@pytest.mark.skip(reason="Deshabilitado temporalmente: problemas con la base de datos de test")
def test_screening_request_and_result(session):
    screening_repo = ScreeningRepository(session)
    request = screening_repo.create_request({"name": "Jane Doe", "document": "X12345"})
    assert request.id is not None
    result = screening_repo.add_result(
        request_id=request.id,
        input_name="Jane Doe",
        is_hit=True,
        hit_count=1,
        recommendation=None
    )
    assert result.id is not None
    screening_repo.complete_request(request.id)
    completed = screening_repo.get_request_with_results(request.id)
    assert completed.status.name == "COMPLETED"
    assert len(completed.results) == 1

@pytest.mark.skip(reason="Deshabilitado temporalmente: problemas con la base de datos de test")
def test_audit_log_and_search(session):
    audit_repo = AuditRepository(session)
    log = audit_repo.log(
        action=AuditAction.CREATE,
        resource_type="entity",
        resource_id="test-id",
        actor_id="user-1",
        actor_name="Test User",
        details={"field": "value"}
    )
    assert log.id is not None
    logs, total = audit_repo.search(actor_id="user-1")
    assert any(l.id == log.id for l in logs)
    assert total >= 1

@pytest.mark.skip(reason="Deshabilitado temporalmente: problemas con la base de datos de test")
def test_data_source_and_update(session):
    ds_repo = DataSourceRepository(session)
    # Crear DataSource OFAC si no existe
    ds = ds_repo.get_by_code("OFAC")
    if ds is None:
        from database.models import DataSource
        ds = DataSource(code="OFAC", name="OFAC", is_active=True, source_type="OFAC")
        session.add(ds)
        session.flush()
    active_sources = ds_repo.list_active()
    assert any(s.code == "OFAC" for s in active_sources)
    # Registrar y completar actualización
    update = ds_repo.record_update(
        source_id=ds.id,
        entities_added=10,
        entities_updated=5,
        total_entities=15
    )
    assert update.id is not None
    completed = ds_repo.complete_update(update.id)
    assert completed.status == "completed"
