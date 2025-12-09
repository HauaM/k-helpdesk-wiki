# 메뉴얼 버전 비교 기능 - 백엔드 API 구현 가이드

## 개요

메뉴얼 버전 비교 기능을 위해 다음 두 개의 API 엔드포인트가 필요합니다.

---

## 1. 메뉴얼 버전 목록 조회

### 엔드포인트
```
GET /api/v1/manuals/{manual_id}/versions
```

### 설명
메뉴얼의 모든 버전을 최신순으로 반환합니다.

### 요청 파라미터

| 파라미터 | 위치 | 타입 | 설명 |
|---------|------|------|------|
| manual_id | path | UUID | 메뉴얼 ID |

### 응답 상태 코드

- **200**: 성공
- **404**: 메뉴얼을 찾을 수 없음
- **500**: 서버 오류

### 응답 본문

```json
[
  {
    "value": "v2.1",
    "label": "v2.1 (현재 버전)",
    "date": "2024-01-15"
  },
  {
    "value": "v2.0",
    "label": "v2.0",
    "date": "2024-01-01"
  },
  {
    "value": "v1.8",
    "label": "v1.8",
    "date": "2023-12-10"
  }
]
```

### 응답 필드 설명

| 필드 | 타입 | 설명 |
|------|------|------|
| value | string | 버전 번호 (예: "v2.1") |
| label | string | 사용자 표시용 레이블 (버전 + 현재 버전 여부) |
| date | string | 버전 승인/생성 날짜 (YYYY-MM-DD 형식) |

### 구현 주의사항

1. **버전 정렬**: 최신 버전을 먼저 반환 (내림차순)
2. **현재 버전 표시**: 가장 최신 버전의 label에 "(현재 버전)" 추가
3. **날짜 형식**: ISO 8601 datetime을 YYYY-MM-DD로 변환
4. **APPROVED 상태**: APPROVED 상태인 버전만 포함

---

## 2. 메뉴얼 특정 버전 상세 조회

### 엔드포인트

**권장 방식:**
```
GET /api/v1/manuals/{manual_id}/versions/{version}
```

### 설명

특정 버전의 메뉴얼 상세 정보를 반환합니다.

### 요청 파라미터

| 파라미터 | 위치 | 타입 | 설명 |
|---------|------|------|------|
| manual_id | path | UUID | 메뉴얼 ID |
| version | path | string | 버전 번호 (예: "v2.1") |

### 응답 상태 코드

- **200**: 성공
- **404**: 메뉴얼 또는 버전을 찾을 수 없음
- **500**: 서버 오류

### 응답 본문

```json
{
  "manual_id": "550e8400-e29b-41d4-a716-446655440000",
  "version": "v2.1",
  "topic": "인터넷뱅킹 로그인 오류 처리 가이드",
  "keywords": ["인터넷뱅킹", "로그인오류", "E001"],
  "background": "고객이 인터넷뱅킹 로그인 시 오류가 발생하는 경우는 다양한 원인이 있을 수 있습니다...",
  "guidelines": [
    {
      "title": "계정 상태 확인",
      "description": "고객의 아이디를 확인하여 계정 잠김 여부를 확인합니다..."
    },
    {
      "title": "브라우저 및 보안프로그램 점검",
      "description": "고객이 사용 중인 브라우저 버전을 확인하고..."
    }
  ],
  "status": "APPROVED",
  "updated_at": "2024-01-15T14:30:00Z"
}
```

### 응답 필드 설명

| 필드 | 타입 | 설명 |
|------|------|------|
| manual_id | string (UUID) | 메뉴얼 ID |
| version | string | 버전 번호 |
| topic | string | 메뉴얼 주제 |
| keywords | string[] | 키워드 배열 |
| background | string | 배경 정보 |
| guidelines | object[] | 조치사항/가이드라인 배열 |
| guidelines[].title | string | 조치사항 제목 |
| guidelines[].description | string | 조치사항 설명 |
| status | string | 메뉴얼 상태 (APPROVED, DEPRECATED) |
| updated_at | string | 업데이트 시간 (ISO 8601) |

### 구현 주의사항

1. **Guideline 형식**: OpenAPI의 `guideline` 필드(문자열)를 파싱하여 배열로 변환
   - OpenAPI: `"guideline": "제목1\n설명1\n제목2\n설명2"`
   - API 응답: `"guidelines": [{"title": "제목1", "description": "설명1"}, ...]`

2. **Status 값**: 메뉴얼의 status 필드 그대로 반환 (APPROVED 또는 DEPRECATED)

