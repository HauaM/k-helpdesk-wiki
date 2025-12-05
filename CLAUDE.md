# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

KHW (K Help Desk Wiki) is a customer support knowledge management system that automatically generates and manages manuals based on consultation history. It uses vector search for similarity matching and LLM-based content generation with hallucination prevention.

**Key Technology Stack:**
- Python 3.10+ with FastAPI (async)
- SQLAlchemy 2.0 (mapped_column, AsyncSession)
- MCP (Model Context Protocol) server for Claude integration
- Abstract interfaces for VectorStore and LLM providers

## Development Commands

### Running the Application

```bash
# Start FastAPI server (development mode with auto-reload)
uv run python main.py

# Or with uvicorn directly
uv run uvicorn app.api.main:app --reload

# Start MCP server for Claude integration
uv run python mcp_server.py
```

### Testing

```bash
# Run all tests
uv run pytest

# Run with coverage report
uv run pytest --cov=app tests/

# Run specific test file
uv run pytest tests/unit/test_consultation_service.py

# Run specific test function
uv run pytest tests/unit/test_consultation_service.py::test_register_consultation
```

### Code Quality

```bash
# Format code with Black
uv run black app/ tests/

# Lint with Ruff
uv run ruff check app/ tests/

# Type checking with mypy
uv run mypy app/
```

### Database Migrations

```bash
# Create new migration
uv run alembic revision --autogenerate -m "Description of changes"

# Apply migrations
uv run alembic upgrade head

# Rollback one migration
uv run alembic downgrade -1
```

## Architecture

### Layered Architecture Principles

The codebase follows strict layering with dependency injection:

1. **API Layer** (`app/api/`, `app/routers/`): FastAPI endpoints, HTTP-specific concerns
2. **Service Layer** (`app/services/`): Pure business logic, FastAPI-independent, MCP-compatible
3. **Repository Layer** (`app/repositories/`): Data access (RDB + VectorStore)
4. **Model Layer** (`app/models/`): SQLAlchemy 2.0 models with mapped_column

**Critical Rule: Services MUST NOT depend on FastAPI types.** Services receive/return pure Python types (Pydantic models, primitives) to enable both HTTP API and MCP usage.

### Dual Storage System

**RDB (PostgreSQL) = Source of Truth**
- All official data stored in PostgreSQL
- JSONB fields for flexible metadata
- GIN indexes for JSONB queries

**VectorStore = Search Index**
- Abstract protocol (`app/vectorstore/protocol.py`) allows swapping implementations
- Two separate indices: `consultation` and `manual`
- Mock implementation for development (`vectorstore_type=mock` in .env)
- Production options: pgvector, Pinecone, Qdrant

If VectorStore fails, RDB data remains intact. Services should handle VectorStore errors gracefully.

### LLM Integration

LLM clients follow the protocol pattern (`app/llm/protocol.py`):
- `mock`: Development mode with predefined responses
- `openai`: OpenAI GPT models
- `anthropic`: Anthropic Claude models

**Hallucination Prevention Rule**: LLMs should only summarize/organize existing consultation content, never create new facts. All prompts should include source text as context.

### MCP Server Integration

The MCP server (`app/mcp/server.py`) exposes KHW functionality to Claude:
- Uses the same service layer as the FastAPI application
- Tools defined in `app/mcp/tools.py`
- Configured via `claude_desktop_config.json`

**Available MCP Tools:**
- `create_consultation`: Save new consultation records
- `search_consultations`: Find similar consultations by semantic search
- `generate_manual_draft`: Create manual from consultation using LLM
- `search_manuals`: Semantic search across manual entries
- `list_review_tasks`: Show pending manual review tasks
- `approve_review_task`: Approve manual changes
- `reject_review_task`: Reject manual changes with reason

### Queue System (Optional)

Async queue abstraction (`app/queue/`) supports:
- Retry queue for failed operations
- Dead Letter Queue (DLQ) for permanent failures
- Currently optional; enable with Celery + Redis in production

## Initial Setup

### First-Time Setup

