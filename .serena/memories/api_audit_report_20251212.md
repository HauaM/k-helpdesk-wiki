# API 감사 및 정리 보고서 (2025-12-12)

## 📋 실행 요약

**제거된 불필요한 API: 3개**
- ❌ POST /consultations/search (중복)
- ❌ POST /consultations/{id}/manual-draft (미구현, 통합됨)
- ❌ POST /manuals/draft/{id}/conflict-check (중복 기능)

**최종 API 수: 13개** (유지)

---

## 🗂️ 최종 API 구조

### consultations (3개 유지)

```
✅ POST   /consultations
   - 설명: 상담 등록
   - 요청: ConsultationCreate
   - 응답: ConsultationResponse
   - FR: FR-1
   - 용도: 고객 상담 기록 저장

✅ GET    /consultations/search
   - 설명: 상담 벡터 검색
   - 쿼리: query, top_k, branch_code, business_type, error_code, start_date, end_date
   - 응답: ConsultationSearchResponse (results, total_found)
   - FR: FR-3, FR-8
   - 용도: 유사 상담 검색 (시맨틱)

✅ GET    /consultations/{consultation_id}
   - 설명: 상담 상세 조회
   - 경로: consultation_id (string)
   - 응답: ConsultationResponse
   - 용도: 상담 정보 확인
```

### manuals (10개 유지)

#### Draft 관련 (1개)
```
✅ POST   /manuals/draft
   - 설명: 상담 기반 메뉴얼 초안 생성 + 비교 + 리뷰 태스크 생성
   - 요청: ManualDraftCreateFromConsultationRequest
     {
       "consultation_id": "uuid",
       "enforce_hallucination_check": boolean,
       "compare_with_manual_id": "uuid" (optional)
     }
   - 응답: ManualDraftCreateResponse
     {
       "comparison_type": "similar|supplement|new",
       "draft_entry": ManualEntryResponse,
       "existing_manual": ManualEntryResponse | null,
       "review_task_id": "uuid" | null,
       "similarity_score": float | null
     }
   - FR: FR-2, FR-6, FR-9, FR-11
   - 용도: 한 번에 Draft 생성 + 비교 + 리뷰 태스크 생성
   - 특징: 3-path 응답 (SIMILAR/SUPPLEMENT/NEW)
```

#### 버전 조회 (3개)
```
✅ GET    /manuals/versions
   - 설명: business_type + error_code로 메뉴얼 그룹의 버전 목록 조회
   - 쿼리: business_type, error_code, include_deprecated
   - 응답: list[ManualVersionResponse]
   - FR: FR-5, FR-11
   - 용도: UI에서 과거 버전 목록 표시 (Draft 생성 전)
   - 정렬: 최신순

✅ GET    /manuals/{manual_id}/versions
   - 설명: 특정 메뉴얼의 모든 버전 목록 조회
   - 경로: manual_id (UUID)
   - 응답: list[ManualVersionResponse]
   - 용도: 특정 메뉴얼의 버전 히스토리 확인

✅ GET    /manuals/{manual_id}/versions/{version}
   - 설명: 특정 버전의 메뉴얼 상세 조회
   - 경로: manual_id, version (string)
   - 응답: ManualVersionInfo
   - 용도: 과거 버전 메뉴얼 내용 확인
```

#### 승인/관리 (2개)
```
✅ POST   /manuals/{manual_id}/approve
   - 설명: Draft 승인 → APPROVED로 상태 변경
   - 요청: ManualApproveRequest
   - 응답: ManualVersionInfo
   - FR: FR-4, FR-5, FR-7
   - 용도: 리뷰 태스크 승인, 버전 관리

✅ PUT    /manuals/{manual_id}
   - 설명: Draft 상태 메뉴얼 수정
   - 요청: ManualEntryUpdate
   - 응답: ManualEntryResponse
   - FR: FR-4
   - 용도: Draft 수정 (topic, keywords, background, guideline)
   - 제약: DRAFT 상태만 수정 가능
```

#### 검색/조회 (4개)
```
✅ GET    /manuals
   - 설명: 메뉴얼 목록 조회
   - 쿼리: status_filter, limit
   - 응답: list[ManualEntryResponse]
   - 용도: 메뉴얼 전체 목록

✅ GET    /manuals/search
   - 설명: 메뉴얼 벡터 검색
   - 쿼리: query, top_k, status, business_type, error_code
   - 응답: list[ManualSearchResult]
   - FR: FR-8
   - 용도: 메뉴얼 유사도 검색

✅ GET    /manuals/{manual_id}
   - 설명: 메뉴얼 상세 조회
   - 경로: manual_id (UUID)
   - 응답: ManualEntryResponse
   - 용도: 메뉴얼 정보 확인

✅ DELETE /manuals/{manual_id}
   - 설명: 메뉴얼 삭제
   - 경로: manual_id (UUID)
   - 용도: 메뉴얼 제거
```

### 선택사항 (유지) - Diff 관련 기능

```
⚠️  GET    /manuals/{manual_id}/diff
   - 설명: 버전 간 Diff (같은 그룹의 메뉴얼 비교)
   - 쿼리: base_version, compare_version, summarize
   - 응답: ManualVersionDiffResponse
   - FR: FR-14
   - 상태: 유지 (UI 필요 여부에 따라)
   - 용도: 메뉴얼 버전 변화 분석

⚠️  GET    /manuals/drafts/{draft_id}/diff-with-active
   - 설명: Draft vs 운영 버전 미리보기
   - 쿼리: summarize
   - 응답: ManualVersionDiffResponse
   - FR: FR-14
   - 상태: 유지 (검토 워크플로우에 중요)
   - 용도: Draft 승인 전 변화 확인
```

