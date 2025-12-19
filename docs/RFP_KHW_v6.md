# 📄 **RFP_KHW_v4.md**

**고객 상담 지식 관리 시스템(KHW) – RFP v4 (최종 요구사항 정의서)**
**FastAPI + SQLAlchemy 2.0 + VectorStore + LLM 기반**

---

# 0. 역할(Role)

당신은 Python 백엔드 아키텍트이다.
본 문서는 **고객 상담 내역 기반 자동 메뉴얼 생성·검색·검토·버전관리·LLM 기반 품질 보정·버전 비교 기능**을 포함한
**엔터프라이즈급 KHW 시스템**의 최종 요구사항을 정의한다.

---

# 1. 시스템 목표(Goal)

KHW(K Help Desk Wiki)의 목표:

1. 상담 내역을 RDB에 구조적으로 저장
2. VectorStore 기반 의미 검색
3. 상담 → 메뉴얼 자동 초안 생성 (LLM)
4. 기존 메뉴얼과의 유사도 비교 및 충돌 탐지
5. 메뉴얼 업데이트 필요 Task 자동 생성
6. LLM 환각 방지 및 입력 기반 규정 준수
7. RDB와 VectorStore 완전 분리 구조
8. MCP(멀티 에이전트)/CLI에서도 사용 가능한 Service Layer 구현
9. 메뉴얼 버전별 관리 및 **버전 간 차이 비교 기능 제공**

---

# 2. 시스템 주요 기능 (High-Level Features)

## ✔ 상담 관리

* 상담 등록 / 조회 / 검색
* 상담 기반 메뉴얼 초안 생성
* 상담 데이터 Embedding 인덱싱

## ✔ 메뉴얼 관리

* DRAFT / APPROVED / DEPRECATED 상태
* 메뉴얼 버전 세트 관리 (ManualVersion)
* APPROVED 상태만 VectorStore 인덱싱

## ✔ 리뷰(검토) 워크플로우

* 유사도 기반 Task 자동 생성
* 상담사/검토자 간 승인/반려 프로세스
* 기존 메뉴얼과의 Diff 요약

## ✔ 검색 기능

* VectorStore Top-K 기반 검색
* RDB 메타 필터 + Re-Ranking
* Threshold 기반 유사도 판단

## ✔ LLM 기반 기능

* 초안 생성
* 차이점 분석(Diff Summary)
* 환각 방지 로직 내장

## ✔ 버전 비교 기능 (FR-14)

* 동일 메뉴얼 세트 내 버전 간 비교
* 운영 버전 vs DRAFT 비교
* 변경된 항목/필드 단위 Diff 제공

---

# 3. 상세 기능 요구사항 (Functional Requirements)

---

# FR-1. 상담 등록(Create Consultation)

### 입력 필드

* branch_code, employee_id, screen_id, transaction_name
* business_type, error_code
* inquiry_text, action_taken
* created_at
* metadata_fields (JSONB)

### 처리

1. SQLAlchemy 2.0 Async 기반 저장
2. 저장 후 VectorStore Embedding 인덱싱
3. VectorStore 실패 시 Retry Queue에 적재
4. 기존 데이터는 RDB에 정상 저장되어야 함

### 엔티티

* Consultation
* ConsultationVectorIndex

---

# FR-2. 상담 기반 메뉴얼 초안 생성 (LLM 기반)

### LLM 입력

* inquiry_text
* action_taken
* business_type, error_code
* 기타 문맥 텍스트

### LLM 출력

* keywords (원문 단어만 사용)
* topic
* background
* guideline

### 환각 방지

* 원문 외 내용 생성 금지
* 규정·정책 문구 금지
* 추론형 문장 금지
* 키워드는 반드시 원문에 존재해야 함

### 후처리

* LLM 출력 검증 (키워드/문장 기반)
* 실패 시 ManualReviewTask 생성
* 성공 시 ManualEntry(DRAFT)로 저장

---

# FR-3. 상담 검색(Search Consultations)

### 처리

1. Query Embedding
2. Consultation VectorStore Top-K 검색
3. ID 기반 RDB 조회
4. 메타 필터 적용
5. Re-Ranking
6. 점수와 함께 결과 반환

---

# FR-4. 메뉴얼 등록/수정

## 1) 상태 관리