```bash
# 1. Clone and navigate
cd /path/to/k-helpdesk-wiki

# 2. Install dependencies with UV (all groups including dev)
uv sync --all-groups

# 3. Copy environment file
cp .env.example .env

# 4. Verify setup by running health check
uv run python main.py
# Open browser to http://localhost:8000/health

# 5. Run a quick test
uv run pytest tests/ -k "test_" --co -q  # List available tests (don't run them)
```

### Verifying Your Setup

```bash
# Test the FastAPI server starts without errors
uv run python main.py &
sleep 2
curl http://localhost:8000/health
# Should return: {"status":"ok","app":"KHW","version":"0.1.0","environment":"development"}

# Test MCP server (separate terminal)
uv run python mcp_server.py
# Should show: "mcp_server_running transport=stdio"

# Run code quality checks
uv run black app/ tests/ --check  # Check formatting
uv run ruff check app/ tests/     # Lint
uv run mypy app/                  # Type checking
```

## Key Design Patterns

### Protocol-Based Abstractions

VectorStore and LLM use Protocol classes (structural subtyping), not ABC:
- `VectorStoreProtocol` in `app/vectorstore/protocol.py`
- `LLMClientProtocol` in `app/llm/protocol.py`

Implementations must match protocol signatures exactly. This enables clean dependency injection and testing.

### Repository Pattern

Repositories (`app/repositories/`) encapsulate all data access:
- `ConsultationRepository` / `ConsultationRDBRepository`: CRUD for consultations
- `ManualRepository` / `ManualRDBRepository`: CRUD for manuals, versions, review tasks
- `TaskRepository`: Review task queries
- `UserRepository`: User/admin management
- Inherit from `BaseRepository` for common operations

### Dependency Injection in Routers

Services are instantiated in router endpoints via FastAPI `Depends()`:

```python
def get_consultation_service(
    session: AsyncSession = Depends(get_session),
) -> ConsultationService:
    return ConsultationService(
        session=session,
        vectorstore=get_consultation_vectorstore(),
        retry_queue=_retry_queue,
    )

@router.post("/consultations")
async def create_consultation(
    data: ConsultationCreate,
    service: ConsultationService = Depends(get_consultation_service),
) -> ConsultationResponse:
    return await service.register_consultation(data)
```

This pattern:
- Keeps services testable (can inject mocks)
- Services remain FastAPI-agnostic (pure Python types only)
- Same services are reused by MCP server

### Search Strategy

Vector search + metadata filtering:
1. VectorStore returns Top-K candidates by semantic similarity
2. RDB filters by metadata (branch_code, business_type, error_code)
3. Results re-ranked by similarity threshold
4. Below threshold = "no similar items found"

Search is configured via `.env`:
```
SEARCH_TOP_K=10  # How many candidates to pull from VectorStore
SEARCH_SIMILARITY_THRESHOLD=0.7  # Min score to consider a match (0-1)
```

## Configuration

All configuration via environment variables (`.env` file).

### Setup

```bash
# Copy the example environment file
cp .env.example .env

# Edit .env with your settings (for development, defaults are usually fine)
```

### Key Configuration Options

**VectorStore Type Selection:**
```bash
VECTORSTORE_TYPE=mock  # Options: mock, pgvector, pinecone, qdrant
VECTORSTORE_DIMENSION=1536  # Embedding dimension (OpenAI default)
```

**LLM Provider Selection:**
```bash
LLM_PROVIDER=mock  # Options: mock, openai, anthropic
LLM_MODEL=gpt-4-turbo-preview
LLM_TEMPERATURE=0.3  # Lower = more deterministic, higher = more creative
LLM_MAX_TOKENS=2000
```

**Database (PostgreSQL):**
```bash
DATABASE_URL=postgresql+asyncpg://user:pass@localhost:5432/khw
DATABASE_POOL_SIZE=5  # Connection pool size
DATABASE_MAX_OVERFLOW=10  # Max overflow connections
```

**Search Tuning:**
```bash
SEARCH_TOP_K=10  # Number of vector candidates to retrieve
SEARCH_SIMILARITY_THRESHOLD=0.7  # Minimum similarity score (0-1)
MANUAL_SIMILARITY_THRESHOLD=0.85  # Higher threshold for manual updates
```

