# 벡터 DB 임베딩 타임라인 & 데이터 흐름 완벽 분석

## 📊 임베딩 시점 타이밍 (Timeline)

### 1️⃣ 상담(Consultation) 임베딩

**시점: 상담 등록 직후 (RDB 저장 완료 후)**

```
POST /api/v1/consultations
  ↓
ConsultationService.create_consultation(data)
  ├─ 1️⃣ await repository.create_consultation(data)
  │   └─ RDB 저장: consultations 테이블에 INSERT (COMMITTED)
  │
  ├─ 2️⃣ try: await _index_consultation_vector(consultation)
  │   ├─ 벡터 텍스트 구성: _build_embedding_text()
  │   ├─ 메타데이터 구성: _build_vector_metadata()
  │   └─ vectorstore.index_document() 호출
  │       └─ VectorStore에 저장 (pgvector/mock)
  │
  └─ 3️⃣ except Exception: _enqueue_index_retry()
      └─ 실패 시 RetryQueueJob 생성
          → 백그라운드에서 재시도
```

**타이밍 특징:**
- ✅ **즉시 (Synchronous)**: RDB 저장 후 바로 임베딩 시도
- ⚠️ **Non-blocking 실패**: 임베딩 실패해도 응답은 전송 (RDB는 안전)
- 🔄 **재시도 메커니즘**: 실패 시 RetryQueueJob 등록

**코드 위치:** app/services/consultation_service.py:54-78

---

### 2️⃣ 매뉴얼(Manual) 임베딩 - 승인 시점

**시점: 매뉴얼 승인 시 (상태 DRAFT → APPROVED)**

```
POST /api/v1/manual-review/tasks/{task_id}/approve
  ↓
TaskService.approve_task()
  ↓
ManualService.approve_manual()
  ├─ 1️⃣ 최신 버전 확인
  │   └─ 새 버전 번호 생성 (ManualVersion 생성)
  │
  ├─ 2️⃣ manual.status = ManualStatus.APPROVED
  │   └─ RDB 업데이트: manual_entries.status = 'APPROVED'
  │
  ├─ 3️⃣ await _index_manual_vector(manual)
  │   ├─ 벡터 텍스트 구성: _build_manual_text()
  │   ├─ 메타데이터 구성 (business_type, error_code, created_at)
  │   └─ vectorstore.index_document() 호출
  │       └─ VectorStore에 저장
  │
  └─ 4️⃣ TaskHistory 기록
      └─ 상태 변경 감사 추적
```

**타이밍 특징:**
- ✅ **APPROVED만**: DRAFT 상태에서는 벡터스토어에 저장 안 함
- ✅ **버전 관리와 함께**: 버전 승인 후 임베딩
- ❌ **검색에 노출**: DRAFT는 검색 불가, APPROVED만 검색 가능

**코드 위치:** app/services/manual_service.py:482-550, 1215-1238

---

### 3️⃣ 매뉴얼 수정 → 재인덱싱 (선택사항)

**시점: 초안 수정 후 (재인덱싱 필요한 경우)**

```
PATCH /api/v1/manuals/{manual_id}
  ↓
ManualService.update_manual()
  └─ RDB만 업데이트 (DRAFT 상태 유지)
     └─ ❌ VectorStore 미변경
        (DRAFT이므로 어차피 검색에 미노출)
```

**특징:**
- 🔒 **DRAFT는 벡터 미반영**: 수정 내용이 벡터스토어에 반영되지 않음
- ✅ **승인 시점에 최종 반영**: 승인될 때 최종 내용으로 임베딩

---

## 📦 임베딩 데이터 구조

### 1️⃣ 상담(Consultation) 임베딩 데이터

**임베딩 텍스트 (embedding text):**
```python
# app/services/consultation_service.py:165-174
def _build_embedding_text(self, consultation: Consultation) -> str:
    parts = [
        f"[요약]{consultation.summary}",
        f"[문의]{consultation.inquiry_text}",
        f"[조치]{consultation.action_taken}",
    ]
    return "\n".join(parts)
```

**예시:**
```
[요약]신용카드 결제 오류 발생
[문의]CVV 인증 시 "Invalid CVV" 에러 발생
[조치]결제 서버 로그 확인 후 프로빌더와 연락하여 해결
```