* ManualEntry 상태: DRAFT / APPROVED / DEPRECATED
* APPROVED만 VectorStore 인덱싱
* DRAFT는 검색 제외

## 2) 메뉴얼 수정 API (PUT /api/v1/manuals/{manual_id})

### 목적
DRAFT 상태의 자동 생성 메뉴얼을 검수자가 수정할 수 있도록 지원

### 요청 (Request)
```json
{
  "topic": "string (5-200자, 선택사항)",
  "keywords": ["string (1-3개, 선택사항)"],
  "background": "string (최소 10자, 선택사항)",
  "guideline": "string (줄바꿈으로 구분, 선택사항)",
  "status": "DRAFT|APPROVED|DEPRECATED (선택사항)"
}
```

### 응답 (Response 200 OK)
```json
{
  "id": "uuid",
  "created_at": "2024-01-15T10:00:00Z",
  "updated_at": "2024-01-15T10:00:00Z",
  "topic": "string",
  "keywords": ["string"],
  "background": "string",
  "guideline": "string",
  "status": "DRAFT|APPROVED|DEPRECATED",
  "source_consultation_id": "uuid",
  "version_id": "uuid|null",
  "business_type": "string|null",
  "error_code": "string|null"
}
```

### 설계 원칙

#### 원칙 1: DRAFT 전용 수정
- **DRAFT 상태인 메뉴얼만 수정 가능**
- APPROVED, DEPRECATED 상태는 수정 불가
- 위반 시: 400 Bad Request 응답 (ValidationError)

#### 원칙 2: 부분 업데이트 지원
- 제공된 필드만 업데이트
- 생략된 필드는 기존 값 유지
- 모든 필드가 선택사항 (Optional)
- 빈 요청도 허용 (변경 없음)

#### 원칙 3: APPROVED 강제 원칙
- PUT 요청으로는 status를 APPROVED로 변경 불가
- APPROVED로의 상태 변경은 **반드시 POST /approve 엔드포인트 사용**
- 이유:
  - 버전 관리 로직 필수 (ManualVersion 증가)
  - 기존 항목 DEPRECATED 처리
  - VectorStore 재인덱싱 필요
  - Audit trail 기록
- 위반 시: 400 Bad Request 응답 (ValidationError)

#### 원칙 4: DEPRECATED 상태로 변경 가능
- DRAFT → DEPRECATED 변경 가능
- 이는 메뉴얼 초안을 버리는 경우 사용

### 에러 응답

#### 404 Not Found
- 지정된 manual_id가 존재하지 않음

#### 400 Bad Request (ValidationError)
케이스:
1. DRAFT가 아닌 상태 메뉴얼 수정 시도
   ```
   "DRAFT 상태인 메뉴얼만 수정 가능합니다. 현재 상태: APPROVED"
   ```

2. status를 APPROVED로 변경 시도
   ```
   "APPROVED 상태로 변경하려면 /approve 엔드포인트를 사용하세요."
   ```

### 사용 시나리오

#### 시나리오 1: 자동 생성 메뉴얼 검수자 수정
```
1. POST /draft → 상담 기반 자동 생성 (DRAFT)
2. PUT /{manual_id} → 검수자가 필요한 부분 수정
3. POST /draft/{manual_id}/conflict-check → 충돌 감지
4. POST /approve/{manual_id} → 승인 및 버전 관리
```

#### 시나리오 2: guideline 라인 추가
```
PUT /api/v1/manuals/{manual_id}
{
  "guideline": "계정 상태 확인\n고객의 아이디를 확인하여 계정 잠김 여부를 확인합니다.\n브라우저 및 보안프로그램 점검\n고객이 사용 중인 브라우저 버전을 확인하고..."
}
```

#### 시나리오 3: 초안 폐기
```
PUT /api/v1/manuals/{manual_id}
{
  "status": "DEPRECATED"
}
```

---

# FR-5. 메뉴얼 버전 관리

### 버전 전략: **문서 세트 단위 버전 관리**

* 전체 메뉴얼 그룹이 하나의 version_id를 공유
* 새로운 메뉴얼 승인 시 version_id 증가
* 기존 항목 전체 DEPRECATED 처리
* 신규 항목 전체 APPROVED 처리

---

# FR-6. 신규 초안 vs 기존 메뉴얼 자동 비교

### 처리