**API Keys (for production):**
```bash
OPENAI_API_KEY=sk-...
ANTHROPIC_API_KEY=sk-ant-...
```

**Development Defaults:**
- `VECTORSTORE_TYPE=mock` uses in-memory storage (no PostgreSQL needed)
- `LLM_PROVIDER=mock` returns predefined responses
- Can run tests without any external services

## Current Development Status

**Completed:**
- Project structure with layered architecture
- Core configuration, logging, and error handling
- SQLAlchemy 2.0 models for all entities
- Pydantic schemas for request/response
- Repository layer implementation
- Abstract protocols for VectorStore and LLM
- Mock implementations for development
- FastAPI routers and API structure with dependency injection
- MCP server integration for Claude
- Service layer business logic (consultation, manual, tasks)
- Queue system (in-memory retry queue + DLQ abstraction)
- Logging and metrics infrastructure

**In Progress / Partially Implemented:**
- Real VectorStore connection (pgvector/Pinecone/Qdrant)
- Real LLM provider integration (OpenAI/Anthropic clients)
- Manual conflict detection algorithm
- Review workflow state machine

**TODO:**
- Comprehensive test coverage (unit and integration tests)
- Database migrations and schema initialization
- PII data encryption/masking for sensitive consultation content
- RBAC (Role-Based Access Control) implementation
- Hallucination validation logic for LLM outputs

## Important Files

- `docs/KHW_RFP.md`: Complete requirements specification
- `docs/MCP_SETUP.md`: Detailed MCP server setup instructions
- `.env.example`: Environment variable template (copy to `.env` for development)
- `app/core/config.py`: Centralized configuration with Pydantic Settings
- `app/core/exceptions.py`: Custom exception hierarchy
- `app/core/db.py`: Database initialization and session management
- `app/models/consultation.py`: Consultation domain model
- `app/models/manual.py`: Manual entry, version, and review task models
- `app/services/consultation_service.py`: Main consultation business logic
- `app/services/manual_service.py`: Manual generation and management logic
- `app/services/task_service.py`: Review task workflow logic
- `app/vectorstore/protocol.py`: Abstract VectorStore interface
- `app/llm/protocol.py`: Abstract LLM client interface

**Note**: The README.md is in Korean (한국어). Key Korean terms:
- 상담 = Consultation
- 메뉴얼 = Manual
- 환각(Hallucination) = Prevents LLM from inventing new facts
- 유사 검색 = Semantic similarity search

## Working with This Codebase

### Adding a New Feature

1. **Define Pydantic schemas** in `app/schemas/` (request/response DTOs)
2. **Update SQLAlchemy models** in `app/models/` if needed
3. **Add repository methods** in `app/repositories/` for data access
4. **Write service business logic** in `app/services/` (must be FastAPI-independent)
5. **Create FastAPI router** in `app/routers/` with `Depends()` for service injection
6. **(Optional) Expose as MCP tool** in `app/mcp/tools.py` if Claude should access it
7. **Write tests** in `tests/unit/` and `tests/integration/`

**Important**: Tests should test the service layer directly, not through HTTP endpoints. This keeps tests fast and decouples them from FastAPI.

### Modifying Existing Services

When modifying service logic (e.g., `ConsultationService`):
- Keep the service constructor signature stable (parameters in `__init__`)
- Return Pydantic models or primitives, never FastAPI types
- Raise custom exceptions from `app/core/exceptions.py`
- Services used by both API routers AND MCP server must be fully compatible

### Changing VectorStore Implementation

1. Create new class implementing `VectorStoreProtocol` from `app/vectorstore/protocol.py`
2. Add to `app/vectorstore/` directory
3. Update factory in `app/vectorstore/__init__.py`
4. Set `VECTORSTORE_TYPE=<type>` in `.env`
5. For each index type (consultation/manual), implement these methods:
   - `index()`: Add or update documents
   - `search()`: Retrieve top-K by similarity
   - `delete()`: Remove documents

### Changing LLM Provider

1. Create new class implementing `LLMClientProtocol` from `app/llm/protocol.py`
2. Add to `app/llm/` directory
3. Update factory in `app/llm/__init__.py`
4. Set `LLM_PROVIDER=<type>` and API key in `.env`
5. Implement required methods:
   - `generate()`: Create text from prompt
   - Follow hallucination prevention rule: always include source context in prompts

