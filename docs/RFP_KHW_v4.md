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

* ManualEntry 상태: DRAFT / APPROVED / DEPRECATED
* APPROVED만 VectorStore 인덱싱
* DRAFT는 검색 제외

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

# 🆕 FR-14. 메뉴얼 버전별 비교 기능 (Version Diff)

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

# 4. 개발 산출물 요구사항

1. SQLAlchemy 2.0 모델
2. Repository Layer
3. Service Layer
4. VectorStore Protocol + Mock
5. LLM Prompt Template 구조화
6. 메뉴얼 생성/비교 로직
7. ReviewTask 워크플로우
8. Version Diff 기능(FR-14)
9. FastAPI Router 전체
10. Retry Queue 처리
11. ERD/시퀀스 다이어그램

---

# 📌 문서 버전 정보

* 문서 버전: **v4.0**
* 포함된 기능 범위: FR-1 ~ FR-14
* 적용 프레임워크: FastAPI, SQLAlchemy 2.0, PostgreSQL, VectorStore(Milvus/pgvector), MCP Ready

---
