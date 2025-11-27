# Singleton to Dependency Injection Migration Guide

This guide documents the migration path from deprecated singleton patterns to modern dependency injection patterns for improved testability and maintainability.

## Timeline

| Phase | Sprint | Description |
|-------|--------|-------------|
| Phase 1 | N+1 | Identify all singleton usages |
| Phase 2 | N+2 | Migrate critical paths to DI pattern |
| Phase 3 | N+3 | Remove deprecated singletons entirely |

---

## Why Migrate?

Singleton patterns have several drawbacks:

1. **Hard to test**: Singletons create global state that's difficult to mock
2. **Hidden dependencies**: Components don't declare their needs explicitly
3. **No lifecycle control**: Hard to manage resources per-request
4. **Thread safety concerns**: Shared mutable state across threads

Dependency injection solves these issues:

1. **Testable**: Inject mock dependencies in tests
2. **Explicit dependencies**: FastAPI `Depends()` makes dependencies clear
3. **Per-request lifecycle**: Resources created/closed per request automatically
4. **Thread-safe**: Each request gets its own instance

---

## Deprecated Patterns

### 1. ConfigManager Singleton

**Before (Deprecated)**:
```python
from config_manager import get_config, ConfigManager

# Using singleton function
config = get_config()

# Using singleton method
config = ConfigManager.get_instance()
```

**After (Recommended)**:
```python
from config_manager import ConfigManager, get_config_dependency

# Direct instantiation (preferred for DI)
config = ConfigManager("config.yaml")

# Factory method
config = ConfigManager.create("config.yaml")

# FastAPI dependency
@app.get("/settings")
def get_settings(config: ConfigManager = Depends(get_config_dependency)):
    return {"version": config.algorithm.version}
```

### 2. DatabaseManager Singleton

**Before (Deprecated)**:
```python
from database.connection import DatabaseManager, get_db_manager

# Using singleton directly
db = DatabaseManager()
with db.session() as session:
    entities = session.query(SanctionedEntity).all()
```

**After (Recommended)**:
```python
from fastapi import Depends
from sqlalchemy.orm import Session
from database.connection import get_db

@app.get("/entities")
def get_entities(db: Session = Depends(get_db)):
    repo = SanctionedEntityRepository(db)
    return repo.list_all()
```

---

## Data Mode: XML vs Database

The API now supports two data modes:

### XML Mode (Default)
- Loads entities from XML files at startup
- Good for development and testing
- Data stored in memory

### Database Mode (Production)
- Queries PostgreSQL for screening
- Set `USE_DATABASE=true` environment variable
- Data stored in PostgreSQL with trigram search

```bash
# Enable database mode
export USE_DATABASE=true
export DATABASE_URL=postgresql://user:pass@host:5432/dbname

# Start server
uvicorn api.server:app --host 0.0.0.0 --port 8000
```

#### Option 2: Unit of Work Pattern (For Complex Transactions)

```python
from database.connection import get_db_provider

provider = get_db_provider()

with provider.get_unit_of_work() as uow:
    repo = SanctionedEntityRepository(uow.session)
    entity = repo.create(data)
    # More operations...
    uow.commit()  # Explicit commit
```

#### Option 3: Session Scope Context Manager

```python
from database.connection import get_db_provider

provider = get_db_provider()

with provider.session_scope() as session:
    session.add(entity)
    # Auto-commits on success, rollbacks on exception
```

---

## Migration Steps by Module

### API Routes (`api/routes/`)

**Priority: HIGH**

```python
# Before
@app.get("/entities/{id}")
def get_entity(id: str):
    db = DatabaseManager()
    with db.session() as session:
        return session.query(SanctionedEntity).get(id)

# After
@app.get("/entities/{id}")
def get_entity(id: str, db: Session = Depends(get_db)):
    return db.query(SanctionedEntity).get(id)
```

### Background Tasks (`tasks/`)

**Priority: MEDIUM**

```python
# Before
def refresh_sanctions_list():
    db = DatabaseManager()
    with db.session() as session:
        # process data
        session.commit()

# After
def refresh_sanctions_list():
    provider = get_db_provider()
    with provider.get_unit_of_work() as uow:
        repo = SanctionedEntityRepository(uow.session)
        # process data
        uow.commit()
```

### Tests (`tests/`)

**Priority: HIGH**

```python
# Before
class TestEntity:
    def setup_method(self):
        self.db = DatabaseManager()
        
    def test_create(self):
        with self.db.session() as session:
            # test code

# After (using pytest fixtures)
@pytest.fixture
def db_session():
    provider = create_test_provider()
    provider.init()
    with provider.session_scope() as session:
        yield session
        session.rollback()

def test_create(db_session):
    repo = SanctionedEntityRepository(db_session)
    # test code
```

---

## Migration Checklist

### Phase 1: Audit (Sprint N+1)

- [ ] Run `grep -r "DatabaseManager" python/` to find all usages
- [ ] Create inventory of all instantiation points
- [ ] Categorize by module (API, tasks, tests, scripts)
- [ ] Create Jira tickets for each module migration
- [ ] Add deprecation warnings (already done in codebase)

### Phase 2: Migrate Critical Paths (Sprint N+2)

- [ ] Migrate all API route handlers
- [ ] Migrate screening service endpoints
- [ ] Migrate health check endpoints
- [ ] Update integration tests
- [ ] Verify no regressions

### Phase 3: Complete Migration (Sprint N+3)

- [ ] Migrate background tasks
- [ ] Migrate CLI scripts
- [ ] Migrate all remaining tests
- [ ] Remove DatabaseManager class
- [ ] Remove get_db_manager() function
- [ ] Update documentation

---

## Finding Usages

Run this command to find all `DatabaseManager` usages:

```bash
# Find all usages
grep -rn "DatabaseManager" python/ --include="*.py"

# Find all get_db_manager usages
grep -rn "get_db_manager" python/ --include="*.py"

# Count usages by file
grep -rc "DatabaseManager\|get_db_manager" python/ --include="*.py" | grep -v ":0"
```

---

## Deprecation Warnings

The codebase now emits warnings when using deprecated patterns:

```python
import warnings

class DatabaseManager(DatabaseSessionProvider):
    """DEPRECATED: Use DatabaseSessionProvider instead."""
    
    def __new__(cls, *args, **kwargs):
        warnings.warn(
            "DatabaseManager is deprecated. Use DatabaseSessionProvider with "
            "FastAPI Depends() or get_db() instead. Will be removed in v2.0.",
            DeprecationWarning,
            stacklevel=2
        )
        # ... rest of implementation
```

To see deprecation warnings during development:

```bash
python -W default::DeprecationWarning -c "from database.connection import DatabaseManager; db = DatabaseManager()"
```

---

## Testing the Migration

### Verify Backward Compatibility

```python
# Ensure old code still works (with warnings)
from database.connection import DatabaseManager

db = DatabaseManager()
db.init()
assert db.health_check() == True
```

### Verify New Pattern

```python
from database.connection import get_db_provider, get_db

# Test provider
provider = get_db_provider()
provider.init()
assert provider.health_check() == True

# Test session generator
for session in get_db():
    assert session is not None
    session.execute("SELECT 1")
```

---

## Rollback Plan

If issues occur during migration:

1. **Keep backward compatibility**: Old code continues to work
2. **Revert specific modules**: Git revert individual migration commits
3. **Re-enable DatabaseManager**: Remove deprecation warning if needed

---

## Support

For questions about this migration:

1. Check this guide first
2. Review `python/database/connection.py` for implementation details
3. Create a GitHub issue with the `database-migration` label

---

*Migration Guide v1.0 - Last Updated: December 2024*
