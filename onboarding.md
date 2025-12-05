# 🎓 K Help Desk Wiki (KHW) 신입 온보딩 가이드

**Welcome! 👋 이 문서는 K Help Desk Wiki 프로젝트를 처음 접하는 개발자를 위한 완벽한 가이드입니다.**

---

## 📖 목차

- [프로젝트 소개](#-프로젝트-소개)
- [핵심 개념](#-핵심-개념)
- [아키텍처 개요](#-아키텍처-개요)
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

#### 기술 스택
```
Frontend: (별도 프로젝트)
Backend: Python 3.10+ + FastAPI (비동기)
Database: PostgreSQL (RDB) + VectorStore (검색 인덱스)
AI/ML: LLM (OpenAI/Anthropic), Embedding, Vector Search
Integration: MCP (Model Context Protocol) - Claude와의 직접 연동
```

---

## 💡 핵심 개념

### 1. **상담 (Consultation)**
- 고객과의 상담 내용을 저장하는 기본 단위
- 포함 정보: 요약, 문의 내용, 취한 조치, 메타데이터 (지점, 업무구분, 에러코드 등)

### 2. **매뉴얼 (Manual Entry)**
- 상담을 기반으로 생성된 **구조화된 지식**
- 상태: **DRAFT** (초안) → **APPROVED** (승인) → **DEPRECATED** (폐지)
- 구성요소:
  - **키워드**: 1-3개의 핵심 검색어
  - **주제 (Topic)**: 한 문장 제목
  - **배경 (Background)**: 문제 상황 설명
  - **가이드라인 (Guideline)**: 해결 방법

### 3. **벡터 검색 (Vector Search)**
- 텍스트를 **숫자 벡터**로 변환하여 의미론적 유사성으로 검색
- 예: "카드 결제 오류"와 "신용카드 결제 실패"를 **같은 의미**로 인식
- 저장소: RDB (원본 데이터) + VectorStore (검색 인덱스)

### 4. **환각 방지 (Hallucination Prevention)**
- LLM이 **원문에 없는 정보를 만들지 않도록** 검증
- 예: 매뉴얼의 모든 키워드와 문구가 원본 상담 텍스트에 존재하는지 확인

### 5. **검토 태스크 (Review Task)**
- 신규 매뉴얼과 기존 매뉴얼의 **충돌 감지**
- 상담자가 승인/반려하는 **워크플로우** 관리

---

## 🏗️ 아키텍처 개요

### 레이어드 아키텍처 (Layered Architecture)

```
┌─────────────────────────────────────┐
│     🌐 API Layer (FastAPI)          │  HTTP 요청 처리
│  /api/v1/consultations              │
│  /api/v1/manuals                    │
│  /api/v1/tasks                      │
└──────────────┬──────────────────────┘
               │
┌──────────────▼──────────────────────┐
│   💼 Service Layer (비즈니스 로직)    │  순수 Python 코드
│  - ConsultationService              │  FastAPI 의존성 ❌
│  - ManualService                    │  테스트 가능 ✅
│  - TaskService                      │
└──────────────┬──────────────────────┘
               │
┌──────────────▼──────────────────────┐
│  📦 Repository Layer (데이터 접근)   │  RDB CRUD 작업
│  - ConsultationRepository           │
│  - ManualRepository                 │
│  - TaskRepository                   │
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

```python
# ❌ 잘못된 방식
from fastapi import HTTPException
class ConsultationService:
    def create(...) -> HTTPException:  # 이러지 마세요!
        ...
```

**왜?** 같은 서비스를 FastAPI API와 MCP(Claude) 서버에서 재사용하기 위함

---

## 📂 프로젝트 구조

```
k-helpdesk-wiki/
├── app/
│   ├── api/
│   │   └── main.py                 # FastAPI 앱 생성
│   ├── routers/                    # 📍 API 엔드포인트
│   │   ├── consultations.py        # POST /consultations, GET /consultations/search
│   │   ├── manuals.py              # POST /manuals/draft, GET /manuals/search
│   │   ├── tasks.py                # POST /tasks/{id}/approve, POST /tasks/{id}/reject
│   │   └── auth.py                 # 인증 관련
│   ├── services/                   # 💼 비즈니스 로직 (핵심!)
│   │   ├── consultation_service.py # 상담 등록, 검색 로직
│   │   ├── manual_service.py       # 매뉴얼 생성, 검토, 승인 로직
│   │   ├── task_service.py         # 검토 태스크 승인/반려
│   │   ├── validation.py           # 환각 방지 검증
│   │   └── rerank.py               # 검색 결과 재순위화
│   ├── repositories/               # 📦 데이터 접근 레이어
│   │   ├── consultation_repository.py
│   │   ├── manual_rdb.py
│   │   ├── task_repository.py
│   │   └── base.py                 # 기본 CRUD 메서드
│   ├── models/                     # 🗄️ SQLAlchemy 도메인 모델
│   │   ├── consultation.py         # Consultation 테이블
│   │   ├── manual.py               # ManualEntry, ManualVersion 테이블
│   │   ├── task.py                 # ManualReviewTask 테이블
│   │   └── base.py                 # BaseModel (공통 필드)
│   ├── schemas/                    # 📊 Pydantic 요청/응답 모델
│   │   ├── consultation.py
│   │   ├── manual.py
│   │   └── user.py
│   ├── vectorstore/                # 🔍 벡터 검색 추상화
│   │   ├── protocol.py             # VectorStoreProtocol (인터페이스)
│   │   ├── mock.py                 # Mock 구현 (개발용)
│   │   ├── base.py                 # 기본 VectorStore 구현
│   │   └── factory.py              # VectorStore 생성 팩토리
│   ├── llm/                        # 🤖 LLM 클라이언트 추상화
│   │   ├── protocol.py             # LLMClientProtocol (인터페이스)
│   │   ├── mock.py                 # Mock 구현 (개발용)
│   │   ├── prompts/                # LLM 프롬프트
│   │   │   ├── manual_draft.py
│   │   │   └── manual_compare.py
│   │   └── factory.py              # LLM 클라이언트 생성 팩토리
│   ├── queue/                      # 📨 비동기 작업 큐
│   │   ├── protocol.py
│   │   ├── inmemory.py
│   │   └── mock.py
│   ├── core/                       # ⚙️ 핵심 유틸리티
│   │   ├── config.py               # 환경 설정 (매우 중요!)
│   │   ├── db.py                   # 데이터베이스 초기화
│   │   ├── exceptions.py           # 커스텀 예외
│   │   ├── logging.py              # 로깅
│   │   ├── security.py             # JWT, 보안
│   │   └── dependencies.py         # FastAPI 의존성 주입
│   ├── mcp/                        # 🔗 MCP 서버 (Claude 통합)
│   │   ├── server.py               # MCP 서버 메인
│   │   └── tools.py                # Claude가 사용할 도구들
│   └── __init__.py
├── main.py                         # FastAPI 실행 진입점
├── mcp_server.py                   # MCP 서버 실행 진입점
├── .env.example                    # 환경 변수 템플릿 (복사해서 .env 만들기)
├── pyproject.toml                  # 프로젝트 메타데이터, 의존성
├── alembic/                        # 🗄️ 데이터베이스 마이그레이션
├── tests/                          # 🧪 테스트
│   ├── unit/                       # 단위 테스트 (Service 테스트)
│   └── integration/                # 통합 테스트
└── docs/                           # 📚 문서
    ├── KHW_RFP.md                  # 전체 요구사항 정의서
    └── MCP_SETUP.md                # MCP 서버 설정 가이드
```

---

## 📊 주요 기능 워크플로우

이 섹션에서는 실제 사용자 상호작용 흐름을 **시퀀스 다이어그램**으로 설명합니다.

### 1️⃣ 상담 등록 워크플로우

사용자가 새로운 상담 내용을 시스템에 등록하는 과정입니다.

```mermaid
sequenceDiagram
    actor User as 상담사
    participant API as API<br/>/consultations
    participant Service as ConsultationService<br/>(비즈니스 로직)
    participant Repo as ConsultationRepository<br/>(데이터 접근)
    participant DB as PostgreSQL<br/>(RDB)
    participant Vector as VectorStore<br/>(검색 인덱스)
    participant Queue as RetryQueue<br/>(재시도 큐)

    User->>API: POST /consultations<br/>{branch_code, inquiry_text, ...}
    API->>Service: create_consultation(data)

    Service->>Repo: create_consultation(data)
    Repo->>DB: INSERT INTO consultations<br/>값 저장 및 commit
    DB-->>Repo: id 반환
    Repo-->>Service: Consultation 객체

    Service->>Service: _build_embedding_text()<br/>벡터화할 텍스트 생성
    Service->>Vector: index_document(id, text, metadata)<br/>벡터 인덱싱 시도

    alt 벡터 인덱싱 성공 ✅
        Vector-->>Service: success
        Service-->>API: ConsultationResponse
        API-->>User: 201 Created
    else 벡터 인덱싱 실패 ❌
        Vector-->>Service: error
        Service->>Queue: enqueue(VectorIndexJob)<br/>재시도 작업 등록
        Queue-->>Service: job_id
        Service-->>API: ConsultationResponse<br/>(RDB 저장됨, 벡터 미인덱스)
        API-->>User: 201 Created
        Note over Service,Queue: 백그라운드에서 재시도
    end
```

**중요 포인트:**
- RDB에 저장하고 **나서** 벡터 인덱싱을 시도
- 벡터 인덱싱 실패해도 **RDB 데이터는 안전**
- 실패 시 재시도 큐에 등록하여 나중에 재시도

---

### 2️⃣ 상담 검색 워크플로우

사용자가 "카드 결제 오류"처럼 자연어로 검색했을 때의 과정입니다.

```mermaid
sequenceDiagram
    actor User as 사용자
    participant API as API<br/>/consultations/search
    participant Service as ConsultationService
    participant Vector as VectorStore
    participant Repo as ConsultationRepository<br/>(메타필터 적용)
    participant Rerank as RerankerService<br/>(결과 재순위화)

    User->>API: GET /consultations/search<br/>?query=카드 결제 오류<br/>&branch_code=001
    API->>Service: search_consultations(request)

    Service->>Service: _build_metadata_filter()<br/>branch_code, business_type 등 필터 생성

    Service->>Vector: search(query, top_k=10,<br/>metadata_filter={...})
    Note over Vector: 의미론적 유사성으로<br/>상위 10개 선택
    Vector-->>Service: [VectorResult1, VectorResult2, ...]

    Service->>Repo: search_by_ids(id_list, filters)<br/>메타필터로 추가 필터링
    Repo->>Repo: WHERE business_type=? AND error_code=?
    Repo-->>Service: [Consultation1, Consultation2, ...]

    Service->>Rerank: rerank_results(results,<br/>domain_weight, recency_weight)
    Note over Rerank: 벡터 점수 + 도메인 가중치<br/>+ 최신도 가중치<br/>를 조합해 순위 조정
    Rerank-->>Service: [RerankedResult1, ...]

    Service-->>API: [ConsultationSearchResult]
    API-->>User: 200 OK<br/>결과 목록 반환

    Note over Service,Rerank: 검색 시간 측정 (NFR-1)<br/>latency 메트릭 기록
```

**검색 알고리즘의 3 단계:**
1. **VectorStore 검색**: 의미론적 유사성으로 후보 선택
2. **메타데이터 필터링**: 지점, 업무구분, 에러코드로 추가 필터
3. **Re-ranking**: 검색 점수 + 도메인 가중치 + 최신도로 최종 순위 결정

---

### 3️⃣ 매뉴얼 초안 생성 워크플로우

상담을 기반으로 LLM이 자동으로 매뉴얼 초안을 생성하는 과정입니다.

```mermaid
sequenceDiagram
    actor Manager as 담당자
    participant API as API<br/>/manuals/draft
    participant Service as ManualService
    participant Repo as ConsultationRepository
    participant LLM as LLM Client<br/>(OpenAI/Anthropic/Mock)
    participant Validator as ValidationService<br/>(환각 검증)
    participant ManualRepo as ManualRepository
    participant TaskService as TaskService<br/>(리뷰 태스크)

    Manager->>API: POST /manuals/draft<br/>{consultation_id}
    API->>Service: create_draft_from_consultation(request)

    Service->>Repo: get_by_id(consultation_id)
    Repo-->>Service: Consultation 객체

    Service->>Service: _call_llm_for_draft()<br/>prompt 생성
    Service->>LLM: complete_json(prompt, system_prompt)
    Note over LLM: LLM이 생성한<br/>키워드, 주제, 배경, 가이드라인
    LLM-->>Service: {keywords, topic, background, guideline}

    alt enforce_hallucination_check = true
        Service->>Validator: validate_keywords_in_source(keywords, text)
        Validator-->>Service: (ok, missing_keywords)

        Service->>Validator: validate_sentences_subset_of_source(background, text)
        Validator-->>Service: (ok, missing_sentences)

        Service->>Validator: validate_sentences_subset_of_source(guideline, text)
        Validator-->>Service: (ok, missing_sentences)

        alt 환각 감지됨 ⚠️
            Service->>ManualRepo: create(ManualEntry)<br/>status=DRAFT
            ManualRepo-->>Service: ManualEntry 객체

            Service->>TaskService: _create_review_task()<br/>new_entry_id만 지정
            TaskService-->>Service: ManualReviewTask 생성<br/>(관리자 검토 필요)

            Note over Service: 매뉴얼은 DRAFT 상태로<br/>관리자가 수동 검토 필요
        else 환각 없음 ✅
            Service->>ManualRepo: create(ManualEntry)<br/>status=DRAFT
            ManualRepo-->>Service: ManualEntry 객체
        end
    else enforce_hallucination_check = false
        Service->>ManualRepo: create(ManualEntry)<br/>status=DRAFT
        ManualRepo-->>Service: ManualEntry 객체
    end

    Service-->>API: ManualDraftResponse
    API-->>Manager: 201 Created<br/>매뉴얼 초안 반환
```

**환각 방지의 핵심:**
- LLM이 생성한 모든 키워드와 문구가 **원본 상담 텍스트**에 존재하는지 검증
- 환각 감지 시 관리자가 수동으로 검토할 수 있도록 **리뷰 태스크** 자동 생성

---

### 4️⃣ 매뉴얼 승인 워크플로우

생성된 매뉴얼 초안을 검토하고 승인하는 과정입니다.

```mermaid
sequenceDiagram
    actor Reviewer as 관리자<br/>(검토자)
    participant API as API<br/>/tasks/{id}/approve
    participant Service as TaskService
    participant ManualService as ManualService<br/>(승인 로직)
    participant ManualRepo as ManualRepository
    participant VersionRepo as VersionRepository
    participant Vector as VectorStore
    participant Consultation as ConsultationRepository

    Reviewer->>API: POST /tasks/{id}/approve<br/>{reviewer_id, notes}
    API->>Service: approve_task(task_id, payload)

    Service->>Service: _add_history()<br/>상태 변경 기록 (TODO → DONE)

    Service->>ManualService: approve_manual(manual_id, request)

    ManualService->>VersionRepo: get_latest_version()
    VersionRepo-->>ManualService: ManualVersion (v1.0)

    ManualService->>ManualService: _next_version_number()<br/>다음 버전 계산 (1.1)
    ManualService->>VersionRepo: create(ManualVersion v1.1)

    Note over ManualService: 금융권 정책: 매뉴얼 승인 시<br/>전체 버전 일괄 적용
    ManualService->>ManualService: _deprecate_previous_entries()<br/>동일 키(업무구분/에러코드)의<br/>기존 APPROVED 매뉴얼 → DEPRECATED
    ManualRepo->>ManualRepo: UPDATE status=DEPRECATED<br/>WHERE business_type=? AND error_code=?

    ManualService->>ManualRepo: update(manual)<br/>status=APPROVED, version=1.1

    ManualService->>ManualService: _index_manual_vector()<br/>승인된 매뉴얼만 벡터 인덱싱
    ManualService->>Vector: index_document(id, text, metadata)
    Vector-->>ManualService: success

    ManualService-->>Service: ManualVersionInfo
    Service-->>API: ManualReviewTaskResponse<br/>상태 = DONE
    API-->>Reviewer: 200 OK

    Note over ManualService,Vector: 이제 이 매뉴얼은<br/>검색 결과에 표시됨

    alt 원본 상담과 연결 (선택사항)
        Reviewer->>API: PUT /consultations/{id}<br/>{manual_entry_id}
        API->>Consultation: update consultation<br/>manual_entry_id 설정
        Note over Consultation: 상담 기록 -> 승인된 매뉴얼<br/>트레이서빌리티 확보
    end
```

**승인 과정의 핵심:**
1. **이력 기록**: 검토자 정보, 검토 의견 기록
2. **버전 증가**: 모든 승인마다 버전 +1 (1.0 → 1.1)
3. **기존 항목 폐지**: 같은 키의 기존 APPROVED 매뉴얼은 DEPRECATED
4. **벡터 인덱싱**: APPROVED 매뉴얼만 검색 가능하도록 인덱싱
5. **트레이서빌리티**: 상담 기록과 승인된 매뉴얼 연결

---

### 5️⃣ 메뉴얼 검색 및 충돌 감지 워크플로우

새로 생성된 매뉴얼과 유사한 기존 매뉴얼을 자동으로 찾아 충돌을 감지합니다.

```mermaid
sequenceDiagram
    actor System as 시스템
    participant Service as ManualService<br/>(충돌 감지)
    participant Vector as VectorStore<br/>(유사도 검색)
    participant ManualRepo as ManualRepository<br/>(상태별 필터링)
    participant LLM as LLM Client<br/>(비교 분석)
    participant TaskRepo as TaskRepository<br/>(리뷰 태스크 생성)

    System->>Service: check_conflict_and_create_task(manual_id)

    Service->>Service: _build_manual_text()<br/>매뉴얼을 벡터화할 텍스트 생성

    Service->>Vector: search(query_text, top_k=3, similarity_threshold=0.85)
    Note over Vector: 내용이 85% 이상 유사한<br/>상위 3개 메뉴얼 검색
    Vector-->>Service: [VectorResult1, ...]

    Service->>ManualRepo: find_by_ids(candidate_ids)
    Note over ManualRepo: 검색된 메뉴얼 중<br/>APPROVED 상태만 필터링
    ManualRepo-->>Service: [ApprovedManual1, ...]

    alt 유사한 승인 매뉴얼이 있음
        Service->>Service: 최고 유사도의 메뉴얼 선택

        Service->>LLM: _call_llm_compare(old_manual, new_manual)
        Note over LLM: LLM이 두 매뉴얼의<br/>차이점 분석
        LLM-->>Service: {differences: [...], summary}

        Service->>TaskRepo: create(ManualReviewTask)<br/>old_entry_id=기존, new_entry_id=신규<br/>유사도 점수, 차이점 포함
        TaskRepo-->>Service: ManualReviewTask 생성

        Service-->>System: ManualReviewTaskResponse
        Note over System: ✅ 리뷰 태스크 생성됨<br/>관리자가 신규/기존 중 선택

    else 유사한 승인 매뉴얼이 없음
        Service-->>System: null
        Note over System: ✅ 충돌 없음, 신규 매뉴얼<br/>자유롭게 승인 가능
    end
```

**충돌 감지의 목적:**
- 중복되는 매뉴얼 방지
- 기존 매뉴얼을 업데이트할지, 새 매뉴얼을 추가할지 의사결정 지원
- 버전 관리 일관성 유지

---

## ⚙️ 개발 환경 설정

### 필수 요구사항

- **Python 3.10+**
- **PostgreSQL 13+** (또는 mock 모드로 로컬 개발)
- **Git**
- **UV** (Python 패키지 매니저, pip 대체)

### Step 1: 프로젝트 클론

```bash
git clone https://github.com/your-org/k-helpdesk-wiki.git
cd k-helpdesk-wiki
```

### Step 2: 의존성 설치

```bash
# UV가 설치되어 있어야 함 (설치: curl -LsSf https://astral.sh/uv/install.sh | sh)
uv sync --all-groups
```

이 명령어가 자동으로:
- 프로젝트 의존성 설치
- 개발 도구 설치 (pytest, black, ruff, mypy 등)
- `.venv` 가상환경 생성

### Step 3: 환경 변수 설정

```bash
# .env 파일 생성 (템플릿 복사)
cp .env.example .env

# .env 파일을 열어서 필요한 항목 설정
# 개발 중에는 기본값(Mock)으로 충분합니다!
```

**개발 환경 기본값:**
```bash
# 벡터스토어: Mock (인메모리)
VECTORSTORE_TYPE=mock

# LLM: Mock (미리 정의된 응답)
LLM_PROVIDER=mock

# 데이터베이스: 로컬 PostgreSQL
DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/khw
```

### Step 4: 데이터베이스 초기화

```bash
# PostgreSQL 설정
# macOS (Homebrew): brew install postgresql@15
# Ubuntu: sudo apt-get install postgresql

# PostgreSQL 서비스 시작
# macOS: brew services start postgresql@15
# Ubuntu: sudo service postgresql start

# 데이터베이스 및 사용자 생성
psql -U postgres -c "CREATE DATABASE khw;"
psql -U postgres -c "CREATE USER khw_user WITH PASSWORD 'password';"
psql -U postgres -c "GRANT ALL PRIVILEGES ON DATABASE khw TO khw_user;"
```

또는 **Mock 모드로 시작** (DB 없이):
```bash
# .env에서 설정
VECTORSTORE_TYPE=mock
LLM_PROVIDER=mock
```

### Step 5: 마이그레이션 (선택사항)

```bash
# 데이터베이스 스키마 생성
uv run alembic upgrade head

# 또는 개발 중에는 자동 초기화 사용
# (app/api/main.py의 lifespan 함수에서 init_db() 호출)
```

---

## 🚀 주요 개발 명령어

### 애플리케이션 실행

#### FastAPI 개발 서버
```bash
# 자동 리로드와 함께 실행 (권장)
uv run python main.py

# 또는 uvicorn 직접 실행
uv run uvicorn app.api.main:app --reload --host 0.0.0.0 --port 8000
```

브라우저에서 확인:
- 🌐 API 문서: http://localhost:8000/docs
- 🔍 헬스 체크: http://localhost:8000/health

#### MCP 서버 (Claude 통합)
```bash
# 별도 터미널에서 실행
uv run python mcp_server.py
```

### 테스트 실행

```bash
# 모든 테스트 실행
uv run pytest

# 커버리지 리포트 포함
uv run pytest --cov=app tests/

# 특정 파일만 테스트
uv run pytest tests/unit/test_consultation_service.py -v

# 특정 함수만 테스트
uv run pytest tests/unit/test_consultation_service.py::test_register_consultation -v

# 빠른 테스트만 (마크 필터)
uv run pytest -m "not slow" -v
```

### 코드 품질 검사

```bash
# 코드 포매팅 (Black)
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
# 새 마이그레이션 생성 (자동 감지)
uv run alembic revision --autogenerate -m "Add user_email column"

# 마이그레이션 적용
uv run alembic upgrade head

# 마지막 마이그레이션 되돌리기
uv run alembic downgrade -1

# 특정 리비전으로 이동
uv run alembic upgrade <revision_id>

# 현재 리비전 확인
uv run alembic current
```

### 기타 유용한 명령어

```bash
# 프로젝트 의존성 업데이트
uv sync --upgrade

# Python 인터프리터 실행 (프로젝트 환경)
uv run python

# 설치된 패키지 목록
uv pip list

# 특정 패키지 설치 (추가)
uv pip install <package_name>
```

---

## 🎬 로컬 개발 시작하기

### 5분 안에 시작하기

```bash
# 1️⃣ 프로젝트 준비
cd k-helpdesk-wiki
uv sync --all-groups

# 2️⃣ 환경 설정
cp .env.example .env
# .env에서 필요한 값 확인 (Mock 모드 기본값 사용)

# 3️⃣ 터미널 1: FastAPI 실행
uv run python main.py
# 또는
uv run uvicorn app.api.main:app --reload

# 4️⃣ 터미널 2: 테스트 실행 (선택)
uv run pytest tests/ -v

# 5️⃣ 브라우저에서 확인
# http://localhost:8000/docs (Swagger UI)
```

### 첫 번째 API 호출 테스트

#### 상담 등록
```bash
curl -X POST http://localhost:8000/api/v1/consultations \
  -H "Content-Type: application/json" \
  -d '{
    "summary": "고객이 결제 오류 호소",
    "inquiry_text": "신용카드로 결제 시 'CVV 인증 실패' 오류 발생",
    "action_taken": "결제 서버 재부팅 후 해결",
    "branch_code": "001",
    "employee_id": "EMP001",
    "business_type": "카드결제",
    "error_code": "CVV_AUTH_FAIL"
  }'
```

응답 예시:
```json
{
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "summary": "고객이 결제 오류 호소",
  "branch_code": "001",
  "created_at": "2024-01-15T10:30:00Z",
  ...
}
```

#### 상담 검색
```bash
curl -X GET "http://localhost:8000/api/v1/consultations/search?query=결제%20오류&branch_code=001" \
  -H "Content-Type: application/json"
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

#### 매뉴얼 승인
```bash
# 먼저 리뷰 태스크 목록 조회
curl -X GET http://localhost:8000/api/v1/tasks

# 그 다음 승인
curl -X POST http://localhost:8000/api/v1/tasks/{task_id}/approve \
  -H "Content-Type: application/json" \
  -d '{
    "reviewer_id": "REV001",
    "review_notes": "승인합니다"
  }'
```

---

## 📝 코드 작성 시 중요한 규칙

### 1️⃣ Service Layer는 항상 FastAPI-Independent

```python
# ❌ 잘못된 방식 - FastAPI 타입 사용
from fastapi import HTTPException

class ConsultationService:
    async def create(...) -> dict:
        raise HTTPException(status_code=400, detail="...")
```

```python
# ✅ 올바른 방식 - 커스텀 예외 사용
from app.core.exceptions import ValidationError

class ConsultationService:
    async def create(...) -> ConsultationResponse:
        raise ValidationError("...")  # FastAPI가 자동으로 처리
```

**왜?** 같은 서비스를 API와 MCP 서버에서 재사용할 수 있어야 함

### 2️⃣ Repository는 모든 데이터 접근을 담당

```python
# ❌ 잘못된 방식 - Service가 직접 DB 접근
class ConsultationService:
    async def create(...):
        result = await self.session.execute(...)  # 직접 쿼리!

# ✅ 올바른 방식 - Repository를 통한 접근
class ConsultationService:
    def __init__(self, repository: ConsultationRepository):
        self.repository = repository

    async def create(...):
        consultation = await self.repository.create_consultation(...)
```

### 3️⃣ 모든 async 함수는 await 필수

```python
# ❌ 잘못된 방식 - await 빠짐
async def process_data():
    result = self.repository.get_by_id(id)  # async인데 await 없음!

# ✅ 올바른 방식
async def process_data():
    result = await self.repository.get_by_id(id)
```

### 4️⃣ 타입 힌트는 필수 (mypy strict)

```python
# ❌ 타입 힌트 부족
def calculate_score(data):  # data의 타입이?
    return data['score'] * 1.2

# ✅ 완전한 타입 힌트
from typing import Any
def calculate_score(data: dict[str, Any]) -> float:
    return data['score'] * 1.2
```

### 5️⃣ 환각 방지: 항상 원문을 Prompt에 포함

```python
# ❌ 잘못된 방식 - 원문 없이 LLM 호출
prompt = f"주제: {topic}에 대한 설명 작성"

# ✅ 올바른 방식 - 원문(context) 포함
prompt = f"""
원본 상담 내용:
{consultation.inquiry_text}

위 상담 내용을 바탕으로 매뉴얼을 작성하세요.
새로운 정보를 추가하지 마세요.
"""
```

### 6️⃣ 예외는 커스텀 예외 사용

```python
from app.core.exceptions import (
    RecordNotFoundError,
    ValidationError,
    VectorIndexError,
)

# 데이터를 찾지 못함
if not consultation:
    raise RecordNotFoundError(f"Consultation(id={id}) not found")

# 입력값 검증 실패
if not is_valid_data(data):
    raise ValidationError("Invalid consultation data")

# 벡터 인덱싱 실패
try:
    await vectorstore.index(...)
except Exception as exc:
    raise VectorIndexError(f"Vector index failed: {exc}")
```

### 7️⃣ 로깅은 구조화된 형식 사용

```python
from app.core.logging import get_logger

logger = get_logger(__name__)

# ❌ 문자열 포매팅
logger.info(f"Consultation created: {consultation.id}")

# ✅ 구조화된 로깅 (키=값)
logger.info("consultation_created", consultation_id=str(consultation.id))
logger.warning("vector_index_failed",
               consultation_id=str(consultation.id),
               error=str(exc))
```

---

## ❓ 자주 묻는 질문 (FAQ)

### Q1: "Mock 모드"와 "Real 모드"의 차이는?

**Mock 모드** (개발용):
```bash
VECTORSTORE_TYPE=mock
LLM_PROVIDER=mock
```
- 데이터베이스 필요 없음 (인메모리)
- LLM이 미리 정의된 응답만 반환
- 테스트와 로컬 개발에 최적

**Real 모드** (프로덕션):
```bash
VECTORSTORE_TYPE=pgvector  # 또는 pinecone, qdrant
LLM_PROVIDER=openai  # 또는 anthropic
OPENAI_API_KEY=sk-...
DATABASE_URL=postgresql://...
```
- 실제 PostgreSQL 데이터베이스 필요
- 실제 LLM API 호출
- 실제 벡터 검색

---

### Q2: "VectorStore"가 정확히 무엇인가요?

**VectorStore**는 텍스트를 **벡터(숫자 배열)**로 변환하여 저장하고 **의미론적 유사성**으로 검색하는 저장소입니다.

```
텍스트: "신용카드 결제 오류"
        ↓ (Embedding)
벡터:  [0.12, -0.45, 0.89, ..., 0.21]  (1536차원)

검색: "카드 결제 실패"
     ↓ (Embedding)
벡터: [0.11, -0.46, 0.88, ..., 0.22]

⚖️ 코사인 유사도 계산 → 0.95 (95% 유사)
```

**구현 옵션:**
- **mock**: 인메모리 (개발)
- **pgvector**: PostgreSQL 확장
- **pinecone**: 클라우드 벡터 DB
- **qdrant**: 오픈소스 벡터 DB

---

### Q3: 왜 RDB와 VectorStore가 따로 있나요?

| 구분 | RDB (PostgreSQL) | VectorStore |
|------|-----------------|-------------|
| **용도** | 원본 데이터 저장 | 검색 인덱스 |
| **신뢰성** | ⭐⭐⭐⭐⭐ ACID | ⭐⭐⭐ 부분 동기화 |
| **기능** | 정확한 필터링, 트랜잭션 | 의미론적 검색 |
| **실패 시** | 데이터 손실 | 검색 불가 (데이터 안전) |

**설계 원칙:**
- RDB = 원본 데이터 (진실의 원천)
- VectorStore = 검색 인덱스 (필요시 재구성 가능)

---

### Q4: 환각(Hallucination)을 방지하는 방법은?

**3가지 검증 방법:**

1. **키워드 검증**: 모든 키워드가 원문에 존재?
   ```python
   keywords = ["결제", "CVV", "인증"]
   source = "신용카드 결제 시 CVV 인증 실패..."
   # 모든 키워드 ✅ 포함되어 있음
   ```

2. **배경 검증**: 배경 문장들이 원문의 부분집합?
   ```python
   background = "신용카드로 결제할 때 CVV 인증 오류가 발생한다."
   source = "신용카드로 결제 시 'CVV 인증 실패' 오류 발생"
   # 원문에 포함되어 있음 ✅
   ```

3. **가이드라인 검증**: 가이드라인이 원문에 근거가 있는가?

---

### Q5: 매뉴얼 버전은 어떻게 관리되나요?

**금융권 정책 반영:**
- 매뉴얼 **승인마다 버전 +1** (1.0 → 1.1 → 1.2)
- 같은 키(업무구분/에러코드)의 **기존 항목은 DEPRECATED**
- **APPROVED 메뉴얼만** 검색에 노출
- 메뉴얼 트레이서빌리티: 상담 → 초안 → 승인

```
Consultation "CVV 오류"
  ↓
ManualEntry (DRAFT)
  ↓ (검토)
ManualEntry (APPROVED, v1.0)
  ↓ (같은 주제 새 상담)
ManualEntry (DRAFT)
  ↓ (승인)
ManualEntry (APPROVED, v1.1)

이전 v1.0 → DEPRECATED (검색에서 제외)
```

---

### Q6: 테스트는 어떻게 작성하나요?

**단위 테스트 (Service 테스트):**
```python
import pytest
from unittest.mock import AsyncMock, MagicMock

@pytest.mark.asyncio
async def test_register_consultation():
    # 1️⃣ Mock 객체 준비
    mock_repo = AsyncMock(spec=ConsultationRepository)
    mock_vectorstore = AsyncMock(spec=VectorStoreProtocol)

    # 2️⃣ Mock 반환값 설정
    mock_consultation = Consultation(id=UUID(...), ...)
    mock_repo.create_consultation.return_value = mock_consultation

    # 3️⃣ Service 생성 (mock 주입)
    service = ConsultationService(
        session=AsyncMock(),
        repository=mock_repo,
        vectorstore=mock_vectorstore,
    )

    # 4️⃣ 테스트 실행
    result = await service.create_consultation(ConsultationCreate(...))

    # 5️⃣ 검증
    assert result.id == mock_consultation.id
    mock_repo.create_consultation.assert_called_once()
    mock_vectorstore.index_document.assert_called_once()
```

**통합 테스트:**
- 실제 Repository + Service 조합 테스트
- 테스트 데이터베이스 사용
- VectorStore/LLM은 Mock으로 대체

---

### Q7: API 문서는 어디서 확인하나요?

```bash
# FastAPI 실행 후
uv run python main.py

# 브라우저 접속
# Swagger UI: http://localhost:8000/docs
# ReDoc: http://localhost:8000/redoc
```

모든 엔드포인트, 요청/응답 스키마, 예제가 자동으로 생성됩니다!

---

### Q8: MCP 서버는 무엇인가요?

**MCP (Model Context Protocol)**:
- Claude가 외부 시스템과 상호작용할 수 있게 해주는 프로토콜
- KHW의 서비스를 **Claude에서 직접 사용** 가능

```bash
# MCP 서버 실행
uv run python mcp_server.py

# Claude Desktop에서 KHW 도구 사용 가능
# - create_consultation: 상담 등록
# - search_consultations: 상담 검색
# - generate_manual_draft: 매뉴얼 생성
# - approve_review_task: 검토 승인
# 등...
```

자세한 설정은 [MCP_SETUP.md](docs/MCP_SETUP.md) 참조

---

### Q9: 프로덕션 배포 시 주의할 점은?

1. **환경 변수 설정**
   ```bash
   ENVIRONMENT=production
   DEBUG=false
   SECRET_KEY=<강력한 임의 문자열>
   ```

2. **데이터베이스**
   ```bash
   DATABASE_URL=postgresql+asyncpg://user:pass@prod-db.example.com/khw
   DATABASE_POOL_SIZE=20  # 증가
   ```

3. **VectorStore & LLM**
   ```bash
   VECTORSTORE_TYPE=pgvector  # 또는 cloud 서비스
   LLM_PROVIDER=openai
   OPENAI_API_KEY=sk-...
   ```

4. **로깅**
   ```bash
   LOG_LEVEL=INFO
   LOG_JSON=true  # 구조화된 로깅
   ```

5. **마이그레이션**
   ```bash
   # 배포 전 반드시 실행
   uv run alembic upgrade head
   ```

---

### Q10: 새로운 기능을 추가하려면 어떻게 해야 하나요?

**일반적인 절차:**

1. **Pydantic Schema 정의** (`app/schemas/`)
   ```python
   class NewFeatureCreate(BaseModel):
       name: str
       value: int
   ```

2. **SQLAlchemy Model 추가** (`app/models/`)
   ```python
   class NewFeature(BaseModel):
       __tablename__ = "new_features"
       name: Mapped[str]
       value: Mapped[int]
   ```

3. **Repository 메서드 추가** (`app/repositories/`)
   ```python
   class NewFeatureRepository(BaseRepository):
       async def create_feature(self, data: NewFeatureCreate) -> NewFeature:
           # CRUD 로직
   ```

4. **Service 비즈니스 로직 추가** (`app/services/`)
   ```python
   class SomeService:
       async def process_feature(self, data: NewFeatureCreate) -> Response:
           # 비즈니스 로직
   ```

5. **FastAPI Router 추가** (`app/routers/`)
   ```python
   @router.post("/features")
   async def create_feature(
       data: NewFeatureCreate,
       service: SomeService = Depends(get_service),
   ) -> Response:
       return await service.process_feature(data)
   ```

6. **테스트 작성** (`tests/`)
   ```python
   @pytest.mark.asyncio
   async def test_process_feature():
       # 테스트
   ```

7. **(선택) MCP 도구 추가** (`app/mcp/tools.py`)

---

## 🎓 다음 단계

축하합니다! 이제 KHW 프로젝트의 기본을 이해했습니다. 🎉

**추가로 학습할 사항:**
- 📚 [KHW_RFP.md](docs/KHW_RFP.md) - 전체 요구사항 정의서
- 📚 [MCP_SETUP.md](docs/MCP_SETUP.md) - MCP 서버 상세 설정
- 📚 [CLAUDE.md](CLAUDE.md) - 프로젝트 개발 지침

**첫 번째 기여:**
1. 간단한 버그 수정으로 시작
2. 테스트 추가 ([tests/unit/](tests/unit/) 참조)
3. 코드 리뷰 받기
4. 병합!

**도움이 필요하면:**
- Slack: #dev-khw 채널
- 문서: docs/ 폴더
- 이슈: GitHub Issues

---

## 📞 연락처 & 리소스

| 주제 | 담당자 | 연락처 |
|------|--------|--------|
| 아키텍처 & 설계 | 개발 리더 | slack: @dev-lead |
| LLM & 환각 방지 | AI 팀 | slack: @ai-team |
| 데이터베이스 | 데이터베이스 팀 | slack: @db-team |
| 배포 & 인프라 | DevOps | slack: @devops |

**유용한 링크:**
- 🔗 프로젝트 GitHub: https://github.com/your-org/k-helpdesk-wiki
- 🔗 API 문서: http://localhost:8000/docs (로컬 실행 후)
- 🔗 요구사항: [KHW_RFP.md](docs/KHW_RFP.md)

---

**Happy Coding! 🚀**

마지막으로, 질문이나 피드백이 있으면 망설이지 말고 팀에 물어보세요.
우리는 모두 새로 배운 사람들이었고, 함께 성장합니다! 💪