**메타데이터 (metadata):**
```python
# app/services/consultation_service.py:181-189
{
    "branch_code": "001",           # 지점 코드
    "business_type": "카드결제",     # 업무구분 (공통코드)
    "error_code": "CVV_AUTH_FAIL",  # 에러코드 (공통코드)
    "created_at": "2025-12-18T10:30:00Z"  # 생성 시간
}
```

**VectorStore 저장 위치:**
- 타입별:
  - `mock`: Python dict (메모리, 서버 재시작 시 손실)
  - `pgvector`: 별도 벡터 테이블 (`consultation_vectors` 테이블, pgvector 확장)
  
- ❌ `consultation_vector_index` RDB 테이블: 설계만 있음 (미사용)

**저장 구조 (pgvector):**
```sql
-- pgvector 자동 관리 테이블
CREATE TABLE consultation_vectors (
    id UUID PRIMARY KEY,
    embedding vector(1536),  -- OpenAI embedding dimension
    metadata JSONB,
    branch_code TEXT,
    business_type TEXT,
    error_code TEXT,
    created_at TIMESTAMPTZ
)
```

---

### 2️⃣ 매뉴얼(Manual) 임베딩 데이터

**임베딩 텍스트 (embedding text):**
```python
# app/services/manual_service.py:1240-1247
def _build_manual_text(self, manual: ManualEntry) -> str:
    parts = [
        "[키워드] " + ", ".join(manual.keywords or []),
        f"[주제] {manual.topic}",
        f"[배경] {manual.background}",
        f"[가이드라인] {manual.guideline}",
    ]
    return "\n".join(parts)
```

**예시:**
```
[키워드] CVV 인증, 결제 실패, 카드 오류
[주제] 신용카드 결제 중 CVV 인증 실패 해결 방법
[배경] 사용자가 신용카드로 결제할 때 CVV 검증 단계에서 "Invalid CVV" 에러 발생
[가이드라인] 1) 카드사 콜센터 연락 2) 카드정보 재입력 3) 결제 서버 상태 확인
```

**메타데이터 (metadata):**
```python
{
    "business_type": "카드결제",
    "error_code": "CVV_AUTH_FAIL",
    "created_at": "2025-12-18T11:00:00Z"
}
```

**VectorStore 저장 위치:**
- 타입별:
  - `mock`: Python dict (메모리)
  - `pgvector`: 별도 벡터 테이블 (`manual_vectors` 테이블)

- ❌ `manual_vector_index` RDB 테이블: 설계만 있음 (미사용)

**저장 구조 (pgvector):**
```sql
CREATE TABLE manual_vectors (
    id UUID PRIMARY KEY,
    embedding vector(1536),
    metadata JSONB,
    business_type TEXT,
    error_code TEXT,
    created_at TIMESTAMPTZ
)
```

---

## 🔄 벡터 임베딩 생성 프로세스

### 흐름도:

```
입력 텍스트 (embedding text)
  ↓
LLM Client (app/llm/)
  ├─ PROVIDER=mock → 고정 임베딩 반환 (테스트용)
  ├─ PROVIDER=openai → OpenAI API 호출 (gpt-3.5-turbo embeddings)
  ├─ PROVIDER=anthropic → Claude embeddings API 호출
  └─ PROVIDER=ollama → 로컬 Ollama 모델 호출
  ↓
벡터 (1536차원 float array)
  ↓
VectorStore.index_document()
  └─ pgvector: INSERT/UPDATE 쿼리 실행
  └─ mock: dict에 저장
```

**현재 설정 (mock mode):**
```python
# .env.example
VECTORSTORE_TYPE=mock          # 메모리 벡터스토어
LLM_PROVIDER=mock              # 고정 임베딩 반환
VECTORSTORE_DIMENSION=1536     # OpenAI 차원
```

---

## 🔍 VectorStore 쿼리 구조

### 1️⃣ 상담 검색 (Semantic Search)

```python
# app/services/consultation_service.py:200-264
# _search_consultations()

# 1️⃣ VectorStore에서 top-k 후보 검색
results = await self.vectorstore.search(
    query="카드 결제 오류",           # 검색어
    top_k=10,                      # 상위 10개
    metadata_filter={
        "branch_code": "001",      # 지점 필터
        "business_type": "카드결제", # 업무구분 필터
    }
)

# 2️⃣ 메타데이터 필터 추가 적용
# 3️⃣ 유사도 점수 필터 (threshold=0.7)
# 4️⃣ RerankerService로 재순위
```