## Testing Guidelines

### Test Structure

```
tests/
├── unit/                  # Test individual services/functions
│   ├── test_consultation_service.py
│   ├── test_manual_service.py
│   └── test_task_service.py
└── integration/           # Test across layers (service + repo)
    ├── test_consultation_flow.py
    └── test_manual_generation.py
```

### Writing Tests

**Unit Tests (Service Layer):**
- Mock `VectorStore` and `LLM` client
- Mock `Repository` if testing service in isolation
- Focus on business logic only
- Fast execution (no I/O)

Example:
```python
@pytest.mark.asyncio
async def test_register_consultation():
    service = ConsultationService(
        session=mock_session,
        vectorstore=mock_vectorstore,
        retry_queue=mock_queue,
    )
    result = await service.register_consultation(data)
    assert result.id is not None
```

**Integration Tests:**
- Use real repository layer (with test database)
- Can mock VectorStore/LLM if not testing those
- Test complete workflows (service + data access)
- Use `pytest.fixture` for async setup

**MCP Tools:**
- Test end-to-end with real services when possible
- MCP tools are thin wrappers around services
- Focus testing on service layer, not MCP glue code

### Running Tests

```bash
# All tests
uv run pytest

# With coverage
uv run pytest --cov=app tests/

# Specific test file
uv run pytest tests/unit/test_consultation_service.py -v

# Specific test function
uv run pytest tests/unit/test_consultation_service.py::test_register_consultation -v

# Run only integration tests
uv run pytest tests/integration/ -v
```

### Test Configuration

- `asyncio_mode = "auto"` in `pyproject.toml` enables pytest-asyncio for all async tests
- Fixtures in `tests/conftest.py` (session/database setup)
- Mock implementations in `app/vectorstore/mock.py` and `app/llm/mock.py`

## Common Gotchas & Tips

### Service Layer Independence

**Problem**: Accidentally importing FastAPI types in services
```python
# ❌ WRONG - Don't do this
from fastapi import HTTPException
class ConsultationService:
    def register(...) -> HTTPException:  # NO!
        ...
```

**Solution**: Services return Pydantic models or primitives; raise custom exceptions
```python
# ✅ CORRECT
from app.core.exceptions import ValidationError
class ConsultationService:
    def register(...) -> ConsultationResponse:
        raise ValidationError("Invalid data")
```

### Database Session Management

- Services receive `AsyncSession` in constructor, don't create their own
- Repository methods handle committing transactions (via the session)
- For read-only operations, session doesn't need explicit commit
- Always `await` async repository calls

### Vector Search Results

- VectorStore returns results by similarity score (0-1), always sorted
- Must apply `SEARCH_SIMILARITY_THRESHOLD` filter after getting results
- If no results meet threshold, return empty list (not an error)
- Vector indices must be rebuilt when models change significantly

### MCP Server Context

- MCP server shares the same service layer as FastAPI
- Each MCP tool call gets a fresh database session
- Tools should be simple wrappers around services (no extra logic)
- Test MCP tools end-to-end in `claude_desktop_config.json` context

### Configuration & Environment

- `.env` overrides all defaults in `app/core/config.py`
- `VECTORSTORE_TYPE=mock` and `LLM_PROVIDER=mock` enable zero-dependency development
- API keys (OPENAI_API_KEY, etc.) only required when using real providers
- Debug info (like SQL query logging) requires `DATABASE_ECHO=true`

### Type Hints

- Codebase requires strict mypy (`strict = true` in `pyproject.toml`)
- Use `Optional[X]` not `X | None` for compatibility
- Async functions must explicitly return `Awaitable[T]` or just `T` (return value type)
- When writing new code, always run `uv run mypy app/` to catch type errors early

### Async/Await Pattern

- All DB queries and VectorStore operations are async
- Always `await` when calling async methods
- Router handlers are async by default (FastAPI handles it)
- Use `async def` for any function calling async functions

### Import Organization

- `from app.` imports work from any module location
- Avoid circular imports (service → repo is OK, repo → service is NOT)
- Models should not import services; services import models