---

## 🗑️ 제거된 API 분석

### 1️⃣ POST /consultations/search (검색 엔드포인트 중복)

**문제점:**
- GET /consultations/search와 동일 기능
- 하나는 Query parameter, 하나는 Request body만 다름
- REST API 규약상 GET은 조회, POST는 생성이므로 혼동

**해결:**
- GET /consultations/search만 유지
- query string으로 통일

---

### 2️⃣ POST /consultations/{id}/manual-draft (미구현, 통합됨)

**문제점:**
- TODO 상태 (실제 구현 안 됨)
- 기능이 POST /manuals/draft에 완전히 통합됨
- Consultation ID를 path parameter로 받으나, body에서도 받으므로 중복

**해결:**
- POST /manuals/draft 사용
```
# 기존 (제거)
POST /consultations/{id}/manual-draft

# 변경 (현재 방식)
POST /manuals/draft
{
  "consultation_id": "uuid"  // consultation ID를 body에서 받음
}
```

---

### 3️⃣ POST /manuals/draft/{id}/conflict-check (중복 기능)

**문제점:**
- POST /manuals/draft 응답에 이미 포함:
  - comparison_type (SIMILAR/SUPPLEMENT/NEW)
  - review_task_id (리뷰 태스크)
- Draft 생성 시 자동으로 비교 완료
- 별도 호출 불필요 (2단계 → 1단계로 단순화)

**해결:**
- POST /manuals/draft만 호출하면 끝남
```
# 기존 (2단계)
POST /manuals/draft                      # Draft 생성만
POST /manuals/draft/{id}/conflict-check  # 비교 후 리뷰 태스크

# 변경 (1단계)
POST /manuals/draft                      # 생성 + 비교 + 리뷰 태스크 모두 포함
```

---

## 📊 API 정리 요약

| 항목 | 변경 전 | 변경 후 | 비고 |
|-----|--------|--------|------|
| 총 API 수 | 16개 | 13개 | 3개 제거 |
| Consultations | 5개 | 3개 | 2개 제거 |
| Manuals | 11개 | 10개 | 1개 제거 |
| 선택사항 (Diff) | 2개 | 2개 | 유지 |

---

## 🎯 API 사용 흐름 (정상 워크플로우)

### 흐름 1: 상담 등록 → 초안 생성 → 승인

```
1. POST /consultations                          # 상담 등록
   요청: 상담 정보
   응답: { "id": "consultation_id" }

2. POST /manuals/draft                          # 초안 생성 + 비교 + 리뷰 태스크
   요청: { "consultation_id": "..." }
   응답: {
     "comparison_type": "new",
     "draft_entry": {...},
     "review_task_id": "task_123"
   }

3. PUT /manuals/{draft_id}                      # (선택) Draft 수정
   요청: { "guideline": "수정된 내용" }
   응답: { ... }

4. POST /manuals/{draft_id}/approve             # Draft 승인
   요청: { "reviewer_notes": "..." }
   응답: { "version": "v1.7", "status": "APPROVED" }
```

### 흐름 2: 상담 검색 → 유사 메뉴얼 확인

```
1. GET /consultations/search?query=로그인       # 유사 상담 검색
   응답: [
     { "id": "c1", "inquiry_text": "..." },
     { "id": "c2", "inquiry_text": "..." }
   ]

2. GET /manuals/search?query=로그인             # 유사 메뉴얼 검색
   응답: [
     { "id": "m1", "topic": "로그인 오류 처리", ... }
   ]
```

### 흐름 3: Draft 리뷰 전 미리보기

```
1. POST /manuals/draft                          # Draft 생성
   응답: { "draft_id": "d1", "review_task_id": "t1" }

2. GET /manuals/drafts/{draft_id}/diff-with-active  # (선택) 운영 버전과 비교
   응답: {
     "base_version": "v1.6",
     "compare_version": "DRAFT",
     "added_entries": [...],
     "modified_entries": [...],
     "removed_entries": [...]
   }

3. POST /manuals/{draft_id}/approve             # 승인
```

---

## 🔍 중요 특징

### 3-Path Draft 생성 응답

POST /manuals/draft는 3가지 경로를 반환:

```
1. SIMILAR (기존 메뉴얼과 유사, 재사용 가능)
   - comparison_type: "similar"
   - existing_manual: 기존 메뉴얼 반환
   - review_task_id: null (리뷰 불필요)
   - similarity_score: >= 0.95

2. SUPPLEMENT (기존 메뉴얼 보충/개선)
   - comparison_type: "supplement"
   - existing_manual: 기존 메뉴얼 반환
   - review_task_id: 생성됨 (검토 필요)
   - similarity_score: 0.7~0.95

3. NEW (신규 메뉴얼)
   - comparison_type: "new"
   - existing_manual: null
   - review_task_id: 생성됨 (검토 필요)
   - similarity_score: null
```

### 메타데이터 필터링

모든 벡터 검색 (consultations, manuals):
- business_type, error_code로 그룹 내에서만 검색
- Cross-group 오염 방지

---

## 📝 변경 이력

| 날짜 | 변경 | 파일 |
|-----|------|------|
| 2025-12-12 | POST /consultations/search 제거 | app/routers/consultations.py |
| 2025-12-12 | POST /consultations/{id}/manual-draft 제거 | app/routers/consultations.py |
| 2025-12-12 | POST /manuals/draft/{id}/conflict-check 제거 | app/routers/manuals.py |

---

**작성:** 2025-12-12
**상태:** 최종 정리 완료
**다음 단계:** UI 개발 시 이 문서 참고
