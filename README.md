# KHW - K Help Desk Wiki

고객 상담 지식 관리 시스템 (Knowledge Helpdesk Wiki)

## 📋 Overview

KHW은 고객 상담 내역을 기반으로 메뉴얼을 자동 생성하고 관리하는 시스템입니다.

**주요 기능:**
- 상담 내역 저장 및 벡터 기반 유사 상담 검색
- LLM을 활용한 메뉴얼 자동 생성
- 기존 메뉴얼과의 충돌 감지 및 검토 워크플로우
- 환각(Hallucination) 방지 규칙 적용

## 🏗️ Architecture

```
app/
├── api/           # FastAPI 앱 팩토리
├── mcp/           # MCP 서버 (Claude 연동)
├── core/          # 설정, DB, 로깅, 에러
├── models/        # SQLAlchemy 모델 (RDB)
├── schemas/       # Pydantic 스키마 (DTO)
├── repositories/  # DB 접근 레이어
├── services/      # 비즈니스 로직 (MCP-ready)
├── vectorstore/   # VectorStore 추상화
├── llm/           # LLM 클라이언트 추상화
├── queue/         # Retry Queue/DLQ
└── routers/       # FastAPI 라우터
```

**레이어 구조:**
- **API Layer** (FastAPI): HTTP 요청/응답 처리
- **Service Layer**: 비즈니스 로직 (FastAPI 독립적)
- **Repository Layer**: 데이터 접근 (RDB + VectorStore)
- **Model Layer**: 도메인 엔티티

## 💬 Claude에서 사용하기 (MCP)

KHW은 MCP(Model Context Protocol) 서버로 제공되어 Claude Desktop/웹에서 직접 사용할 수 있습니다.

### MCP 서버 시작

```bash
# MCP 서버 실행
uv run python mcp_server.py
```

### Claude Desktop 설정

`~/Library/Application Support/Claude/claude_desktop_config.json` (macOS) 또는
`~/.config/Claude/claude_desktop_config.json` (Linux) 파일에 추가:

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

**자세한 MCP 설정 방법**: [docs/MCP_SETUP.md](docs/MCP_SETUP.md)

### Claude에서 사용 예시

```
# 상담 생성
새 상담을 생성해주세요: "카드 결제 오류"

# 유사 상담 검색
"카드 결제"와 관련된 상담을 검색해주세요

# 메뉴얼 생성
이 상담으로 메뉴얼을 생성해주세요
```

## 🚀 Quick Start

### Prerequisites

- Python 3.10+
- PostgreSQL 15+ (optional, 나중에 설정)
- Redis (optional, queue 사용 시)

### Installation

1. **Clone repository**
```bash
cd /home/hauam/workspace/k-helpdesk-wiki
```

2. **Install dependencies**
```bash
# Using UV (recommended)
uv sync

# Install dev dependencies as well
uv sync --all-groups
```

3. **Environment setup**
```bash
cp .env.example .env
# Edit .env with your configuration
```

4. **Run application**
```bash
# Using UV
uv run python main.py

# Or with uvicorn
uv run uvicorn app.api.main:app --reload
```

5. **Access API**
- API Docs: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc
- Health Check: http://localhost:8000/health

## 📡 API Endpoints

### Consultations
```
POST   /api/v1/consultations              # Create consultation
GET    /api/v1/consultations/search       # Search similar consultations
POST   /api/v1/consultations/{id}/manual-draft  # Generate manual draft
```

### Manuals
```
GET    /api/v1/manuals                    # List manuals
GET    /api/v1/manuals/search             # Search manuals
POST   /api/v1/manuals/{id}/review        # Create review task
```

### Manual Review Tasks
```
GET    /api/v1/manual-review/tasks                 # List review tasks
POST   /api/v1/manual-review/tasks/{id}/approve    # Approve task
POST   /api/v1/manual-review/tasks/{id}/reject     # Reject task
```

## 🗄️ Database Setup

### Using Alembic (Production)

```bash
# Initialize Alembic (already done)
uv run alembic init alembic

# Create migration
uv run alembic revision --autogenerate -m "Initial migration"

# Run migration
uv run alembic upgrade head
```

### Development Mode

데이터베이스는 아직 실제 연결 전입니다. 현재는 Mock 구현체로 동작합니다.

## 🔧 Configuration

`.env` 파일에서 다음을 설정할 수 있습니다:

### VectorStore Options
- `mock`: 메모리 기반 (개발용)
- `pgvector`: PostgreSQL + pgvector extension
- `pinecone`: Pinecone 클라우드
- `qdrant`: Qdrant 벡터 DB

### LLM Provider Options
- `mock`: Mock 응답 (개발용)
- `openai`: OpenAI GPT models
- `anthropic`: Anthropic Claude models

## 📝 Development Status

### ✅ Completed
- [x] Project structure and configuration
- [x] Core module (config, db, logging, exceptions)
- [x] SQLAlchemy models (Consultation, ManualEntry, ManualVersion, ManualReviewTask)
- [x] Pydantic schemas (request/response DTOs)
- [x] Repository layer (RDB access)
- [x] VectorStore abstraction + Mock implementation
- [x] LLM client abstraction + Mock implementation
- [x] Queue abstraction (Retry/DLQ)
- [x] Service layer structure (business logic)
- [x] FastAPI routers and API main

### 🚧 TODO (Next Steps)
- [ ] Implement service layer logic (consultation, manual)
- [ ] Connect real PostgreSQL database
- [ ] Implement real VectorStore (pgvector/Pinecone/Qdrant)
- [ ] Implement real LLM client (OpenAI/Anthropic)
- [ ] LLM hallucination validation logic
- [ ] Manual conflict detection algorithm
- [ ] Review workflow implementation
- [ ] Unit tests
- [ ] Integration tests
- [ ] API documentation enhancement

## 🧪 Testing

```bash
# Run all tests
uv run pytest

# Run with coverage
uv run pytest --cov=app tests/

# Run specific test file
uv run pytest tests/unit/test_consultation_service.py
```

## 📚 Documentation

자세한 내용은 다음 문서를 참고하세요:
- [RFP Document](docs/KHW_RPF.md) - 전체 요구사항 명세
- API Documentation - http://localhost:8000/docs (서버 실행 후)

## 🔐 Security

- PII 데이터는 암호화/마스킹 필요 (TODO)
- RBAC 구현 필요 (TODO)
- API Key 관리는 환경변수로

## 🤝 Contributing

1. Feature branch 생성
2. 코드 작성 및 테스트
3. PR 생성

## 📄 License

Private Project

## 👥 Team

- Backend Architect: TBD
- LLM Engineer: TBD
- DevOps: TBD
