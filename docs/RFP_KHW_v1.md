# 🚀 **고객 상담 지식 관리 시스템(KHW) – RFP v4 (최종 완전체)**

FastAPI + SQLAlchemy 2.0 + VectorStore + LLM 기반

---

# 0. 역할(Role)

당신은 Python 백엔드 아키텍트이다.
본 문서는 **고객 상담 내역 기반 자동 메뉴얼 생성·검색·검토·버전관리·LLM 기반 품질 보정**이 가능한 **엔터프라이즈급 KHW 시스템**의 최종 요구사항 정의서이다.

---

# 1. 시스템 목표(Goal)

KHW(K Help Desk Wiki)의 목표:

1. 상담 내역을 RDB에 구조적으로 저장
2. VectorStore 기반 의미 검색
3. 상담 → 메뉴얼 자동 초안 생성 (LLM)
4. 기존 메뉴얼과의 유사도 비교 및 충돌 탐지
5. 업데이트 검토 Workflow 자동화
6. LLM 환각 방지 및 입력 기반 규정 준수
7. RDB와 VectorStore 완전 분리로 확장성 보장
8. MCP/CLI 등 외부 에이전트에서도 재사용 가능한 Service Layer 제공

---

# 2. 시스템 주요 기능

## ✔ 1) 상담 관리

* 상담 등록 / 상세조회
* 의미기반 검색
* "메뉴얼 생성하기" 버튼 제공
* 대량 상담 데이터 저장 구조

---

## ✔ 2) 메뉴얼 관리

* 메뉴얼 초안(DRAFT) 생성
* 버전 관리(ManualVersion)
* APPROVED 상태만 VectorStore 인덱싱
* 항목별 독립 VectorStore Index
* 기존 메뉴얼과 신규 초안 비교(LLM 기반)

---

## ✔ 3) 메뉴얼 업데이트 검토 Workflow

* 유사도 기반 업데이트 필요 Task 자동 생성
* TODO → IN_PROGRESS → DONE/REJECTED
* 승인 시 자동 version up
* 반려 시 초안 유지 또는 폐기

---

## ✔ 4) LLM 기반 기능

* 요약/배경/가이드라인 생성
* 키워드 추출
* 기존 메뉴얼과 차이점 비교
* 환각 방지 로직 강제
* 입력 기반 문장 집합에서만 재구성

---

## ✔ 5) 검색 기능 (RDB + VectorStore Re-ranking)

* VectorStore Top-K 검색
* RDB 메타 필터 적용
* 3단계 Re-Ranking 적용
* Threshold 기반 필터
* 검색 latency 로깅

---

## ✔ 6) Task 관리

* 메뉴얼 업데이트 자동 Task 생성
* 검토자 Assignment
* 이력(TaskHistory) 저장
* Web UI용 상세 비교 데이터 제공

---

# 3. 기능 요구사항 상세(FR)

---

# FR-1. 상담 등록(Create Consultation)

### 입력 필드

* branch_code
* employee_id
* screen_id
* transaction_name
* business_type
* error_code
* inquiry_text
* action_taken
* created_at
* metadata_fields(JSONB)

### 처리 요구사항

1. SQLAlchemy 2.0 Async 기반 저장
2. 저장 후 VectorStore 인덱싱 (비동기)
3. VectorStore 실패 → Retry Queue로 재처리
4. Retry Queue는 Redis/RDB 기반 선택 가능 (후술)
5. 상담 엔티티

   * Consultation
   * ConsultationVectorIndex

### 출력

* 저장된 Consultation DTO

---

# FR-2. 상담 기반 메뉴얼 초안 생성 (LLM)

### 트리거

상담 저장 직후 “메뉴얼 생성하시겠습니까?” Yes 선택

### LLM 입력

* inquiry_text
* action_taken
* business_type
* error_code

### LLM 출력 항목

* keywords (원문 단어만 사용)
* topic
* background
* guideline

### 환각 방지 규칙

* 원문 문장 외 문장 생성 금지
* 모호한 추론형 문장 금지 (“가능성 있음”, “추정됨” 등)
* 규정·정책 문구 생성 금지
* 키워드는 반드시 원문에 존재해야 함

### 후처리

* LLM 출력 검증: 원문 기반 여부 체크
* 실패시 ManualReviewTask 생성
* 성공 시 ManualEntry(DRAFT)로 저장

---

# FR-3. 상담 검색(Search Consultations)

### 입력

* query
* filters (business_type, branch_code, error_code, 기간 등)

### 처리 흐름

1. Query를 embedding으로 변환
2. Consultation VectorStore에서 Top-K ID 검색
3. ID 기반 RDB 조회
4. 메타 필터 적용
5. 3단계 Re-Ranking(세부는 아래 FR-8)
6. 결과 반환

---

# FR-4. 메뉴얼 등록/수정

### 규칙

* ManualEntry 상태 = DRAFT/APPROVED/DEPRECATED
* APPROVED 상태일 때만 VectorStore 인덱싱
* DRAFT는 검색 제외

---

# FR-5. 메뉴얼 버전 관리 (문서 세트 버전 방식)

### 선택된 버전 전략

→ **문서 전체가 하나의 Version Set을 공유(정책집 개념)**

### 이유

* 금융권 메뉴얼은 "한 번에 배포·적용"이 관례
* 전체 버전 롤백이 용이
* 승인 시 같은 version_id로 묶어서 관리 가능

### 요구사항

1. 신규 메뉴얼 승인은 전체 세트의 ManualVersion +1
2. 기존 항목은 DEPRECATED
3. 신규 항목은 APPROVED
4. Version 간 차이 비교 기록

