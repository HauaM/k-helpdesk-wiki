# KHW - K Help Desk Wiki

고객 상담 지식 관리 시스템 (Knowledge Helpdesk Wiki)

## Overview

KHW는 고객 상담 내역을 기반으로 메뉴얼을 자동 생성하고, 검토/승인/버전 관리까지 제공하는 지식 관리 시스템입니다.

**주요 기능**
- 상담 등록 및 벡터 기반 유사 상담/메뉴얼 검색
- LLM 기반 메뉴얼 초안 생성 및 비교(diff) 지원
- 메뉴얼 검토 태스크 및 승인 워크플로우
- 메뉴얼 버전 관리 (APPROVED/DEPRECATED/DRAFT)
- 공통 코드/부서/사용자 관리 및 역할 기반 접근 제어

## Architecture

```
app/
├── api/           # FastAPI 앱 팩토리, 미들웨어, 에러 핸들러
├── routers/       # FastAPI 라우터
├── services/      # 비즈니스 로직 (FastAPI 독립)
├── repositories/  # RDB/VectorStore 접근
├── models/        # SQLAlchemy 모델
├── schemas/       # Pydantic 스키마 (DTO)
├── vectorstore/   # VectorStore 추상화 + 구현체
├── llm/           # LLM 클라이언트 + 프롬프트
├── queue/         # Retry/DLQ 추상화
├── mcp/           # MCP 서버 (Claude 연동)
└── core/          # 설정, DB, 로깅, 보안
```

**Entrypoints**
- API: `main.py`
- MCP: `mcp_server.py`

## Quick Start

### Prerequisites

- Python 3.12+
- PostgreSQL 15+ (필수, Async SQLAlchemy 사용)
- Redis (선택, 큐 사용 시)

### Installation

```bash
uv sync --all-groups
```

### Environment setup

```bash
cp .env.example .env
# Edit .env with your configuration
```

### Database migration

```bash
uv run alembic current
uv run alembic upgrade head
or
uv run python -m alembic current
uv run python -m alembic upgrade head
```

### Run API

```bash
uv run python main.py
# or
uv run uvicorn app.api.main:app --reload --host 0.0.0.0 --port 8000
```

### Run MCP server

```bash
uv run python mcp_server.py
```

### API Docs

- Swagger: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc
- Health: http://localhost:8000/health

## MCP (Claude)

Claude Desktop/웹에서 MCP 서버로 접근할 수 있습니다.

```json
{
  "mcpServers": {
    "khw": {
      "command": "uv",
      "args": ["run", "python", "/절대경로/k-helpdesk-wiki/mcp_server.py"],
      "env": {
        "PYTHONPATH": "/절대경로/k-helpdesk-wiki"
      }
    }
  }
}
```

자세한 설정은 `docs/MCP_SETUP.md`를 참고하세요.

## API Endpoints (대표)

### Auth
- `POST /api/v1/auth/signup`
- `POST /api/v1/auth/login`
- `GET /api/v1/auth/me`

### Consultations
- `POST /api/v1/consultations`
- `GET /api/v1/consultations/search`
- `GET /api/v1/consultations/{consultation_id}`

### Manuals
- `POST /api/v1/manuals/draft`
- `POST /api/v1/manuals/approve/{manual_id}`
- `GET /api/v1/manuals`
- `GET /api/v1/manuals/search`
- `GET /api/v1/manuals/versions?business_type=...&error_code=...`
- `GET /api/v1/manuals/{manual_id}`
- `PUT /api/v1/manuals/{manual_id}`
- `DELETE /api/v1/manuals/{manual_id}`
- `GET /api/v1/manuals/{manual_id}/versions`
- `GET /api/v1/manuals/{manual_id}/versions/{version}`
- `GET /api/v1/manuals/{manual_id}/diff`
- `GET /api/v1/manuals/{manual_id}/approved-group`
- `GET /api/v1/manuals/{manual_id}/review-tasks`
- `GET /api/v1/manuals/drafts/{draft_id}/diff-with-active`

### Manual Review Tasks
- `GET /api/v1/manual-review/tasks`
- `POST /api/v1/manual-review/tasks/{task_id}/approve`
- `POST /api/v1/manual-review/tasks/{task_id}/reject`
- `PUT /api/v1/manual-review/tasks/{task_id}`

### Admin (Users, Departments, Common Codes)
- `GET /api/v1/users`
- `POST /api/v1/users`
- `PUT /api/v1/users/{user_id}`
- `DELETE /api/v1/users/{user_id}`
- `GET /api/v1/users/search`
- `GET /api/v1/admin/departments`
- `POST /api/v1/admin/departments`
- `PUT /api/v1/admin/departments/{department_id}`
- `DELETE /api/v1/admin/departments/{department_id}`
- `GET/PUT /api/v1/admin/users/{user_id}/departments`
- `GET/POST/PUT/DELETE /api/v1/admin/common-codes/groups`
- `GET/POST/PUT/DELETE /api/v1/admin/common-codes/groups/{group_id}/items`
- `GET /api/v1/common-codes/{group_code}`
- `POST /api/v1/common-codes/bulk`

## Configuration

주요 설정은 `.env`에서 관리합니다:

- `DATABASE_URL`: Async PostgreSQL URL
- `VECTORSTORE_TYPE`: `mock`, `pgvector`, `pinecone`, `qdrant`
- `LLM_PROVIDER`: `mock`, `openai`, `anthropic`, `ollama`
- `LLM_MODEL`, `LLM_TEMPERATURE`, `LLM_MAX_TOKENS`
- `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`
- `E5_MODEL_NAME`, `EMBEDDING_DEVICE`
- `SECRET_KEY`, `ACCESS_TOKEN_EXPIRE_MINUTES`

## Development Status

### Done
- 상담 등록/검색 및 벡터 인덱싱
- 메뉴얼 초안 생성 및 비교(diff)
- 메뉴얼 승인/버전 관리 (APPROVED/DEPRECATED/DRAFT)
- 메뉴얼 검토 태스크 워크플로우
- 공통코드/부서/사용자 관리 (관리자 전용)
- JWT 인증 및 역할 기반 접근 제어
- pgvector/LLM(OpenAI/Anthropic/Ollama) 구현체 포함
- 테스트: 서비스/라우터/정책 검증 케이스 추가

### TODO
- 운영 환경 배포 가이드 정리
- 큐 브로커 기반 재시도/비동기 워커 정식 적용
- API 문서화 정리 및 샘플 요청/응답 보강

## Testing & Lint

```bash
uv run pytest
uv run pytest --cov=app tests/

uv run black app/ tests/ --check
uv run ruff check app/ tests/
uv run mypy app/
```

## Documentation

- `docs/RFP_KHW_v6.md` (요구사항 명세)
- `docs/MANUAL_WORKFLOW_AND_VERSIONING.md`
- `docs/UnitSpec.md`
- `docs/FR15_COMMON_CODE_IMPLEMENTATION.md`

## Security

- JWT 기반 인증 + 역할(Role) 기반 인가
- 비밀키/외부 API 키는 `.env`에만 저장
- 운영 환경에서는 `SECRET_KEY` 교체 필수

## Contributing

1. Feature branch 생성
2. 코드 작성 및 테스트
3. PR 생성 (Conventional Commits)

## License

Private Project