1. ManualEntry(DRAFT)의 Embedding 생성
2. VectorStore Top-K 검색
3. Threshold 이상이면 유사 항목 존재로 판정
4. Diff Summary 생성 (LLM 기반)
5. ManualReviewTask 생성

---

# FR-7. 메뉴얼 검토 Workflow

### Task 상태

* TODO / IN_PROGRESS / DONE / REJECTED

### 승인 처리

* ManualVersion 증가
* 기존 항목 DEPRECATED
* 신규 항목 APPROVED
* VectorStore 재인덱싱

---

# FR-8. 메뉴얼/상담 검색

### Re-ranking 방식

1. Vector Similarity
2. Domain Score (error_code, business_type 일치 가중치)
3. Recency Score (버전 최신 가중치)

---

# FR-9. LLM 환각 방지 기능

* 원문 기반 Subset 요약만 허용
* 정책·추측·추론 문장 금지
* 키워드 검증
* background/guideline 검증
* 위반 시 생성 중단 + Task 생성

---

# FR-10. Task 관리

* Task 생성/조회/승인/반려
* Task 이력 저장
* Task Assignment
* Task별 Diff/유사도 정보 조회

---

# FR-11. VectorStore 처리 요구사항

### Metadata 스키마

```json
{
  "business_type": "string",
  "branch_code": "string",
  "error_code": "string",
  "manual_id": "number or null",
  "consultation_id": "number or null",
  "version": "number",
  "created_at": "timestamp"
}
```

### 실패 처리

* Retry Queue (Redis or RDB)
* Exponential Backoff
* Dead Letter Queue

---

# FR-12. MCP Ready 요구사항

* Service Layer는 Request/Response 의존 금지
* 순수 데이터 타입만 주고받기
* 모든 결과는 Pydantic 모델로 반환
* MCP Tool Wrapper에서 직접 호출 가능해야 함

---

# FR-13. 비기능 요구사항(NFR)

### 성능

* 검색 P95 ≤ 1초
* VectorStore 검색 150ms 이하
* 배치 처리 수백 건/분

### 확장성

* RDB ↔ VectorStore 완전 분리
* PostgreSQL → Oracle 전환 가능
* VectorStore Milvus/Qdrant 교체 가능

### 보안

* PII 암호화/마스킹
* RBAC
* 변경 이력 추적

### 모니터링

* 검색 latency
* LLM 호출 로그
* VectorStore 성공/실패율
* Task 처리량

---

# FR-14. 메뉴얼 버전별 비교 기능 (Version Diff)

## 1) 목적

* 동일 메뉴얼 세트 내 **서로 다른 버전(version_id)** 간 변경 사항 비교
* 운영 버전 vs 신규 DRAFT 변경 점검
* 히스토리 기반 변경 추적 기능 제공

---

## 2) 주요 시나리오

### 시나리오 A — 최신 버전 vs 직전 버전 비교

* manual_group_id 입력
* 최신 version_id와 직전 version_id 자동 선택

### 시나리오 B — 임의 두 버전 비교

* base_version, compare_version 직접 입력
* 각 버전의 ManualEntry 세트 비교

### 시나리오 C — 운영 버전 vs 특정 DRAFT

* 운영 버전의 ManualEntry 세트 vs DraftEntry 비교

---

## 3) 비교 단위 및 로직

### 항목 매칭 기준

* 논리 키(logical_key)
* 또는 (topic + business_type + error_code) 조합

### diff 구분

* `added_entries`
* `removed_entries`
* `modified_entries`

  * 변경된 필드만 포함 (keywords/topic/background/guideline)

### 응답 예시(JSON)

```json
{
  "base_version": 2,
  "compare_version": 3,
  "added_entries": [...],
  "removed_entries": [...],
  "modified_entries": [
    {
      "logical_key": "acct_new_01",
      "before": { "background": "...", "guideline": "..." },
      "after":  { "background": "...", "guideline": "..." }
    }
  ],
  "llm_summary": "옵션: 변경 요약"
}
```

---

## 4) LLM 요약 (옵션)

### 제한

* 시스템이 계산한 diff JSON 외 새로운 내용 생성 금지
* 정책/추측/제안 문구 생성 금지
* 실제 변경된 내용만 자연어 요약

### 사용 목적

