# 🎓 K Help Desk Wiki (KHW) 신입 온보딩 가이드

**Welcome! 👋 이 문서는 K Help Desk Wiki 프로젝트를 처음 접하는 개발자를 위한 완벽한 최신 가이드입니다.**

---

## 📖 목차

- [프로젝트 소개](#-프로젝트-소개)
- [핵심 개념](#-핵심-개념)
- [아키텍처 개요](#-아키텍처-개요)
- [데이터베이스 구조](#-데이터베이스-구조)
- [프로젝트 구조](#-프로젝트-구조)
- [주요 기능 워크플로우](#-주요-기능-워크플로우)
- [개발 환경 설정](#-개발-환경-설정)
- [주요 개발 명령어](#-주요-개발-명령어)
- [로컬 개발 시작하기](#-로컬-개발-시작하기)
- [코드 작성 시 중요한 규칙](#-코드-작성-시-중요한-규칙)
- [자주 묻는 질문 (FAQ)](#-자주-묻는-질문-faq)

---

## 🎯 프로젝트 소개

### KHW (K Help Desk Wiki)란?

KHW는 **고객 지원 상담 기록을 기반으로 자동으로 매뉴얼을 생성하고 관리하는 지식 관리 시스템**입니다.

#### 핵심 가치
- 📞 **상담 이력 자동 수집**: 고객 상담 내용을 구조화된 형식으로 저장
- 🤖 **AI 기반 매뉴얼 생성**: LLM을 활용해 상담 내용에서 매뉴얼 초안 자동 생성
- 🔍 **스마트 검색**: 벡터 기반 의미론적 검색으로 유사 상담 및 매뉴얼 찾기
- ✅ **품질 관리**: 매뉴얼 검토 및 승인 워크플로우로 신뢰할 수 있는 콘텐츠 관리
- 📋 **공통코드 관리**: 업무구분, 에러코드 등 시스템 전역 코드 관리 (FR-15)

#### 기술 스택
```
Frontend: (별도 프로젝트)
Backend: Python 3.10+ + FastAPI (비동기)
Database: PostgreSQL (RDB) + VectorStore (검색 인덱스)
AI/ML: LLM (OpenAI/Anthropic/Ollama), Embedding, Vector Search
Integration: MCP (Model Context Protocol) - Claude와의 직접 연동
```

#### 최근 추가된 기능 (2024년 12월)
- ✨ **FR-15**: 공통코드 관리 시스템 완성 (BUSINESS_TYPE, ERROR_CODE 등)
- 🦙 **Ollama LLM 지원**: 로컬 LLM 모델 지원 (OpenAI/Anthropic 대안)
- 📊 **Manual Diff API**: 매뉴얼 버전 간 비교 및 변경사항 분석
- 🔗 **향상된 리뷰 태스크**: 기존 매뉴얼 정보와 함께 비교 데이터 제공

---

## 💡 핵심 개념

### 1. **상담 (Consultation)**
- 고객과의 상담 내용을 저장하는 기본 단위
- 포함 정보: 요약, 문의 내용, 취한 조치, 메타데이터 (지점, 업무구분, 에러코드 등)
- 상담 등록 후 자동으로 벡터 인덱싱

### 2. **매뉴얼 (Manual Entry)**
- 상담을 기반으로 생성된 **구조화된 지식**
- 상태: **DRAFT** (초안) → **APPROVED** (승인) → **DEPRECATED** (폐지)
- 구성요소:
  - **키워드**: 1-3개의 핵심 검색어
  - **주제 (Topic)**: 한 문장 제목
  - **배경 (Background)**: 문제 상황 설명
  - **가이드라인 (Guideline)**: 해결 방법

### 3. **매뉴얼 버전 (Manual Version)**
- 승인된 매뉴얼은 버전 번호를 받음 (1.0, 1.1, 1.2...)
- 같은 업무구분/에러코드로 새 매뉴얼 승인 시, 이전 버전은 DEPRECATED 처리
- 변경사항 추적을 위한 changelog 관리

### 4. **리뷰 태스크 (Review Task)**
- 신규 매뉴얼과 기존 매뉴얼의 **충돌 감지**
- 상담자가 승인/반려하는 **워크플로우** 관리
- 상태: TODO → IN_PROGRESS → DONE/REJECTED
- 모든 상태 변경은 TaskHistory에 감사 추적 기록

### 5. **공통코드 (Common Code)** - NEW (FR-15)
- 시스템 전역에서 사용하는 코드 값 관리
- 그룹 단위로 조직화 (예: BUSINESS_TYPE, ERROR_CODE, STATUS_CODE)
- 관리자 API로 CRUD, 공개 API로 조회
- 각 코드 항목은 추가 속성(JSONB)을 저장 가능

### 6. **벡터 검색 (Vector Search)**
- 텍스트를 **숫자 벡터**로 변환하여 의미론적 유사성으로 검색
- 예: "카드 결제 오류"와 "신용카드 결제 실패"를 **같은 의미**로 인식
- 저장소: RDB (원본 데이터) + VectorStore (검색 인덱스)
- 검색 시 메타데이터 필터 적용 (지점, 업무구분 등)

### 7. **환각 방지 (Hallucination Prevention)**
- LLM이 **원문에 없는 정보를 만들지 않도록** 검증
- 예: 매뉴얼의 모든 키워드와 문구가 원본 상담 텍스트에 존재하는지 확인

---

## 🏗️ 아키텍처 개요

### 레이어드 아키텍처 (Layered Architecture)

```
┌─────────────────────────────────────┐
│     🌐 API Layer (FastAPI)          │  HTTP 요청 처리
│  /api/v1/consultations              │
│  /api/v1/manuals                    │
│  /api/v1/manual-review/tasks        │
│  /admin/common-codes/               │  ← 새로운 공통코드 관리
│  /common-codes/                     │  ← 공개 API
└──────────────┬──────────────────────┘
               │
┌──────────────▼──────────────────────┐
│   💼 Service Layer (비즈니스 로직)    │  순수 Python 코드
│  - ConsultationService              │  FastAPI 의존성 ❌
│  - ManualService                    │  테스트 가능 ✅
│  - TaskService                      │
│  - CommonCodeService    (NEW)       │
└──────────────┬──────────────────────┘
               │
┌──────────────▼──────────────────────┐
│  📦 Repository Layer (데이터 접근)   │  RDB CRUD 작업
│  - ConsultationRepository           │
│  - ManualRepository                 │
│  - TaskRepository                   │
│  - CommonCodeRepository (NEW)       │
└──────────────┬──────────────────────┘
               │
┌──────────────▼──────────────────────┐
│   🗄️ Data Layer                      │
│  - PostgreSQL (원본 데이터)           │
│  - VectorStore (검색 인덱스)         │
│  - LLM (AI 모델)                    │
└─────────────────────────────────────┘
```

### 중요한 설계 원칙

#### ✅ Service Layer는 FastAPI-Independent
```python
# ✅ 올바른 방식
class ConsultationService:
    async def create_consultation(self, data: ConsultationCreate) -> ConsultationResponse:
        # Pydantic 모델, 순수 Python 타입만 사용
        return ConsultationResponse(...)
```

**왜?** 같은 서비스를 FastAPI API와 MCP(Claude) 서버에서 재사용하기 위함

#### ✅ Repository 의존성 주입
```python
class ConsultationService:
    def __init__(self, repository: ConsultationRepository):
        self.repository = repository

    async def create(self, data: ConsultationCreate):
        return await self.repository.create_consultation(data)
```

**왜?** 테스트 시 Mock Repository를 주입할 수 있음

---

## 🗄️ 데이터베이스 구조

### 테이블 관계도 (ERD)

```
┌─────────────────────────────────────────────────────────────────────┐
│                       Consultation (상담)                              │
├─────────────────────────────────────────────────────────────────────┤
│ id (PK, UUID)           │ summary, inquiry_text, action_taken        │
│ branch_code             │ employee_id, screen_id, transaction_name   │
│ business_type, error_code │ metadata_fields (JSONB)                  │
│ manual_entry_id (FK)    │ → 승인된 매뉴얼 연결 (1:1, nullable)       │
│ created_at, updated_at  │                                            │
└────────────┬────────────────────────────────────┬────────────────────┘
             │ 1:N (source_consultation_id)       │ 1:1 (FK)
             │                                     │
    ┌────────▼────────────┐              ┌────────▼──────────────┐
    │ ManualEntry        │              │ ConsultationVector   │
    │ (매뉴얼)            │              │ Index (벡터 인덱스)   │
    ├────────────────────┤              ├──────────────────────┤
    │ id (PK, UUID)      │              │ consultation_id (FK) │
    │ keywords (JSONB)   │              │ embedding (ARRAY)    │
    │ topic              │              │ metadata_json        │
    │ background         │              │ branch_code, ...     │
    │ guideline          │              │ status               │
    │ business_type      │              │ (PENDING/INDEXED/...) │
    │ error_code         │              └──────────────────────┘
    │ version_id (FK)    │ → ManualVersion (N:1, optional)
    │ status             │   (DRAFT/APPROVED/DEPRECATED)
    │ source_consult...  │
    │ created_at, ...    │
    └────────┬───────────┘
             │ N:1 (으로의 old/new_entry_id)
             │
    ┌────────▼──────────────────┐
    │ ManualReviewTask          │
    │ (리뷰 태스크)              │
    ├───────────────────────────┤
    │ id (PK, UUID)             │
    │ old_entry_id (FK) [NULL]  │
    │ new_entry_id (FK)         │
    │ similarity (Float)        │
    │ status (TODO/DONE/...)    │
    │ reviewer_id (String)      │
    │ review_notes, ...         │
    └────────┬──────────────────┘
             │ 1:N (task_id)
             │
    ┌────────▼──────────────────┐
    │ TaskHistory               │
    │ (태스크 감사 추적)         │
    ├───────────────────────────┤
    │ id (PK, Integer)          │
    │ task_id (FK)              │
    │ from_status → to_status   │
    │ changed_by                │
    │ reason                    │
    │ created_at                │
    └───────────────────────────┘


┌──────────────────────────────────────────────────────┐
│ ManualVersion (매뉴얼 버전)                            │
├──────────────────────────────────────────────────────┤
│ id (PK, UUID)                                        │
│ version (String, unique)  e.g. "1.0", "1.1"         │
│ description               변경 사항 설명              │
│ changelog (JSONB)         상세 변경 기록              │
│ created_at                                           │
└─────────────────────────────────────────────────────┘
  ▲ 1:N (version_id)
  │
  └── ManualEntry 에서 참조


┌──────────────────────────────────────────────────────┐
│ ManualVectorIndex (매뉴얼 벡터 인덱스)                │
├──────────────────────────────────────────────────────┤
│ id (PK, Integer)          자동증가                    │
│ manual_entry_id (FK)      유니크 제약                 │
│ embedding (ARRAY)         벡터 데이터                 │
│ metadata_json             필터링용 메타데이터         │
│ business_type, error_code │                          │
│ status (PENDING/INDEXED)  │                          │
└──────────────────────────────────────────────────────┘


┌────────────────────────────────────────────────────────┐
│ User (사용자)                                          │
├────────────────────────────────────────────────────────┤
│ id (PK, Integer)    ← 자동증가 (UUID 아님)            │
│ username, password_hash                               │
│ employee_id, name, department                         │
│ role (CONSULTANT/REVIEWER/ADMIN)                      │
│ is_active                                             │
│ created_at, updated_at                                │
└────────────────────────────────────────────────────────┘


┌─────────────────────────────────────────────────────────┐
│ CommonCodeGroup (공통코드 그룹)                         │
├─────────────────────────────────────────────────────────┤
│ id (PK, UUID)                                           │
│ group_code (String, unique) e.g. "BUSINESS_TYPE"      │
│ group_name                  한글명                      │
│ description                 설명                        │
│ is_active (Boolean)         활성화 여부                │
│ created_at, updated_at                                 │
└────────────┬────────────────────────────────────────────┘
             │ 1:N (cascade delete)
             │
    ┌────────▼───────────────────────────────┐
    │ CommonCodeItem (공통코드 항목)          │
    ├────────────────────────────────────────┤
    │ id (PK, UUID)                          │
    │ group_id (FK)                          │
    │ code_key (String)   e.g. "CARD_ERROR"  │
    │ code_value (String) e.g. "카드 오류"   │
    │ sort_order (Integer)                   │
    │ is_active (Boolean)                    │
    │ attributes (JSONB)  추가 속성          │
    │ created_at, updated_at                 │
    │ UNIQUE(group_id, code_key)             │
    └────────────────────────────────────────┘


┌────────────────────────────────────────────────────────┐
│ RetryQueueJob (재시도 큐 - VectorStore 색인 실패)     │
├────────────────────────────────────────────────────────┤
│ id (PK, Integer)          자동증가                     │
│ target_type (Enum)        CONSULTATION / MANUAL       │
│ target_id (UUID)          대상 ID                     │
│ payload (JSONB)           작업 정보                   │
│ attempts (Integer)        재시도 횟수                 │
│ status (Enum)             PENDING/RETRYING/FAILED    │
│ last_error (String)       마지막 오류 메시지         │
│ next_retry_at (DateTime)  다음 재시도 시각          │
│ created_at, updated_at                               │
└────────────────────────────────────────────────────────┘
```

### 데이터베이스 특성

| 테이블 | 기본 키 | 특징 |
|------|-------|------|
| Consultation | UUID | 상담 정보, 메타필터 인덱스 |
| ManualEntry | UUID | 다중 상태 관리, 버전 참조 |
| ManualVersion | UUID | 버전 번호 유니크, Changelog |
| ManualReviewTask | UUID | 비교/승인/반려 워크플로우 |
| TaskHistory | Integer | 감사 추적, 상태 변경 기록 |
| User | Integer | 자동 증가 PK (다른 모델과 다름) |
| CommonCodeGroup | UUID | 공통코드 그룹, 계층 관리 |
| CommonCodeItem | UUID | 공통코드 항목, 정렬 순서 관리 |
| ConsultationVectorIndex | - | 벡터 메타데이터, 상담과 1:1 |
| ManualVectorIndex | - | 벡터 메타데이터, 매뉴얼과 1:1 |
| RetryQueueJob | Integer | VectorStore 실패 재시도 관리 |

---

## 📂 프로젝트 구조

```
k-helpdesk-wiki/
├── app/
│   ├── api/
│   │   └── main.py                 # FastAPI 앱 생성
│   ├── routers/                    # 📍 API 엔드포인트
│   │   ├── auth.py                 # 사용자 인증
│   │   ├── consultations.py        # POST /consultations, GET /search
│   │   ├── manuals.py              # POST /draft, GET /search, DIFF API
│   │   ├── tasks.py                # POST /approve, POST /reject
│   │   └── common_codes.py         # NEW: /admin/common-codes, /common-codes
│   ├── services/                   # 💼 비즈니스 로직 (핵심!)
│   │   ├── consultation_service.py # 상담 등록, 검색 로직
│   │   ├── manual_service.py       # 매뉴얼 생성, 검토, 승인, 비교 로직
│   │   ├── task_service.py         # 검토 태스크 승인/반려
│   │   ├── common_code_service.py  # NEW: 공통코드 CRUD (682 lines)
│   │   ├── user_service.py         # 사용자 관리
│   │   ├── validation.py           # 환각 방지 검증
│   │   ├── rerank.py               # 검색 결과 재순위화
│   │   └── [helper services]       # 유틸리티
│   ├── repositories/               # 📦 데이터 접근 레이어
│   │   ├── base.py                 # BaseRepository 기본 메서드
│   │   ├── consultation_rdb.py     # Consultation CRUD
│   │   ├── consultation_repository.py # 검색 쿼리
│   │   ├── manual_rdb.py           # ManualEntry CRUD
│   │   ├── manual_repository.py    # 매뉴얼 쿼리 레이어
│   │   ├── task_repository.py      # ManualReviewTask 쿼리
│   │   ├── user_repository.py      # User 쿼리
│   │   └── common_code_rdb.py      # NEW: CommonCode CRUD (386 lines)
│   ├── models/                     # 🗄️ SQLAlchemy 도메인 모델
│   │   ├── base.py                 # BaseModel, UUIDMixin, TimestampMixin
│   │   ├── consultation.py         # Consultation 테이블
│   │   ├── manual.py               # ManualEntry, ManualVersion 테이블
│   │   ├── task.py                 # ManualReviewTask, TaskHistory 테이블
│   │   ├── user.py                 # User 테이블
│   │   ├── vector_index.py         # ConsultationVectorIndex, ManualVectorIndex
│   │   ├── queue.py                # RetryQueueJob (VectorStore 재시도)
│   │   └── common_code.py          # NEW: CommonCodeGroup, CommonCodeItem
│   ├── schemas/                    # 📊 Pydantic 요청/응답 모델
│   │   ├── base.py                 # 공통 스키마
│   │   ├── consultation.py         # ConsultationCreate, Response
│   │   ├── manual.py               # ManualDraft, Response (향상됨)
│   │   ├── user.py                 # UserCreate, Response
│   │   └── common_code.py          # NEW: CommonCode schemas (279 lines)
│   ├── vectorstore/                # 🔍 벡터 검색 추상화
│   │   ├── protocol.py             # VectorStoreProtocol (인터페이스)
│   │   ├── mock.py                 # Mock 구현 (개발용)
│   │   ├── pgvector.py             # PostgreSQL pgvector 구현
│   │   └── __init__.py             # VectorStore 팩토리
│   ├── llm/                        # 🤖 LLM 클라이언트 추상화
│   │   ├── protocol.py             # LLMClientProtocol (인터페이스)
│   │   ├── mock.py                 # Mock 구현 (개발용)
│   │   ├── ollama.py               # NEW: Ollama 로컬 LLM 지원
│   │   ├── prompts.py              # 프롬프트 기본 설정
│   │   ├── prompts/                # LLM 프롬프트
│   │   │   ├── manual_draft.py     # 초안 생성 프롬프트
│   │   │   ├── manual_compare.py   # 매뉴얼 비교 프롬프트
│   │   │   └── manual_diff.py      # 매뉴얼 차이점 분석 프롬프트
│   │   └── __init__.py             # LLM 클라이언트 팩토리
│   ├── queue/                      # 📨 비동기 작업 큐
│   │   ├── protocol.py             # QueueProtocol
│   │   ├── inmemory.py             # 인메모리 구현
│   │   └── mock.py                 # Mock 구현
│   ├── core/                       # ⚙️ 핵심 유틸리티
│   │   ├── config.py               # 환경 설정 (올람 타임아웃 추가)
│   │   ├── db.py                   # 데이터베이스 초기화
│   │   ├── exceptions.py           # 커스텀 예외
│   │   ├── logging.py              # 구조화된 로깅
│   │   ├── security.py             # JWT, 보안
│   │   └── dependencies.py         # FastAPI 의존성 주입
│   ├── mcp/                        # 🔗 MCP 서버 (Claude 통합)
│   │   ├── server.py               # MCP 서버 메인
│   │   └── tools.py                # Claude가 사용할 도구들 (235 lines, 향상됨)
│   └── __init__.py
├── main.py                         # FastAPI 실행 진입점
├── mcp_server.py                   # MCP 서버 실행 진입점
├── .env.example                    # 환경 변수 템플릿
├── pyproject.toml                  # 프로젝트 메타데이터, 의존성
├── alembic/                        # 🗄️ 데이터베이스 마이그레이션
│   └── versions/
│       ├── 20251206_0001_reviewer_to_employee_id_string.py
│       ├── 20251208_2257_fr_15_add_common_code_management.py
│       └── 20251209_1512_fix_common_code_group_id_column_type.py
├── tests/                          # 🧪 테스트
│   ├── unit/
│   │   ├── test_consultation_service.py
│   │   ├── test_manual_service.py
│   │   ├── test_common_code_service.py     # NEW (479 lines)
│   │   └── [other tests]
│   └── integration/
└── docs/                           # 📚 문서
    ├── KHW_RFP.md                  # 전체 요구사항 정의서
    ├── MCP_SETUP.md                # MCP 서버 설정 가이드
    ├── FR15_COMMON_CODE_IMPLEMENTATION.md   # NEW (725 lines)
    ├── FR15_IMPLEMENTATION_SUMMARY.md       # NEW (486 lines)
    ├── BACKEND_API_GUIDE.md        # NEW (262 lines)
    └── [other documentation]
```

---

## 📊 주요 기능 워크플로우

### 1️⃣ 상담 등록 → 벡터 인덱싱

```
사용자 입력
  ↓
POST /api/v1/consultations
  ↓
ConsultationService.register_consultation()
  ↓
1️⃣ ConsultationRepository.create() → PostgreSQL 저장 (ACID 보장)
  ↓
2️⃣ VectorStore.index_document() → 벡터 인덱싱 시도
  ├─ 성공 → 즉시 검색 가능 ✅
  └─ 실패 → RetryQueueJob 생성 (백그라운드 재시도) ⚠️
  ↓
응답 (201 Created)
```

**중요:** RDB 저장 후 벡터 인덱싱 시도 → 실패해도 데이터는 안전

### 2️⃣ 상담 검색 (의미론적 유사성)

```
사용자: "카드 결제 오류"
  ↓
GET /api/v1/consultations/search?query=...&branch_code=001
  ↓
ConsultationService.search_consultations()
  ↓
1️⃣ VectorStore.search(top_k=10) → 상위 10개 의미적 유사 결과
  ↓
2️⃣ ConsultationRepository.search_by_ids() → 메타데이터 필터
   (branch_code, business_type, error_code로 추가 필터)
  ↓
3️⃣ RerankerService.rerank() → 점수 + 도메인가중치 + 최신도로 재순위
  ↓
응답 (정렬된 결과)
```

### 3️⃣ 매뉴얼 초안 생성 (LLM)

```
사용자: "상담 #123으로 매뉴얼 만들어"
  ↓
POST /api/v1/manuals/draft {consultation_id}
  ↓
ManualService.create_draft_from_consultation()
  ↓
1️⃣ 원본 상담 조회
  ↓
2️⃣ LLM 호출 (프롬프트에 원문 포함)
   "위 상담 내용에서만 정보를 추출하세요"
  ↓
3️⃣ 환각 검증 (enforce_hallucination_check=true)
   - 키워드가 원문에 있는가?
   - 배경/가이드라인이 원문의 부분집합인가?
   └─ 위반 시 → DRAFT 생성 + 리뷰 태스크 자동 생성
  ↓
4️⃣ ManualRepository.create() → 저장
  ↓
응답 (201 Created)
```

### 4️⃣ 매뉴얼 충돌 감지 및 리뷰 태스크

```
신규 매뉴얼 생성
  ↓
ManualService.check_conflict_and_create_task()
  ↓
1️⃣ VectorStore 검색: 유사도 >= 0.85의 APPROVED 매뉴얼 찾기
  ├─ 없음 → 충돌 없음 ✅
  └─ 있음 ↓

2️⃣ LLM으로 비교 분석
   "기존 매뉴얼과 새 매뉴얼의 차이점은?"
  ↓
3️⃣ ManualReviewTask 생성
   - old_entry_id = 기존 매뉴얼
   - new_entry_id = 신규 매뉴얼
   - similarity = 유사도 점수
   - 상태 = TODO
  ↓
관리자 리뷰: 신규 승인 vs 기존 유지 선택
```

### 5️⃣ 매뉴얼 승인 및 버전 관리

```
관리자: "매뉴얼 #456 승인"
  ↓
POST /api/v1/manual-review/tasks/{id}/approve
  ↓
TaskService.approve_task()
  ↓
1️⃣ TaskHistory 기록: TODO → IN_PROGRESS → DONE
  ↓
2️⃣ ManualService.approve_manual()
   a. 현재 버전 확인 (예: 1.0)
   b. 새 버전 번호 생성 (1.1)
   c. ManualVersion 생성 및 changelog 저장
  ↓
3️⃣ 기존 승인 매뉴얼 처리
   - 같은 business_type/error_code 의 APPROVED → DEPRECATED
   - (금융권 정책: 새 버전이 이전 버전을 완전 대체)
  ↓
4️⃣ VectorStore 인덱싱 (APPROVED만)
   - 승인된 매뉴얼만 검색에 노출
  ↓
5️⃣ 결과 응답
```

### 6️⃣ 공통코드 관리 (NEW - FR-15)

```
관리자: "업무구분 코드 추가"
  ↓
POST /admin/common-codes/groups/{group_id}/items
{
  "code_key": "CARD_ERROR",
  "code_value": "카드 결제 오류",
  "sort_order": 1,
  "attributes": {"category": "payment", ...}
}
  ↓
CommonCodeService.create_code_item()
  ↓
1️⃣ 중복 검사 (group_id + code_key 유니크)
  ↓
2️⃣ CommonCodeItemRepository.create()
  ↓
3️⃣ 응답 (201 Created)

---

공개 API: 활성 코드 조회
  ↓
GET /common-codes/BUSINESS_TYPE
  ↓
CommonCodeService.get_active_items_by_group()
  ↓
응답 (프론트엔드 드롭다운용)
```

---

## ⚙️ 개발 환경 설정

### 필수 요구사항

- **Python 3.10+**
- **PostgreSQL 13+** (또는 mock 모드로 로컬 개발)
- **Git**
- **UV** (Python 패키지 매니저)

### Step 1: 프로젝트 클론 및 의존성 설치

```bash
git clone https://github.com/your-org/k-helpdesk-wiki.git
cd k-helpdesk-wiki

# UV로 모든 의존성 설치 (dev 포함)
uv sync --all-groups
```

### Step 2: 환경 변수 설정

```bash
# .env 파일 생성
cp .env.example .env

# 개발 환경 기본값은 이미 설정되어 있음 (Mock 모드)
# VECTORSTORE_TYPE=mock
# LLM_PROVIDER=mock
```

### Step 3: 데이터베이스 초기화 (선택)

```bash
# PostgreSQL이 없어도 Mock 모드로 개발 가능
# 하지만 실제 데이터 저장이 필요하면:

# PostgreSQL 서비스 시작
# macOS: brew services start postgresql@15
# Ubuntu: sudo service postgresql start

# 데이터베이스 생성
psql -U postgres -c "CREATE DATABASE khw;"

# 마이그레이션 실행
uv run alembic upgrade head
```

### Step 4: 애플리케이션 실행

```bash
# 터미널 1: FastAPI 실행
uv run python main.py

# 브라우저에서 확인
# http://localhost:8000/docs (Swagger UI)
# http://localhost:8000/health (헬스 체크)
```

---

## 🚀 주요 개발 명령어

### 애플리케이션 실행

```bash
# FastAPI 개발 서버 (자동 리로드)
uv run python main.py

# 또는 uvicorn 직접 실행
uv run uvicorn app.api.main:app --reload

# MCP 서버 (별도 터미널)
uv run python mcp_server.py
```

### 테스트

```bash
# 모든 테스트 실행
uv run pytest

# 커버리지 포함
uv run pytest --cov=app tests/

# 특정 테스트 파일
uv run pytest tests/unit/test_common_code_service.py -v

# 특정 테스트 함수
uv run pytest tests/unit/test_common_code_service.py::test_create_group -v
```

### 코드 품질 검사

```bash
# 포매팅 (Black)
uv run black app/ tests/

# 린팅 (Ruff)
uv run ruff check app/ tests/ --fix

# 타입 체크 (mypy)
uv run mypy app/

# 모두 한 번에
uv run black app/ tests/ && uv run ruff check app/ tests/ --fix && uv run mypy app/
```

### 데이터베이스 마이그레이션

```bash
# 새 마이그레이션 생성
uv run alembic revision --autogenerate -m "Description"

# 마이그레이션 적용
uv run alembic upgrade head

# 마지막 마이그레이션 취소
uv run alembic downgrade -1

# 현재 리비전 확인
uv run alembic current
```

---

## 🎬 로컬 개발 시작하기 (5분)

```bash
# 1️⃣ 프로젝트 준비
cd k-helpdesk-wiki
uv sync --all-groups

# 2️⃣ 환경 설정
cp .env.example .env
# .env 파일 확인 (Mock 모드 기본값)

# 3️⃣ FastAPI 실행 (터미널 1)
uv run python main.py

# 4️⃣ 테스트 실행 (터미널 2)
uv run pytest tests/ -v

# 5️⃣ 브라우저에서 확인
# http://localhost:8000/docs
```

### 첫 번째 API 호출

#### 상담 등록

```bash
curl -X POST http://localhost:8000/api/v1/consultations \
  -H "Content-Type: application/json" \
  -d '{
    "summary": "결제 오류 호소",
    "inquiry_text": "신용카드로 결제 시 CVV 인증 실패 오류 발생",
    "action_taken": "결제 서버 재부팅 후 해결",
    "branch_code": "001",
    "employee_id": "EMP001",
    "business_type": "카드결제",
    "error_code": "CVV_AUTH_FAIL"
  }'
```

#### 상담 검색

```bash
curl -X GET "http://localhost:8000/api/v1/consultations/search?query=결제%20오류&branch_code=001"
```

#### 매뉴얼 초안 생성

```bash
curl -X POST http://localhost:8000/api/v1/manuals/draft \
  -H "Content-Type: application/json" \
  -d '{
    "consultation_id": "550e8400-e29b-41d4-a716-446655440000",
    "enforce_hallucination_check": true
  }'
```

#### 공통코드 그룹 생성

```bash
curl -X POST http://localhost:8000/admin/common-codes/groups \
  -H "Content-Type: application/json" \
  -d '{
    "group_code": "BUSINESS_TYPE",
    "group_name": "업무 구분",
    "description": "고객 상담의 업무 카테고리"
  }'
```

#### 공통코드 항목 추가

```bash
curl -X POST http://localhost:8000/admin/common-codes/groups/{group_id}/items \
  -H "Content-Type: application/json" \
  -d '{
    "code_key": "CARD_ERROR",
    "code_value": "카드 결제 오류",
    "sort_order": 1,
    "attributes": {"category": "payment"}
  }'
```

---

## 📝 코드 작성 시 중요한 규칙

### 1️⃣ Service Layer는 항상 FastAPI-Independent

```python
# ❌ 잘못된 방식
from fastapi import HTTPException
class ConsultationService:
    async def create(...) -> dict:
        raise HTTPException(status_code=400)

# ✅ 올바른 방식
from app.core.exceptions import ValidationError
class ConsultationService:
    async def create(...) -> ConsultationResponse:
        raise ValidationError("...")
```

**왜?** API와 MCP 서버 모두에서 서비스를 재사용하기 위함

### 2️⃣ Repository는 모든 데이터 접근을 담당

```python
# ✅ 올바른 방식
class ConsultationService:
    def __init__(self, repository: ConsultationRepository):
        self.repository = repository

    async def create(...):
        return await self.repository.create_consultation(...)
```

### 3️⃣ 모든 async 함수는 await 필수

```python
# ❌ 잘못된 방식
async def process():
    result = self.repository.get_by_id(id)  # await 빠짐!

# ✅ 올바른 방식
async def process():
    result = await self.repository.get_by_id(id)
```

### 4️⃣ 타입 힌트는 필수 (mypy strict)

```python
# ✅ 완전한 타입 힌트
from typing import Any
def calculate_score(data: dict[str, Any]) -> float:
    return data['score'] * 1.2
```

### 5️⃣ 환각 방지: 항상 원문을 Prompt에 포함

```python
# ✅ 올바른 방식 - 원문(context) 포함
prompt = f"""
원본 상담 내용:
{consultation.inquiry_text}

위 상담 내용을 바탕으로만 매뉴얼을 작성하세요.
새로운 정보를 추가하지 마세요.
"""
```

### 6️⃣ 예외는 커스텀 예외 사용

```python
from app.core.exceptions import (
    RecordNotFoundError,
    ValidationError,
)

# 데이터 미검색
if not consultation:
    raise RecordNotFoundError(f"Consultation(id={id}) not found")

# 검증 실패
if not is_valid_data(data):
    raise ValidationError("Invalid consultation data")
```

### 7️⃣ 공통코드 사용 (FR-15)

```python
# 공통코드로 정의된 값만 사용
# ✅ 올바른 방식
business_type = "카드결제"  # 공통코드에서 검증됨
error_code = "CVV_AUTH_FAIL"  # 공통코드에서 검증됨

# DB에서 공통코드 조회 후 검증
common_codes = await commoncode_service.get_codes_by_group("BUSINESS_TYPE")
if business_type not in [c.code_value for c in common_codes]:
    raise ValidationError(f"Invalid business_type: {business_type}")
```

---

## ❓ 자주 묻는 질문 (FAQ)

### Q1: Mock 모드와 Real 모드의 차이는?

**Mock 모드** (개발):
- VECTORSTORE_TYPE=mock, LLM_PROVIDER=mock
- 데이터베이스 필요 없음
- 로컬 개발에 최적

**Real 모드** (프로덕션):
- VECTORSTORE_TYPE=pgvector, LLM_PROVIDER=openai
- 실제 PostgreSQL 필요
- 실제 API 호출

### Q2: LLM 제공자 선택은?

**Mock**: 개발 및 테스트용 (즉시 응답)

**OpenAI**:
```bash
LLM_PROVIDER=openai
LLM_MODEL=gpt-4-turbo-preview
OPENAI_API_KEY=sk-...
```

**Anthropic**:
```bash
LLM_PROVIDER=anthropic
LLM_MODEL=claude-3-sonnet
ANTHROPIC_API_KEY=sk-ant-...
```

**Ollama** (로컬, NEW):
```bash
LLM_PROVIDER=ollama
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_TIMEOUT=300  # 초 단위
# 로컬에서 ollama run llama2 실행 필요
```

### Q3: 벡터 검색은 어떻게 작동하나?

```
텍스트: "신용카드 결제 오류"
  ↓ (Embedding - LLM이 숫자 벡터로 변환)
벡터: [0.12, -0.45, ..., 0.21]  (1536차원)

검색: "카드 결제 실패"
  ↓ (Embedding)
벡터: [0.11, -0.46, ..., 0.22]

⚖️ 코사인 유사도 = 0.95 (95% 유사)
```

**구현 옵션:**
- mock: 인메모리 (개발)
- pgvector: PostgreSQL 확장
- pinecone: 클라우드 벡터 DB
- qdrant: 오픈소스 벡터 DB

### Q4: 왜 RDB와 VectorStore가 따로 있나?

| 구분 | RDB | VectorStore |
|------|-----|-------------|
| 용도 | 원본 데이터 저장 | 검색 인덱스 |
| 신뢰성 | ⭐⭐⭐⭐⭐ ACID | ⭐⭐⭐ 부분 동기화 |
| 실패 시 | 데이터 손실 | 검색 불가 (데이터 안전) |

**설계:** RDB = 진실의 원천, VectorStore = 검색용 인덱스

### Q5: 공통코드는 어떻게 사용하나?

**관리자가 미리 정의:**
- /admin/common-codes/groups 에서 BUSINESS_TYPE, ERROR_CODE 등 그룹 생성
- /admin/common-codes/groups/{id}/items 에서 항목 추가

**개발자는 사용:**
- GET /common-codes/BUSINESS_TYPE → 활성 항목 조회
- Consultation, ManualEntry 생성 시 공통코드 검증
- 드롭다운/선택박스에 표시

### Q6: 환각 검증은 어떻게 되나?

**3가지 검증:**

1. **키워드 검증**: "결제", "CVV", "인증" 모두 원문에 있는가?
2. **배경 검증**: 배경 문장이 원문의 부분집합인가?
3. **가이드라인 검증**: 해결책이 원문에 근거가 있는가?

**검증 실패 시:**
- DRAFT 상태로 저장
- 관리자가 수동 검토하도록 리뷰 태스크 자동 생성

### Q7: 매뉴얼 버전은 어떻게 관리되나?

**금융권 정책:**
- 매뉴얼 승인마다 버전 +1 (1.0 → 1.1)
- 같은 업무구분/에러코드의 기존 항목은 DEPRECATED
- APPROVED 매뉴얼만 검색에 노출
- 모든 승인은 TaskHistory에 기록

### Q8: 테스트는 어떻게 작성하나?

```python
import pytest
from unittest.mock import AsyncMock

@pytest.mark.asyncio
async def test_register_consultation():
    # 1️⃣ Mock 준비
    mock_repo = AsyncMock(spec=ConsultationRepository)
    mock_vectorstore = AsyncMock(spec=VectorStoreProtocol)

    # 2️⃣ Mock 반환값 설정
    mock_consultation = Consultation(id=..., ...)
    mock_repo.create_consultation.return_value = mock_consultation

    # 3️⃣ Service 생성 (mock 주입)
    service = ConsultationService(
        repository=mock_repo,
        vectorstore=mock_vectorstore,
    )

    # 4️⃣ 테스트 실행
    result = await service.register_consultation(ConsultationCreate(...))

    # 5️⃣ 검증
    assert result.id == mock_consultation.id
    mock_repo.create_consultation.assert_called_once()
```

### Q9: MCP 서버는 무엇인가?

**MCP (Model Context Protocol):**
- Claude가 외부 시스템과 상호작용할 수 있는 프로토콜
- KHW의 서비스를 Claude에서 직접 사용

```bash
# MCP 서버 실행
uv run python mcp_server.py

# Claude Desktop에서 KHW 도구 사용 가능
# - create_consultation
# - search_consultations
# - generate_manual_draft
# - approve_review_task
```

자세한 설정은 [MCP_SETUP.md](docs/MCP_SETUP.md) 참조

### Q10: 새 기능을 추가하려면?

**일반적인 절차:**

1. **Pydantic Schema** (`app/schemas/`)
2. **SQLAlchemy Model** (`app/models/`) - 필요시
3. **Repository 메서드** (`app/repositories/`)
4. **Service 비즈니스 로직** (`app/services/`)
5. **FastAPI Router** (`app/routers/`)
6. **테스트** (`tests/`)
7. **(선택) MCP 도구** (`app/mcp/tools.py`)

---

## 🎓 다음 단계

축하합니다! 이제 KHW 프로젝트의 기본을 이해했습니다. 🎉

**추가 학습:**
- 📚 [KHW_RFP.md](docs/KHW_RFP.md) - 전체 요구사항 정의서
- 📚 [FR15_COMMON_CODE_IMPLEMENTATION.md](docs/FR15_COMMON_CODE_IMPLEMENTATION.md) - 공통코드 상세 가이드
- 📚 [MCP_SETUP.md](docs/MCP_SETUP.md) - MCP 서버 설정
- 📚 [BACKEND_API_GUIDE.md](docs/BACKEND_API_GUIDE.md) - API 엔드포인트 상세

**첫 번째 기여:**
1. 간단한 버그 수정으로 시작
2. 테스트 추가 ([tests/unit/](tests/unit/) 참조)
3. 코드 리뷰 받기
4. 병합!

---

**Happy Coding! 🚀**

질문이나 피드백이 있으면 팀에 문의하세요. 함께 성장합니다! 💪