**SQL 쿼리 (pgvector):**
```sql
SELECT id, metadata, 1.0/(1.0+(embedding <-> :embedding)) AS score
FROM consultation_vectors
WHERE business_type = $1 AND error_code = $2 AND branch_code = $3
ORDER BY embedding <-> :embedding
LIMIT 10
```

### 2️⃣ 매뉴얼 검색 (Semantic Search)

```python
# app/services/manual_service.py
# search_manuals()

results = await self.vectorstore.search(
    query="결제 실패",
    top_k=10,
    metadata_filter={
        "business_type": "카드결제"
    }
)
```

---

## 🗄️ RDB와 VectorStore 동기화

### 데이터 일관성 전략:

| 작업 | RDB | VectorStore | 상태 |
|------|-----|-------------|------|
| Consultation 등록 | ✅ INSERT | ✅ index_document() | 즉시 동기화 |
| Manual DRAFT 수정 | ✅ UPDATE | ❌ 미변경 | 비동기 |
| Manual 승인 | ✅ UPDATE status | ✅ index_document() | 승인 시 동기화 |
| Consultation 삭제 | ✅ DELETE | ✅ delete() | 즉시 동기화 |
| Manual DRAFT 삭제 | ✅ DELETE | ✅ delete() (if indexed) | 즉시 동기화 |

### 실패 시나리오:

```
Consultation 저장 중 실패
  → RDB 미저장, 응답 실패 ✅ OK

Consultation 저장 성공, 임베딩 실패
  → RDB 저장됨 ✅ OK
  → RetryQueueJob 등록 (재시도)
  → 응답: 201 Created (임베딩 실패 무시) ✅ OK

Manual 승인 중 임베딩 실패
  → RDB 상태 APPROVED로 업데이트됨
  → RetryQueueJob 등록 (재시도)
  → 응답: 200 OK (임베딩 재시도 중)
```

**원칙: "RDB = 진실의 원천, VectorStore = 검색 인덱스"**

---

## 📋 임베딩 데이터 요약

### Consultation 임베딩

| 항목 | 값 |
|------|-----|
| **임베딩 시점** | 등록 직후 (동기) |
| **포함 텍스트** | [요약][문의][조치] (3가지) |
| **메타데이터** | branch_code, business_type, error_code, created_at |
| **저장소** | VectorStore (pgvector/mock) |
| **RDB 추적** | ❌ consultation_vector_index 미사용 |
| **검색 노출** | ✅ 즉시 (모든 상담) |
| **재인덱싱** | ❌ 미지원 (삭제 후 재등록만 가능) |

### Manual 임베딩

| 항목 | 값 |
|------|-----|
| **임베딩 시점** | 승인 시 (DRAFT→APPROVED) |
| **포함 텍스트** | [키워드][주제][배경][가이드라인] (4가지) |
| **메타데이터** | business_type, error_code, created_at |
| **저장소** | VectorStore (pgvector/mock) |
| **RDB 추적** | ❌ manual_vector_index 미사용 |
| **검색 노출** | ✅ APPROVED만 (DRAFT 미노출) |
| **재인덱싱** | ✅ UPSERT로 자동 반영 |

---

## 🚀 실제 동작 예시

### 예시 1: Consultation 임베딩

```
1. API 호출
   POST /api/v1/consultations
   {
     "summary": "신용카드 결제 오류",
     "inquiry_text": "CVV 인증 시 Invalid CVV 에러",
     "action_taken": "카드사 확인 후 재시도",
     "branch_code": "001",
     "business_type": "카드결제",
     "error_code": "CVV_AUTH_FAIL"
   }

2. RDB 저장
   INSERT INTO consultations (id, summary, inquiry_text, ...)
   VALUES (...)
   → consultation_id = "550e8400-e29b-41d4-a716-446655440000"

3. 벡터 구성
   embedding_text = """
   [요약]신용카드 결제 오류
   [문의]CVV 인증 시 Invalid CVV 에러
   [조치]카드사 확인 후 재시도
   """
   
   metadata = {
     "branch_code": "001",
     "business_type": "카드결제",
     "error_code": "CVV_AUTH_FAIL",
     "created_at": "2025-12-18T10:30:00Z"
   }

4. VectorStore 저장
   vectorstore.index_document(
     id="550e8400-e29b-41d4-a716-446655440000",
     text=embedding_text,
     metadata=metadata
   )
   → consultation_vectors 테이블에 INSERT

5. 응답
   201 Created
   {
     "id": "550e8400-e29b-41d4-a716-446655440000",
     "summary": "신용카드 결제 오류",
     ...
   }
```