* 검토자/관리자가 변경 흐름을 쉽게 이해하도록 지원

---

## 5) API 요구사항

### 1) 버전 목록 조회

`GET /manuals/{manual_group_id}/versions`

### 2) 두 버전 비교

`GET /manuals/{manual_group_id}/diff?base_version=&compare_version=`

### 3) 운영 버전 vs DRAFT 비교

`GET /manuals/drafts/{draft_id}/diff-with-active`

---


# 🆕 FR-15. 공통코드 관리 기능 (Common Code Management)

## 1) 목적

업무 구분(business_type), 에러코드(error_code), 지점 코드(branch_code), 화면구분 등의
**공통 코드들을 중앙에서 관리**하고
프론트엔드에서 API를 통해 사용할 수 있도록 제공한다.

이는 KHW 전체 기능의 일관성을 유지하는 핵심 인프라 기능이다.

---

## 2) 기능 범위

### ✔ 공통코드 그룹(CommonCodeGroup) 관리

* group_code (예: BUSINESS_TYPE, ERROR_CODE)
* group_name
* description
* is_active

### ✔ 공통코드 항목(CommonCodeItem) 관리

* code_key (예: "CAR_LOAN")
* code_value (예: "자동차 대출") 
* group_id (FK)
* description
* sort_order
* is_active

### ✔ 주요 특징

* 서브그룹 코드는 key:value 구조로 저장
* 코드 순서 변경 지원(sort_order)
* 코드 활성/비활성 관리

---

## 3) API 요구사항

### 관리자(Admin)용 API

```
GET    /admin/common-codes/groups
POST   /admin/common-codes/groups
GET    /admin/common-codes/groups/{group_code}/items
POST   /admin/common-codes/groups/{group_code}/items
PUT    /admin/common-codes/items/{id}
DELETE /admin/common-codes/items/{id}   (soft delete 권장)
```

### 프론트엔드 공통 코드 조회 API

```
GET  /common-codes/{group_code}
POST /common-codes/bulk   (예: ["BUSINESS_TYPE", "ERROR_CODE"])
```

### 응답 예시

```json
{
  "group_code": "BUSINESS_TYPE",
  "items": [
    { "key": "RETAIL", "value": "리테일" },
    { "key": "LOAN",   "value": "대출" }
  ]
}
```

---

## 4) 데이터베이스 요구사항

### CommonCodeGroup 테이블

* id (PK)
* group_code (Unique)
* group_name
* description
* is_active
* created_at, updated_at

### CommonCodeItem 테이블

* id (PK)
* group_id (FK)
* code_key
* code_value
* metadata (JSONB)
* sort_order
* is_active
* created_at, updated_at

---

## 5) 비기능 요구사항

* 코드 변경 시 모든 변경 이력 저장(옵션)
* 공통코드 조회 API는 캐싱 가능해야 함
* 공통코드 변경 후 반영을 위한 캐시 무효화 기능 제공(옵션)

---

# 🆕 FR-16. 메뉴얼 초안 조회 기능 (Manual Draft List View – API 기반 버전)**

*(기존 RFP_v5 + 제공된 API 스펙 반영한 최종본)*

---

## 1) 목적

상담사가 LLM으로 생성한 **메뉴얼 초안(DRAFT)** 을
이미 구현된 API인 **`GET /api/v1/manuals`** 를 활용해 목록 형태로 조회하고,
상태별 필터링(status_filter), limit 등의 파라미터를 이용하여 쉽게 탐색할 수 있도록 한다.

초안 목록 조회의 목적:

* DRAFT 상태 메뉴얼을 일괄적으로 확인
* 초안의 metadata(업무구분, 에러코드 등)를 기반으로 검색·필터링
* 검토자가 승인 대상 초안을 빠르게 식별
* “승인된 메뉴얼(Approved)” 과 구분되는 독립된 초안 관리 페이지 구현

---

## 2) 사용 API

### ✔ **기존 API 그대로 사용**

```
GET /api/v1/manuals
```

#### Query Parameters

| 파라미터          | 타입     | 설명                                                 |
| ------------- | ------ | -------------------------------------------------- |
| status_filter | string | DRAFT / APPROVED / DEPRECATED (초안 조회 시 기본값: DRAFT) |
| limit         | int    | 조회 개수 조절                                           |

#### 초안 조회에 필요한 값

