# SQLAlchemy Developer Guide for Heimdex

**Version**: 1.0
**Last Updated**: 2025-10-29
**Target Audience**: Developers working on Heimdex services

---

## Table of Contents

1. [Quick Start](#quick-start)
2. [Architecture Overview](#architecture-overview)
3. [Common Patterns](#common-patterns)
4. [Repository Layer](#repository-layer)
5. [Anti-Patterns to Avoid](#anti-patterns-to-avoid)
6. [Query Optimization](#query-optimization)
7. [Testing with SQLAlchemy](#testing-with-sqlalchemy)
8. [Debugging](#debugging)
9. [Migration Workflow](#migration-workflow)
10. [Troubleshooting](#troubleshooting)

---

## Quick Start

### Basic Usage

```python
from heimdex_common.db import get_db
from heimdex_common.repositories import JobRepository

# Always use context manager for automatic transaction management
with get_db() as session:
    repo = JobRepository(session)

    # Create a job
    job = repo.create_job(
        org_id=your_org_id,
        job_type="mock_process",
    )

    # Session auto-commits on successful exit
    # Session auto-rolls back on exception
```

### Key Principles

1. **Always use `get_db()` context manager** - Handles transactions automatically
2. **Use repositories, not models directly** - Encapsulates business logic
3. **Never bypass the session** - All database operations must go through session
4. **Let exceptions propagate** - Context manager handles rollback

---

## Architecture Overview

### Layered Architecture

```
┌─────────────────────────────────────────────┐
│           API / Worker Layer                 │
│   (FastAPI endpoints, Dramatiq actors)       │
└─────────────────┬───────────────────────────┘
                  │ Uses
┌─────────────────▼───────────────────────────┐
│         Repository Layer                     │
│   (JobRepository, future: AssetRepository)   │
│                                              │
│   - Business logic                           │
│   - Data access abstraction                  │
│   - Query builders                           │
└─────────────────┬───────────────────────────┘
                  │ Uses
┌─────────────────▼───────────────────────────┐
│         ORM Layer (SQLAlchemy)               │
│   (Job, JobEvent models)                     │
│                                              │
│   - Schema definition                        │
│   - Relationships                            │
│   - Validations                              │
└─────────────────┬───────────────────────────┘
                  │
┌─────────────────▼───────────────────────────┐
│         Database Layer                       │
│   (PostgreSQL)                               │
│                                              │
│   - Data persistence                         │
│   - Constraints enforcement                  │
│   - Indexes                                  │
└─────────────────────────────────────────────┘
```

### Directory Structure

```
packages/common/src/heimdex_common/
├── models.py              # SQLAlchemy ORM models
├── db.py                  # Session management, engine config
├── config.py              # Database connection config
└── repositories/
    ├── __init__.py
    └── job_repository.py  # Data access layer for Job
```

---

## Common Patterns

### 1. Creating Records

```python
from uuid import uuid4
from heimdex_common.db import get_db
from heimdex_common.repositories import JobRepository

def create_job_example(org_id: UUID, job_type: str):
    """Create a new job."""
    with get_db() as session:
        repo = JobRepository(session)

        job = repo.create_job(
            org_id=org_id,
            job_type=job_type,
            idempotency_key="unique-key-123",  # Optional
            requested_by="user@example.com",   # Optional
            priority=0,
        )

        # Job is committed when context exits
        return job.id
```

### 2. Reading Records

```python
def get_job_example(job_id: UUID):
    """Retrieve a single job."""
    with get_db() as session:
        repo = JobRepository(session)
        job = repo.get_job_by_id(job_id)

        if not job:
            raise ValueError(f"Job {job_id} not found")

        return {
            "id": str(job.id),
            "status": job.status,
            "type": job.type,
            "created_at": job.created_at.isoformat(),
        }
```

### 3. Updating Records

```python
def update_job_status_example(job_id: UUID, new_status: str):
    """Update a job's status."""
    with get_db() as session:
        repo = JobRepository(session)

        # Simple status update
        repo.update_job_status(
            job_id=job_id,
            status=new_status,
            started_at=datetime.now(UTC) if new_status == "running" else None,
        )

        # Automatically logs job event and commits
```

### 4. Querying Lists

```python
def list_queued_jobs_example(org_id: UUID, limit: int = 10):
    """Get jobs waiting to be processed."""
    with get_db() as session:
        repo = JobRepository(session)
        jobs = repo.get_queued_jobs(
            org_id=org_id,
            limit=limit,
            job_type="mock_process",  # Optional filter
        )

        return [
            {"id": str(job.id), "created_at": job.created_at}
            for job in jobs
        ]
```

### 5. Error Handling

```python
from sqlalchemy.exc import IntegrityError

def create_job_with_error_handling(org_id: UUID, idempotency_key: str):
    """Create job with proper error handling."""
    try:
        with get_db() as session:
            repo = JobRepository(session)
            job = repo.create_job(
                org_id=org_id,
                job_type="mock_process",
                idempotency_key=idempotency_key,
            )
            return job.id

    except IntegrityError as e:
        # Duplicate idempotency key
        if "uq_job_org_idempotency" in str(e):
            raise ValueError(f"Job with key {idempotency_key} already exists")
        raise

    except ValueError as e:
        # Repository-level validation errors
        raise

    except Exception as e:
        # Unexpected errors
        logger.error(f"Unexpected error creating job: {e}")
        raise
```

### 6. Transaction Management

```python
def multi_step_operation_example(org_id: UUID):
    """Multiple operations in single transaction."""
    with get_db() as session:
        repo = JobRepository(session)

        # Step 1: Create job
        job = repo.create_job(org_id=org_id, job_type="complex_job")

        # Step 2: Update status
        repo.update_job_status(job.id, status="running")

        # Step 3: Log additional event
        repo.log_job_event(
            job_id=job.id,
            prev_status="running",
            next_status="running",
            detail_json={"checkpoint": "initialized"},
        )

        # All committed together (or all rolled back if any step fails)
        return job.id
```

---

## Repository Layer

### When to Use Repositories

✅ **Always** - Repositories are the standard way to access data

❌ **Never use models directly** from API/Worker code:

```python
# ❌ BAD - Direct model usage
from heimdex_common.models import Job
with get_db() as session:
    job = session.query(Job).filter(Job.id == job_id).first()

# ✅ GOOD - Use repository
from heimdex_common.repositories import JobRepository
with get_db() as session:
    repo = JobRepository(session)
    job = repo.get_job_by_id(job_id)
```

### Adding New Repository Methods

When you need a new query pattern:

```python
# In packages/common/src/heimdex_common/repositories/job_repository.py

class JobRepository:
    # ... existing methods ...

    def get_jobs_by_type_and_status(
        self,
        org_id: UUID,
        job_type: str,
        status: str,
        limit: int = 100,
    ) -> list[Job]:
        """
        Retrieve jobs filtered by type and status.

        Args:
            org_id: Organization identifier
            job_type: Job type to filter by
            status: Status to filter by
            limit: Maximum number of jobs to return

        Returns:
            List of Job instances matching criteria
        """
        return (
            self.session.query(Job)
            .filter(
                Job.org_id == org_id,
                Job.type == job_type,
                Job.status == status,
            )
            .order_by(desc(Job.created_at))
            .limit(limit)
            .all()
        )
```

### Creating New Repositories

For new tables, create a new repository:

```python
# packages/common/src/heimdex_common/repositories/asset_repository.py

from sqlalchemy.orm import Session
from ..models import Asset

class AssetRepository:
    """Repository for Asset data access."""

    def __init__(self, session: Session):
        self.session = session

    def create_asset(self, job_id: UUID, ...) -> Asset:
        """Create a new asset."""
        asset = Asset(...)
        self.session.add(asset)
        self.session.flush()
        return asset

    # ... more methods ...
```

Don't forget to export it:

```python
# packages/common/src/heimdex_common/repositories/__init__.py

from .job_repository import JobRepository
from .asset_repository import AssetRepository

__all__ = ["JobRepository", "AssetRepository"]
```

---

## Anti-Patterns to Avoid

### 1. ❌ Opening Nested Sessions

```python
# ❌ BAD - Nested sessions
with get_db() as session1:
    repo = JobRepository(session1)
    job = repo.create_job(...)

    with get_db() as session2:  # ❌ Don't nest!
        repo2 = JobRepository(session2)
        # ...
```

**Why bad**: Creates transaction isolation issues, potential deadlocks.

**Solution**: Use single session for related operations.

### 2. ❌ Committing Manually

```python
# ❌ BAD - Manual commit
with get_db() as session:
    repo = JobRepository(session)
    job = repo.create_job(...)
    session.commit()  # ❌ Don't do this!
```

**Why bad**: Context manager handles commit/rollback automatically.

**Solution**: Let context manager handle it.

### 3. ❌ Accessing Relationships After Session Close

```python
# ❌ BAD - Lazy loading after session closes
with get_db() as session:
    repo = JobRepository(session)
    job = repo.get_job_by_id(job_id)

# Session is closed here
events = job.events  # ❌ DetachedInstanceError!
```

**Why bad**: Relationships are lazy-loaded by default, requires active session.

**Solution**: Use eager loading or access relationships inside session:

```python
# ✅ GOOD - Eager loading
with get_db() as session:
    repo = JobRepository(session)
    job = repo.get_job_with_events(job_id)  # Loads events immediately

events = job.events  # ✅ Works, events already loaded
```

### 4. ❌ N+1 Query Problem

```python
# ❌ BAD - N+1 queries
with get_db() as session:
    repo = JobRepository(session)
    jobs = repo.get_queued_jobs(org_id, limit=100)

    for job in jobs:
        events = job.events  # ❌ 1 query per job = 100 queries!
```

**Why bad**: Each iteration triggers a separate query.

**Solution**: Use eager loading:

```python
# ✅ GOOD - Single query with JOIN
from sqlalchemy.orm import joinedload

def get_jobs_with_events(self, org_id: UUID) -> list[Job]:
    return (
        self.session.query(Job)
        .options(joinedload(Job.events))  # ✅ Loads in one query
        .filter(Job.org_id == org_id)
        .all()
    )
```

### 5. ❌ Using `get_db()` Outside Context Manager

```python
# ❌ BAD - Manual session management
session = get_db()  # ❌ Returns generator, not session!
repo = JobRepository(session)
# ...
```

**Why bad**: Skips transaction management, resource leaks.

**Solution**: Always use `with` statement:

```python
# ✅ GOOD
with get_db() as session:
    repo = JobRepository(session)
    # ...
```

### 6. ❌ Raw SQL Queries

```python
# ❌ BAD - Raw SQL
with get_db() as session:
    result = session.execute(
        "SELECT * FROM job WHERE status = 'queued'"
    ).fetchall()
```

**Why bad**: Bypasses ORM benefits, type safety, SQL injection risk.

**Solution**: Use repository methods or ORM queries:

```python
# ✅ GOOD
with get_db() as session:
    repo = JobRepository(session)
    jobs = repo.get_queued_jobs(org_id)
```

**Exception**: Complex queries that ORM can't express efficiently:

```python
# ✅ OK - Use text() for complex raw SQL
from sqlalchemy import text

with get_db() as session:
    result = session.execute(
        text("""
            SELECT status, COUNT(*) as count
            FROM job
            WHERE org_id = :org_id
            GROUP BY status
        """),
        {"org_id": org_id}  # Always use parameters!
    ).mappings().all()
```

---

## Query Optimization

### 1. Use Indexes Effectively

Check if your query uses indexes:

```python
# In psql:
EXPLAIN ANALYZE
SELECT * FROM job
WHERE org_id = '...' AND status = 'queued'
ORDER BY created_at;

# Should see:
# Index Scan using idx_job_org_status on job
```

### 2. Eager Loading with `joinedload()`

For one-to-many relationships:

```python
from sqlalchemy.orm import joinedload

def get_job_with_events(self, job_id: UUID) -> Job:
    """Get job with all events in single query."""
    return (
        self.session.query(Job)
        .options(joinedload(Job.events))  # Single JOIN query
        .filter(Job.id == job_id)
        .first()
    )
```

### 3. Load Only Required Columns

```python
from sqlalchemy.orm import load_only

def get_job_ids_by_status(self, org_id: UUID, status: str) -> list[UUID]:
    """Get only job IDs, not full records."""
    jobs = (
        self.session.query(Job)
        .options(load_only(Job.id))  # Only load ID column
        .filter(Job.org_id == org_id, Job.status == status)
        .all()
    )
    return [job.id for job in jobs]
```

### 4. Use `exists()` for Existence Checks

```python
from sqlalchemy import exists

def job_exists(self, job_id: UUID) -> bool:
    """Check if job exists (faster than fetching full record)."""
    return self.session.query(
        exists().where(Job.id == job_id)
    ).scalar()
```

### 5. Batch Operations with `bulk_insert_mappings()`

```python
def create_many_jobs(self, jobs_data: list[dict]) -> None:
    """Create multiple jobs efficiently."""
    self.session.bulk_insert_mappings(Job, jobs_data)
    self.session.flush()
```

### 6. Use Connection Pooling

Already configured in `packages/common/src/heimdex_common/db.py`:

```python
engine = create_engine(
    database_url,
    pool_size=5,          # 5 persistent connections
    max_overflow=10,      # Up to 10 additional on demand
    pool_pre_ping=True,   # Verify connections before use
    pool_recycle=300,     # Recycle connections after 5 minutes
)
```

---

## Testing with SQLAlchemy

### Unit Testing with In-Memory Database

```python
# tests/conftest.py
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from heimdex_common.models import Base

@pytest.fixture
def session():
    """Provide a test database session."""
    # Use in-memory SQLite for speed
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)

    SessionLocal = sessionmaker(bind=engine)
    session = SessionLocal()

    yield session

    session.close()

# tests/test_job_repository.py
from uuid import uuid4
from heimdex_common.repositories import JobRepository

def test_create_job(session):
    """Test job creation."""
    repo = JobRepository(session)

    org_id = uuid4()
    job = repo.create_job(
        org_id=org_id,
        job_type="test_job",
    )

    assert job.id is not None
    assert job.status == "queued"
    assert job.org_id == org_id
    assert job.type == "test_job"

def test_get_job_by_id(session):
    """Test job retrieval."""
    repo = JobRepository(session)

    # Create job
    job = repo.create_job(org_id=uuid4(), job_type="test")
    session.commit()

    # Retrieve job
    retrieved = repo.get_job_by_id(job.id)

    assert retrieved is not None
    assert retrieved.id == job.id
```

### Integration Testing with Test Database

```python
# Use Docker for test database
# docker-compose.test.yml
services:
  test-db:
    image: postgres:15
    environment:
      POSTGRES_DB: heimdex_test
      POSTGRES_USER: test
      POSTGRES_PASSWORD: test
    ports:
      - "5433:5432"

# tests/integration/conftest.py
import pytest
from heimdex_common.db import get_engine, create_tables, drop_tables

@pytest.fixture(scope="session")
def test_engine():
    """Create test database engine."""
    engine = get_engine()  # Uses TEST_DATABASE_URL env var
    create_tables()
    yield engine
    drop_tables()

@pytest.fixture
def session(test_engine):
    """Provide a clean session for each test."""
    from heimdex_common.db import get_session_factory

    SessionLocal = get_session_factory()
    session = SessionLocal()

    yield session

    session.rollback()  # Rollback any changes
    session.close()
```

### Mocking for Fast Tests

```python
# tests/test_api_mocked.py
from unittest.mock import Mock, MagicMock
from heimdex_api.jobs import create_job

def test_create_job_endpoint(mocker):
    """Test job creation endpoint with mocked database."""
    # Mock the repository
    mock_repo = Mock()
    mock_repo.create_job.return_value = Mock(
        id=uuid4(),
        status="queued",
    )

    mocker.patch("heimdex_api.jobs.JobRepository", return_value=mock_repo)

    # Test endpoint
    response = create_job(JobCreateRequest(type="mock_process"))

    assert response.job_id is not None
    mock_repo.create_job.assert_called_once()
```

---

## Debugging

### 1. Enable SQL Logging

Temporarily enable query logging:

```python
# In packages/common/src/heimdex_common/db.py
engine = create_engine(
    database_url,
    echo=True,  # 🔧 Enable SQL logging
)
```

Output:
```
INFO sqlalchemy.engine.Engine SELECT job.id, job.status, ...
INFO sqlalchemy.engine.Engine {'job_id': UUID('...')}
```

### 2. Use `EXPLAIN ANALYZE`

Check query performance:

```python
from sqlalchemy import text

with get_db() as session:
    result = session.execute(
        text("EXPLAIN ANALYZE SELECT * FROM job WHERE status = :status"),
        {"status": "queued"}
    ).fetchall()

    for row in result:
        print(row[0])
```

### 3. Inspect Generated SQL

```python
from sqlalchemy import select
from heimdex_common.models import Job

query = select(Job).where(Job.status == "queued")
print(str(query.compile(compile_kwargs={"literal_binds": True})))

# Output: SELECT job.id, job.status, ... WHERE job.status = 'queued'
```

### 4. Debug Lazy Loading Issues

```python
# Add this to catch lazy loading after session closes
from sqlalchemy.orm import lazyload

with get_db() as session:
    job = session.query(Job).options(lazyload('*')).first()
    # Any lazy load attempt will fail immediately
```

### 5. Profile Query Performance

```python
import time

with get_db() as session:
    start = time.perf_counter()

    repo = JobRepository(session)
    jobs = repo.get_queued_jobs(org_id, limit=1000)

    elapsed = time.perf_counter() - start
    print(f"Query took {elapsed*1000:.2f}ms")
```

---

## Migration Workflow

### Creating New Migrations

```bash
# 1. Make changes to models in packages/common/src/heimdex_common/models.py

# 2. Generate migration
cd packages/common
alembic revision --autogenerate -m "Add asset table"

# 3. Review generated migration
cat alembic/versions/<revision>_add_asset_table.py

# 4. Edit if needed (autogenerate isn't perfect)

# 5. Test migration on clean database
alembic upgrade head

# 6. Test downgrade
alembic downgrade -1
```

### Migration Best Practices

1. **Always review autogenerated migrations** - Fix any issues

2. **Test both upgrade and downgrade** - Ensure reversibility

3. **Never edit applied migrations** - Create new migration instead

4. **Use descriptive names**:
   ```bash
   alembic revision --autogenerate -m "add_asset_table_with_indexes"
   ```

5. **Add data migrations when needed**:
   ```python
   def upgrade():
       # Schema change
       op.add_column('job', sa.Column('new_field', sa.String()))

       # Data migration
       op.execute("""
           UPDATE job SET new_field = 'default_value'
           WHERE new_field IS NULL
       """)
   ```

### Common Migration Commands

```bash
# Show current version
alembic current

# Show history
alembic history --verbose

# Upgrade to latest
alembic upgrade head

# Upgrade to specific version
alembic upgrade <revision>

# Downgrade one version
alembic downgrade -1

# Downgrade to specific version
alembic downgrade <revision>

# Downgrade all
alembic downgrade base

# Generate SQL without executing
alembic upgrade head --sql > migration.sql
```

---

## Troubleshooting

### Error: "DetachedInstanceError: Instance is not bound to a Session"

**Cause**: Trying to access lazy-loaded relationships after session closes.

**Solution**:
```python
# ✅ Load relationships before session closes
with get_db() as session:
    repo = JobRepository(session)
    job = repo.get_job_with_events(job_id)  # Eager load
    events = job.events  # Access inside session

# Now you can use job.events outside session
```

### Error: "ResourceClosedError: This Connection is closed"

**Cause**: Trying to use session after context manager exits.

**Solution**: Move all database operations inside `with` block:
```python
with get_db() as session:
    repo = JobRepository(session)
    job = repo.get_job_by_id(job_id)
    # Do everything here
```

### Error: "IntegrityError: duplicate key value violates unique constraint"

**Cause**: Trying to insert duplicate on unique field (e.g., idempotency_key).

**Solution**: Catch and handle:
```python
try:
    job = repo.create_job(...)
except IntegrityError as e:
    if "uq_job_org_idempotency" in str(e):
        # Handle duplicate idempotency key
        raise ValueError("Job already exists")
    raise
```

### Error: "OperationalError: (psycopg2.OperationalError) connection already closed"

**Cause**: Database connection lost (network issue, timeout, etc.).

**Solution**: Retry with exponential backoff:
```python
from tenacity import retry, stop_after_attempt, wait_exponential

@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=10)
)
def resilient_create_job(...):
    with get_db() as session:
        repo = JobRepository(session)
        return repo.create_job(...)
```

### Slow Queries

**Diagnosis**:
```bash
# Enable slow query logging in PostgreSQL
ALTER DATABASE heimdex SET log_min_duration_statement = 100; # Log queries > 100ms

# Check pg_stat_statements
SELECT query, mean_exec_time, calls
FROM pg_stat_statements
ORDER BY mean_exec_time DESC
LIMIT 10;
```

**Solutions**:
1. Add missing indexes
2. Use eager loading for relationships
3. Reduce number of queries (N+1 problem)
4. Use `load_only()` to load fewer columns

---

## Quick Reference

### Common Imports

```python
# Database session
from heimdex_common.db import get_db

# Repositories
from heimdex_common.repositories import JobRepository

# Models (only for type hints, never query directly!)
from heimdex_common.models import Job, JobEvent

# SQLAlchemy utilities
from sqlalchemy import desc, func, text, and_, or_
from sqlalchemy.orm import joinedload, load_only
from sqlalchemy.exc import IntegrityError, OperationalError

# Standard library
from uuid import UUID, uuid4
from datetime import datetime, UTC
```

### Session Usage Template

```python
def my_database_operation(job_id: UUID):
    """Template for database operations."""
    try:
        with get_db() as session:
            repo = JobRepository(session)

            # Your operations here
            job = repo.get_job_by_id(job_id)

            # All commits automatically when exiting 'with' block
            return job

    except IntegrityError as e:
        # Handle constraint violations
        raise

    except ValueError as e:
        # Handle repository-level errors
        raise

    except Exception as e:
        # Log unexpected errors
        logger.error(f"Database error: {e}")
        raise
```

---

## Additional Resources

- [SQLAlchemy 2.0 Documentation](https://docs.sqlalchemy.org/en/20/)
- [Alembic Documentation](https://alembic.sqlalchemy.org/)
- [Heimdex Migration Report](./MIGRATION_REPORT.md)
- [Heimdex DB Schema](./db-schema.md)

---

**Guide Version**: 1.0
**Last Updated**: 2025-10-29
**Maintained By**: Heimdex Engineering Team