---

# FR-6. 신규 초안과 기존 메뉴얼 자동 비교

### 처리

1. 신규 초안 Embedding 생성
2. Manual VectorStore에서 Top-K 검색
3. Threshold 이상이면 Task 생성
4. LLM으로 차이점 비교 (입력 기반, 환각 금지)
5. Task 상세에 diff 포함

---

# FR-7. 메뉴얼 검토 Workflow

### 기능

* Task 목록 조회
* 상태: TODO / IN_PROGRESS / DONE / REJECTED
* Task 상세

  * 기존 메뉴얼
  * 신규 초안
  * 유사도 점수
  * LLM 차이점 비교
* 승인/반려 처리

### 승인 시 후처리

* ManualVersion 증가
* 기존 항목 Deprecated
* 신규 항목 Approved
* VectorStore 인덱싱 재생성

---

# FR-8. 메뉴얼/상담 검색 (Re-ranking 포함)

검색은 3중 점수 정렬 수행:

### (1) **Vector Similarity Score(기본)**

* Cosine similarity

### (2) **도메인 메타 가중치(Business Type, Error Code 등)**

* 도메인 일치 시 +가중치
* 예) error_code 정확 일치 = +0.2

### (3) **문서 최신성 가중치**

* version 최신일수록 +0.1

### 처리 순서

Vector Top-K → RDB Filter → Re-Ranking → 반환

---

# FR-9. LLM 환각 방지 기능 (고도화)

### 금지 규칙

* 원문 문장에 없는 단어 삽입 금지
* 모호한 확률·추정·가정 문장 금지
* 규정·정책 문구 자동 생성 금지

### LLM 출력 검증 로직

* 키워드: 원문에 해당 단어 존재하는지 검사
* background/guideline: 원문 문장 집합 내 Subset인지 확인
* 위반 시 생성 자동 실패 → ManualReviewTask 생성

---

# FR-10. Task 관리

* Task 상태 변경 API
* TaskHistory 저장
* Assignment(담당자 배정)
* Task 검색 필터
* 승인/반려 시 Web UI에 diff 제공

---

# FR-11. VectorStore 처리 요구사항

### Metadata 스키마 (최종 확정)

모든 인덱싱 항목에 공통 적용:

```
{
  "business_type": str,
  "branch_code": str,
  "error_code": str,
  "manual_id": int | null,
  "consultation_id": int | null,
  "version": int,
  "created_at": timestamp
}
```

### 저장 규칙

`manual_vector_store.add()`
`consultation_vector_store.add()`

### 검색 규칙

* cosine similarity
* metadata filter
* top_k configurable

### 오류 처리 (Retry Queue 구조 확정)

* Redis / PostgreSQL 둘 중 하나 선택
* exponential backoff
* 실패 5회 이상 → Dead Letter Queue
* 모든 실패 로그 저장

---

# FR-12. MCP Ready 요구사항

### 필수 규칙

* Service Layer는 FastAPI 객체(Request/Response) 접근 금지
* 순수 데이터만 전달
* 모든 Service 함수는 Pydantic 모델을 반환해야 함
* MCP Tool에서 바로 호출 가능하도록 설계

---

# 4. LLM Prompt Template 아키텍처 (추가 개선 적용)

## 1) System Prompt (불변 규칙)

* 입력 텍스트 외 근거 사용 금지
* 환각 금지 규칙
* 출력 JSON Schema 강제
* 정책·규정 생성 금지

## 2) Instruction Prompt (기능별 명령)

예)

* “원문에서 키워드 1~3개 추출하라. 원문 단어만 사용한다.”
* “background/guideline은 원문 문장만 재구성하여 작성하라.”
* “원문에 없는 문장은 절대 생성하지 마라.”

## 3) Context Prompt

* 상담 원문
* 기존 메뉴얼(비교용)
* 비고자료

---

# 5. 비기능 요구사항(NFR)

### NFR-1. 성능

* 검색 API P95 ≤ 1초
* Vector 검색 ≤ 150ms
* Task 생성 평균 100ms 이하
* 배치 수백 건/분 처리 가능

### NFR-2. 확장성

* RDB ↔ VectorStore 물리적 분리
* 향후 PostgreSQL → Oracle 전환 가능
* VectorStore는 Milvus/Qdrant로 교체 가능

### NFR-3. 보안

* PII 암호화/마스킹
* RBAC(상담사/검토자/관리자)
* 모든 상태 변경 로깅

### NFR-4. 모니터링

* 검색 latency
* LLM 호출 이력
* VectorStore 실패율
* Task 처리량

---

# 6. API 요구사항 (최종 정리)

## 상담

* POST /consultations
* GET /consultations/{id}
* POST /consultations/search

## 메뉴얼

* POST /manuals/draft
* POST /manuals/approve/{id}
* GET /manuals/search

## 메뉴얼 검토

* GET /manual-review/tasks
* POST /manual-review/tasks/{id}/approve
* POST /manual-review/tasks/{id}/reject

---

# 7. 개발 산출물 기준 (Deliverables)

1. SQLAlchemy 2.0 모델 전체
2. VectorStore Protocol + Mock 구현
3. Repository Layer
4. Service Layer
5. LLM Prompt Template (System/Instruction/Context 분리)
6. 메뉴얼 생성/비교/검증 로직
7. ReviewTask Workflow
8. FastAPI Router 전체
9. Retry Queue + Dead Letter Queue 처리 모듈
10. 전체 ERD/시퀀스 다이어그램

---