초안 조회 페이지에서는:

```
GET /api/v1/manuals?status_filter=DRAFT&limit=100
```

이 호출만으로 충분히 초안 목록 정보를 구성할 수 있음.

---

## 3) API 응답 구조 기반 필드 정의 (RFP 반영)

제공된 응답 구조:

```json
[
  {
    "created_at": "2025-12-10T08:46:56.741Z",
    "updated_at": "2025-12-10T08:46:56.741Z",
    "id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
    "keywords": ["string"],
    "topic": "string",
    "background": "stringstri",
    "guideline": "stringstri",
    "business_type": "string",
    "error_code": "string",
    "source_consultation_id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
    "version_id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
    "status": "DRAFT",
    "business_type_name": "string"
  }
]
```

이 필드를 기준으로, 초안 목록 화면에서 사용되는 핵심 비즈니스 데이터는 다음과 같다:

| 필드                                 | 설명               | 비고                    |
| ---------------------------------- | ---------------- | --------------------- |
| id                                 | Draft ID         | 상세조회 시 사용             |
| created_at                         | 초안 생성 일시         | 최신순 정렬 기본값            |
| updated_at                         | 최근 수정 일시         |                       |
| topic                              | 초안 제목(토픽)        | 목록에서 핵심               |
| keywords                           | 원문에서 추출된 키워드     | 다중 표시 가능              |
| business_type / business_type_name | 업무 분류            | 공통코드 매핑               |
| error_code                         | 관련 오류코드          | 공통코드 매핑               |
| source_consultation_id             | 원본 상담 ID         | 상담 상세 페이지 연결          |
| version_id                         | 메뉴얼 버전 세트 ID     | APPROVED와 연결될 때 사용    |
| status                             | DRAFT/APPROVED 등 | 초안 목록에서는 DRAFT 필터로 조회 |

---

## 4) 기능 요구사항 (UI/비즈니스 관점에서 RFP 반영)

### ✔ 4.1 초안 목록 조회(List View)

#### Mandatory Columns

* topic
* keywords
* business_type_name
* error_code
* created_at
* status (항상 DRAFT)
* source_consultation_id
* actions (상세보기, 삭제 등)

#### Filtering Requirements

* status_filter = DRAFT 를 기본값으로 적용
* business_type 옵션 필터
* error_code 옵션 필터
* topic 부분 검색
* 기간 검색(created_at range)

---

### ✔ 4.2 상세 조회(Drill-down)

목록에서 특정 초안을 선택하면:

* topic
* keywords
* background
* guideline
* business_type_name
* error_code
* 원본 상담 내용 조회 링크(/consultations/{source_consultation_id})
* version_id (검토 후 승인되면 연결 예정)

---

### ✔ 4.3 삭제 정책

* 초안(DRAFT)은 삭제 가능
* 삭제는 soft-delete → 목록에서 제외
* 차후 검토 중인 초안(IN_PROGRESS)일 경우 삭제 불가 (추가 요구사항 가능)

---

## 5) 정렬/페이징 기준

#### 기본 정렬

```
created_at DESC
```

#### 페이징

* limit 기반 페이징
* 페이지네이션은 프론트에서 limit+cursor 방식 권장

---

## 6) VectorStore 영향

* 초안은 VectorStore 인덱싱 대상이 아니다.
* API가 background/guideline을 포함하더라도, 인덱싱은 APPROVED 단계에서 수행한다.

---

## 7) ERD 영향 없음

* 기존 ManualEntry 엔티티에 의존
* 목록조회는 내부적으로 ManualRepository.search() 형태로 처리 가능

---

# 🆕 FR-17. 상담 메뉴얼 작성 여부 관리 기능

*(Consultation Manual Creation Flag)*

## 1) 목적

상담(Consultation)이 **메뉴얼 초안 생성 프로세스를 거쳤는지 여부**를 RDB에서 명확히 관리한다.
상담 상세 화면에서 “메뉴얼 생성됨” 상태를 UI에 반영할 수 있어야 한다.

---

## 2) 데이터베이스 요구사항

### Consultation 테이블 확장

* `is_manual_generated` BOOLEAN NOT NULL DEFAULT false

  * 의미: 해당 상담을 기반으로 메뉴얼 초안 생성 프로세스가 **정상 완료**되었음을 나타냄

