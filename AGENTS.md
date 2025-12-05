# Repository Guidelines

## Project Structure & Modules
- Core code lives in `app/` with clear layers: `api`/`routers` (FastAPI entrypoints), `services` (business logic, FastAPI-agnostic), `repositories` (RDB/vector access), `models` (SQLAlchemy), `schemas` (Pydantic DTOs), `vectorstore` and `llm` (protocols + impls), `queue` (retry/DLQ), `mcp` (Claude tools). Tests sit in `tests/`; docs in `docs/`; entrypoints are `main.py` (API) and `mcp_server.py` (MCP).

## Build, Test, and Development Commands
- Install: `uv sync --all-groups` (installs runtime + dev deps). Set up env from `.env.example`.
- Run API: `uv run python main.py` or `uv run uvicorn app.api.main:app --reload`.
- Run MCP server: `uv run python mcp_server.py` (stdio transport).
- Lint/format/type-check: `uv run black app/ tests/ --check`; `uv run ruff check app/ tests/`; `uv run mypy app/`.
- Tests: `uv run pytest`; with coverage `uv run pytest --cov=app tests/`.
- Migrations: `uv run alembic revision --autogenerate -m "msg"`; apply with `uv run alembic upgrade head`.

## Coding Style & Naming Conventions
- Python 3.10+, async-first. Follow Black line length 100 and Ruff defaults; prefer type hints everywhere (`mypy` strict). Keep services free of FastAPI types; inject dependencies at routers. Use `snake_case` for modules/functions, `PascalCase` for models/schemas/services, UPPER_SNAKE for constants. Keep prompts/config in `app/llm/` and vector logic in `app/vectorstore/`; avoid cross-layer imports that break the API/service/repo boundaries.

## Testing Guidelines
- Pytest with `pytest-asyncio`; tests live in `tests/` following `test_*.py` and `Test*` classes. Use `--cov=app` for coverage; prefer unit tests on services and repositories with mocks for LLM/vectorstore. Name tests after behavior (`test_register_consultation_returns_id`). When adding async code, mark with `@pytest.mark.asyncio`.

## Commit & Pull Request Guidelines
- Match existing history: Conventional Commits style (`feat: ...`, `fix: ...`, etc.; can be Korean or English). Keep commits focused; include migrations and updated tests in the same commit when applicable.
- PRs should include: summary of change, linked issue/task, how to run/verify (commands above), and notes on schema or config changes. Add screenshots or sample payloads for API-affecting changes; mention MCP tool additions explicitly. Avoid mixing refactors with feature work unless tightly coupled.

## Security & Configuration Tips
- Never commit secrets; keep real keys in `.env`. Default dev mode uses mock vectorstore/LLM; note when switching to cloud providers. If enabling PostgreSQL, confirm `DATABASE_URL` and run migrations. Review prompts to ensure hallucination-prevention context is included; services should not invent data beyond provided consultation content.