3. **DateTime 형식**: ISO 8601 datetime을 그대로 반환

---

## 대안 구현 방식

### 옵션 2: Diff API 활용

현재 OpenAPI에 존재하는 Diff API를 활용할 수 있습니다:

```
GET /api/v1/manuals/{manual_group_id}/diff?base_version=v2.0&compare_version=v2.1
```

응답: `ManualVersionDiffResponse`

**장점**: 버전 간 차이를 효율적으로 계산
**단점**: 프론트엔드에서 diff 결과를 파싱하여 비교 UI를 구성해야 함

### 옵션 3: 쿼리 파라미터 활용 (임시 방안)

```
GET /api/v1/manuals/{manual_id}?version=v2.0
```

응답: 기존 `ManualEntryResponse` (guideline은 문자열)

**장점**: 기존 엔드포인트 재활용
**단점**: 문자열을 파싱해야 하고, 선택적 파라미터 처리 필요

---

## 구현 체크리스트

### API 1: GET /api/v1/manuals/{manual_id}/versions

- [ ] 엔드포인트 구현
- [ ] manual_id 파라미터 검증 (UUID 형식)
- [ ] 메뉴얼 존재 여부 확인
- [ ] APPROVED 상태인 버전만 필터링
- [ ] 버전을 최신순으로 정렬
- [ ] 현재 버전 표시 ("(현재 버전)" 라벨 추가)
- [ ] 날짜 형식 변환 (ISO 8601 → YYYY-MM-DD)
- [ ] 404/500 에러 처리

### API 2: GET /api/v1/manuals/{manual_id}/versions/{version}

- [ ] 엔드포인트 구현
- [ ] manual_id, version 파라미터 검증
- [ ] 메뉴얼 및 버전 존재 여부 확인
- [ ] Guideline 필드 파싱 (문자열 → 배열 변환)
- [ ] 정확한 필드명 사용 (guidelines 배열)
- [ ] ISO 8601 datetime 반환
- [ ] 404/500 에러 처리

---

## 테스트 예시

### 성공 케이스

```bash
# 버전 목록 조회
curl -X GET "http://localhost:8000/api/v1/manuals/550e8400-e29b-41d4-a716-446655440000/versions"

# 특정 버전 조회
curl -X GET "http://localhost:8000/api/v1/manuals/550e8400-e29b-41d4-a716-446655440000/versions/v2.1"
```

### 에러 케이스

```bash
# 존재하지 않는 메뉴얼
curl -X GET "http://localhost:8000/api/v1/manuals/00000000-0000-0000-0000-000000000000/versions"
# 응답: 404 Not Found

# 존재하지 않는 버전
curl -X GET "http://localhost:8000/api/v1/manuals/550e8400-e29b-41d4-a716-446655440000/versions/v99.9"
# 응답: 404 Not Found
```

---

## 프론트엔드 연동 흐름

1. **페이지 로드**
   - `GET /api/v1/manuals/{manualId}/versions` 호출
   - 버전 목록 표시 (드롭다운)

2. **버전 선택**
   - 사용자가 이전/최신 버전 선택
   - `GET /api/v1/manuals/{manualId}/versions/{oldVersion}` 호출 (병렬)
   - `GET /api/v1/manuals/{manualId}/versions/{newVersion}` 호출 (병렬)

3. **비교 표시**
   - 프론트엔드에서 두 버전 데이터 비교
   - 추가/삭제/수정 항목 시각적 표시

---

## FAQ

**Q: guideline 필드는 왜 배열로 변환해야 하나요?**
A: 프론트엔드에서 각 조치사항을 독립적으로 표시하고 변경사항을 추적하기 위함입니다.

**Q: 버전은 어떤 형식으로 저장되나요?**
A: "v2.1", "v2.0" 등의 문자열 형식입니다. 메뉴얼 그룹이 승인될 때마다 새로운 버전이 생성됩니다.

**Q: 완전히 새로운 엔드포인트를 추가하고 싶지 않은데요?**
A: 옵션 2(Diff API) 또는 옵션 3(쿼리 파라미터)을 참고하세요.

---

## 관련 파일

- 프론트엔드 타입 정의: `src/types/manuals.ts`
- API 레이어: `src/lib/api/manuals.ts`
- 훅: `src/hooks/useManualVersionCompare.ts`
- 컴포넌트: `src/components/manuals/ManualVersionCompareView.tsx`
- 페이지: `src/pages/manuals/ManualVersionComparePage.tsx`