* `manual_generated_at` TIMESTAMP NULL *(선택)*

  * 의미: 메뉴얼 초안 생성 프로세스 완료 시각

> ⚠️ 주의
> Consultation 엔티티는 **특정 메뉴얼 엔트리(manual_entry_id)를 직접 참조하지 않는다.**

---

## 3) 처리 규칙

### 트리거 시점

* FR-2 「상담 기반 메뉴얼 초안 생성」 흐름에서
  LLM 생성 → 검증 → 비교 → Task 생성(필요 시)까지 포함한
  **초안 작성 프로세스가 정상 종료된 시점**에 상태를 변경한다.

### 업데이트 내용

* `is_manual_generated = true`
* `manual_generated_at = now()` *(선택)*

---

## 5) 예외 정책

* 초안 생성이 실패(LLM 검증 실패, 저장 실패 등)하여
  프로세스가 정상 종료되지 않은 경우
  → `is_manual_generated`는 **변경하지 않는다(false 유지)**

---

# 🆕 FR-18. 사용자 인증 및 접근 제어 (Authentication & Authorization)

## 1) 목적

KHW 시스템은 **인증된 사용자만 접근 가능**해야 하며,
사용자 역할(Role)에 따라 **기능 접근 범위가 명확히 분리**되어야 한다.

본 기능은 모든 FR의 **전제 조건(Foundation Layer)** 이다.

---

## 2) 인증 요구사항 (Authentication)

### ✔ 인증 방식

* JWT 기반 인증
* Access Token 필수
* 모든 `/api/v1/**`, `/admin/**` 엔드포인트에 인증 적용
* Swagger(OpenAPI)에서도 인증 헤더 입력 가능해야 함

### ✔ 처리 규칙

* 인증 실패 → 401 Unauthorized
* 토큰 만료 → 401 Unauthorized
* 인증 정보 없음 → 401 Unauthorized

---

## 3) 사용자 역할(Role)

| Role       | 설명                    |
| ---------- | --------------------- |
| CONSULTANT | 상담 등록, 상담 조회, 초안 생성, 초안 조회, 메뉴얼 조회   |
| REVIEWER   | 상담 등록, 상담 조회, 초안 생성, 초안 조회, 메뉴얼 조회, 메뉴얼 검토(Task), 승인/반려   |
| ADMIN      | 모든권한인가 |

---

## 4) 인가(Authorization) 규칙

* FR-7(메뉴얼 승인)은 REVIEWER 이상만 가능
* FR-15(공통코드 관리)는 ADMIN 만 가능
* FR-16(초안 조회)는 초안을 작성한 CONSULTANT 또는 관리자만 가능

---

## 5) 비기능 요구사항

* Service Layer는 인증 객체에 의존하지 않는다
* 인증 컨텍스트는 Router Layer에서만 처리한다

---

# 🆕 FR-19. 부서 및 사용자 매핑 관리

## 1) 목적

사용자는 반드시 **하나 이상의 부서(Department)** 에 소속되며,
부서는 **상담 조회 범위·검토 권한·업무 책임 범위**의 기준이 된다.

---

## 2) 데이터 모델 요구사항

### Department

* id (PK)
* department_code (Unique)
* department_name
* is_active
* created_at, updated_at

### UserDepartment (Mapping)

* user_id (FK)
* department_id (FK)
* is_primary BOOLEAN
* created_at

---

## 3) 처리 규칙

* 사용자는 최소 1개의 부서에 소속되어야 함

---

## 4) 확장 고려

* 다부서 겸임 가능
* 향후 부서 기반 통계/권한 확장 가능

---

# 🆕 FR-20. 사용자별 검토(Task) 항목 노출 제어

## 1) 목적

메뉴얼 검토(Task)는 **모든 사용자에게 노출되지 않으며**,
지정된 사용자 또는 역할 기반으로만 조회 가능해야 한다.

---

## 2) Task 할당 방식

* Task 생성 시:

  * reviewer_role
  * reviewer_department_id (선택)
  * reviewer_user_id (선택)

---

## 3) 조회 규칙

| 사용자        | 조회 가능 Task         |
| ---------- | ------------------ |
| CONSULTANT | 본인이 생성한 초안 관련 Task |
| REVIEWER   | 본인 또는 소속 부서 Task   |
| ADMIN      | 전체 Task            |