### 예시 2: Manual 임베딩 (승인)

```
1. API 호출
   POST /api/v1/manual-review/tasks/{task_id}/approve
   {
     "approver_id": "ADMIN001"
   }

2. RDB 상태 업데이트
   UPDATE manual_entries SET status='APPROVED' WHERE id=...
   UPDATE manual_versions SET ...
   UPDATE manual_review_tasks SET status='DONE' WHERE id=...

3. 벡터 구성
   embedding_text = """
   [키워드] CVV 인증, 결제 실패, 카드 오류
   [주제] 신용카드 결제 중 CVV 인증 실패 해결
   [배경] 사용자가 신용카드 결제 중 CVV 검증 단계에서 오류 발생
   [가이드라인] 1) 카드사 연락 2) 카드정보 재입력 3) 결제 서버 확인
   """
   
   metadata = {
     "business_type": "카드결제",
     "error_code": "CVV_AUTH_FAIL",
     "created_at": "2025-12-18T11:00:00Z"
   }

4. VectorStore 저장 (UPSERT)
   vectorstore.index_document(
     id=manual_id,
     text=embedding_text,
     metadata=metadata
   )
   → manual_vectors 테이블에 UPSERT
      (기존 버전은 UPDATE로 덮어씀)

5. 응답
   200 OK
   {
     "version": "1.0",
     "approved_at": "2025-12-18T11:00:00Z"
   }
```

---

## ⚙️ 설정 및 환경 변수

```bash
# .env
VECTORSTORE_TYPE=pgvector          # 또는 mock, pinecone, qdrant
LLM_PROVIDER=openai                # 또는 anthropic, ollama, mock
LLM_MODEL=gpt-4-turbo-preview
VECTORSTORE_DIMENSION=1536         # OpenAI 기본값
OPENAI_API_KEY=sk-...              # 필요 시

# 개발 환경 (기본값, 외부 서비스 불필요)
VECTORSTORE_TYPE=mock
LLM_PROVIDER=mock
```

---

## 🔧 주요 코드 위치

| 기능 | 파일 | 행번호 |
|------|------|--------|
| Consultation 임베딩 | app/services/consultation_service.py | 54-78 |
| Consultation 벡터 텍스트 | app/services/consultation_service.py | 165-174 |
| Consultation 메타데이터 | app/services/consultation_service.py | 181-189 |
| Manual 임베딩 | app/services/manual_service.py | 1215-1238 |
| Manual 벡터 텍스트 | app/services/manual_service.py | 1240-1247 |
| VectorStore 추상화 | app/vectorstore/protocol.py | - |
| pgvector 구현 | app/vectorstore/pgvector.py | - |
| Mock 구현 | app/vectorstore/mock.py | - |

---

## 📌 최종 결론

**임베딩 시점:**
- 🔴 **Consultation**: 등록 직후 (RDB 저장 완료 후 즉시)
- 🟡 **Manual**: 승인 시점 (APPROVED 상태 변경 시)

**임베딩 데이터:**
- **Consultation**: 요약 + 문의 + 조치 (3가지 필드)
- **Manual**: 키워드 + 주제 + 배경 + 가이드라인 (4가지 필드)
- **공통 메타데이터**: branch_code, business_type, error_code, created_at

**저장 메커니즘:**
- ✅ **RDB**: 절대적 진실의 원천 (PostgreSQL)
- ✅ **VectorStore**: 검색 인덱스 (pgvector/mock/Pinecone/Qdrant)
- ❌ **RDB 추적 테이블**: consultation_vector_index, manual_vector_index 미사용

**실패 처리:**
- 임베딩 실패 시 RetryQueueJob 등록
- RDB 데이터는 항상 안전하게 유지