---

## 4) 보안 요구사항

* Task ID 직접 접근 시 권한 검증 필수
* 권한 없는 Task 접근 → 403 Forbidden

---

# 🆕 FR-21. 상담 입력 메타정보 동적 관리 기능

## 1) 목적

상담 입력 시 요구되는 메타 정보는
**운영 정책에 따라 변경 가능**해야 하며,
관리자가 UI/API를 통해 관리할 수 있어야 한다.

---

## 2) 관리 대상 메타 정보 예시

* 필수 입력 여부
* 표시 여부
* 입력 타입 (text / select / number)
* 공통코드 연동 여부

---

## 3) 데이터 모델 (예시)

### ConsultationMetaField

* id (PK)
* field_key
* field_label
* field_type
* is_required
* is_active
* sort_order
* linked_common_code_group (nullable)
* created_at, updated_at

---

## 4) 처리 규칙

* is_required=true 인 항목은 상담 등록 시 필수
* 필수값 누락 → 400 ValidationError
* 메타 필드 변경 시 즉시 반영
z

# 🆕 FR-22. 상담 입력 시 유사 메뉴얼 사전 탐색 기능

## 1) 목적

상담 등록 또는 입력 과정에서
**이미 존재하는 유사 메뉴얼을 즉시 안내**하여
중복 초안 생성을 사전에 방지한다.

---

## 2) 처리 흐름

1. 상담 입력 중 임시 텍스트 수집
2. VectorStore 임시 검색 수행
3. 유사도 Threshold 초과된 3개의 메뉴얼 반환 
4. top 1의 자료의 topic, keywords, background, guideline, business_type, error_code, source_consultation_id 등의 정보를 보여줌
5. 추가로 추천 자료로 top-2, top-3의 topic을 보여주며 클릭시 해당 메뉴얼을 팝업으로 볼 수 있게 한다.

---

## 3) 기술 요구사항

* 임시 Embedding 허용 (저장 ❌)
* 검색 결과는 APPROVED 메뉴얼만 대상
* Threshold는 설정값으로 관리

---

## 4) UX 정책 (참고)

* 경고 수준 알림 (강제 차단 ❌)
* 초안 생성은 사용자가 선택

---

# 🆕 FR-23. 관리자 전용 랜딩 페이지

## 1) 목적

관리자는 시스템 운영 상태를 **한 화면에서 파악**할 수 있어야 한다.

---

## 2) 주요 정보

* 미처리 Task 수
* 신규 DRAFT 수
* 최근 승인 메뉴얼
* 공통코드 변경 이력
* VectorStore 저장 이력(실패, 성공)

---

## 3) 접근 제어

* ADMIN Role 전용
* 일반 사용자 접근 시 403

---

# 🆕 FR-24. FAST MCP 기반 MCP 확장 기능

## 1) 목적

KHW의 핵심 기능을
**MCP(Model Context Protocol)** 기반으로 외부 AI가 직접 호출할 수 있도록 한다.

---

## 2) 제공 MCP Tool 예시

* create_consultation
* search_consultations
* generate_manual_draft
* get_manual_diff
* approve_review_task

---

## 3) 설계 원칙

* MCP는 **확장 인터페이스**
* 모든 로직은 기존 Service Layer 재사용
* MCP 전용 비즈니스 로직 금지

---

## 4) 보안 정책

* MCP 호출도 인증 필수
* Role 기반 접근 제어 동일 적용

---


# 4. 개발 산출물 요구사항

1. SQLAlchemy 2.0 모델 전체
2. Repository Layer
3. Service Layer
4. VectorStore Protocol 및 Mock
5. LLM Prompt Template
6. 메뉴얼 생성/비교/검증 로직
7. ReviewTask 워크플로우
8. Version Diff 기능(FR-14)
9. **공통코드 관리 기능(FR-15)**
10. FastAPI Router 전체
11. Retry Queue / Dead Letter Queue 처리 모듈
12. ERD, 시퀀스 다이어그램

---

# 📌 문서 버전 정보

* 문서 버전: **v5.0**
* 포함된 기능 범위: FR-1 ~ FR-15
* 적용 프레임워크: FastAPI, SQLAlchemy 2.0, PostgreSQL, VectorStore(Milvus/pgvector), MCP Ready

---
