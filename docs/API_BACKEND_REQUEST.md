# 메뉴얼 버전 생성 API 구현 요청서

## 개요
메뉴얼 상세 조회 화면에서 **APPROVED/DEPRECATED 상태의 메뉴얼도 "수정하기" 기능을 제공**하기 위해 새로운 API 엔드포인트가 필요합니다.

사용자가 APPROVED/DEPRECATED 메뉴얼을 수정하려고 하면, 해당 메뉴얼을 기반으로 **새로운 DRAFT 버전을 생성**한 후, 그 DRAFT 버전에서 편집 가능하도록 해야 합니다.

---

## 요청 API 스펙

### 엔드포인트
```
POST /api/v1/manuals/{manual_id}/create-version
```

### 요약
"메뉴얼 버전 생성"

### 설명
기존 메뉴얼(APPROVED/DEPRECATED)을 기반으로 새로운 DRAFT 버전을 생성합니다.
- 현재 메뉴얼의 모든 콘텐츠(topic, keywords, background, guideline)를 복사
- 상태는 DRAFT로 설정
- 새로운 ID와 버전 번호로 생성 (기존 메뉴얼과는 별개)
- 추적 정보: created_at, updated_at, source_consultation_id 등 설정

---

## 요청 사양

### 경로 파라미터
```
manual_id: string (UUID)
  - 기반이 될 기존 메뉴얼의 ID
```

### 요청 바디
```json
{
  "reason": "string (optional, default: null)",
  "description": "수정 이유 또는 메모"
}
```

**또는 (더 간단한 버전):**

요청 바디 없이 진행 가능:
```json
{}
```

### HTTP 상태 코드

#### 201 Created
```json
{
  "id": "uuid",
  "created_at": "2024-01-15T10:30:00Z",
  "updated_at": "2024-01-15T10:30:00Z",
  "topic": "string",
  "keywords": ["string"],
  "background": "string",
  "guideline": "string (줄바꿈으로 구분된 문자열)",
  "status": "DRAFT",
  "source_consultation_id": "uuid (원본 source_consultation_id 유지)",
  "version_id": "uuid (optional, null 가능)",
  "business_type": "string (optional, null)",
  "error_code": "string (optional, null)"
}
```
응답은 `ManualEntryResponse`와 동일한 구조

#### 400 Bad Request
```json
{
  "detail": "Invalid manual_id format"
}
```

#### 404 Not Found
```json
{
  "detail": "Manual not found"
}
```

#### 422 Unprocessable Entity
```json
{
  "detail": [
    {
      "loc": ["body", "reason"],
      "msg": "Field validation error",
      "type": "value_error"
    }
  ]
}
```

---

## 구현 요구사항

### 비즈니스 로직
1. ✅ 기존 메뉴얼이 존재하는지 확인 (404 처리)
2. ✅ 기존 메뉴얼의 모든 필드 복사
3. ✅ 새로운 UUID 생성 (새로운 메뉴얼 ID)
4. ✅ 상태를 DRAFT로 설정
5. ✅ 타임스탬프 업데이트 (created_at, updated_at를 현재 시각으로)
6. ✅ `source_consultation_id`는 기존 값 유지 (또는 원본 메뉴얼의 ID를 참조)
7. ✅ 버전 관리: 새로운 버전 번호 할당 (자동 증가 로직)

### 권한 검증 (optional)
- 기존 메뉴얼을 생성한 사용자 또는 관리자만 버전 생성 가능
- 또는 모든 인증된 사용자 가능

### 참고사항
- 기존 메뉴얼의 상태(APPROVED/DEPRECATED)와 관계없이 버전 생성 가능
- DRAFT인 메뉴얼도 버전 생성 가능 (모임 초안의 수정 이력 추적)

---

## 프론트엔드 구현 계획

### 변경 흐름

#### 현재 흐름 (DRAFT만 편집 가능)
```
메뉴얼 상세 조회 → "수정하기" 클릭 → /manuals/{manualId}/edit (DRAFT만 가능)
```

#### 새로운 흐름 (모든 상태에서 편집 가능)
```
메뉴얼 상세 조회 (APPROVED/DEPRECATED)
  → "수정하기" 클릭
  → POST /api/v1/manuals/{manualId}/create-version 호출 (새 DRAFT 버전 생성)
  → /manuals/{newManualId}/edit 로 리다이렉트 (새 DRAFT 버전 편집)
```

### 프론트엔드 코드 변경
1. `ManualDetailView.tsx` - handleEdit() 함수 수정
   - 상태가 DRAFT가 아니면 API 호출해서 새 버전 생성
   - 생성된 새 메뉴얼 ID로 편집 페이지 라우팅

2. `src/lib/api/manuals.ts` - 새 함수 추가
   ```typescript
   export const createManualVersion = (manualId: string) =>
     api.post<ManualDetail>(`/api/v1/manuals/${manualId}/create-version`, {});
   ```

3. `ManualEditPage.tsx` - DRAFT 상태 체크 제거
   - DRAFT 상태만 편집 가능한 제약 조건 제거

---

## 예상 사용 시나리오

### 시나리오 1: APPROVED 메뉴얼 수정
```
1. 사용자가 APPROVED 메뉴얼 상세 페이지에서 "수정하기" 클릭
2. 프론트엔드: POST /api/v1/manuals/abc-123/create-version
3. 백엔드: 새로운 DRAFT 메뉴얼 생성 (ID: def-456)
4. 프론트엔드: 자동으로 /manuals/def-456/edit 페이지로 이동
5. 사용자: DRAFT 메뉴얼 수정 후 저장
```

### 시나리오 2: DEPRECATED 메뉴얼 수정
```
1. 사용자가 DEPRECATED 메뉴얼 상세 페이지에서 "수정하기" 클릭
2. (위와 동일한 흐름)
```

---

## 관련 기존 API

### 참고 - 유사한 API 구조
- `POST /api/v1/manuals/draft` - 상담 기반 초안 생성 (ManualDraftResponse 반환)
- `PUT /api/v1/manuals/{manual_id}` - DRAFT 메뉴얼 수정

새로운 API는 `PUT /api/v1/manuals/{manual_id}`의 응답 구조와 동일하게 `ManualEntryResponse` (또는 `ManualDetail`)를 반환하면 됩니다.

---

## OpenAPI 스펙 추가 형식

```yaml
/api/v1/manuals/{manual_id}/create-version:
  post:
    tags:
      - manuals
    summary: Create new manual version
    description: >
      APPROVED/DEPRECATED 메뉴얼을 기반으로 새로운 DRAFT 버전을 생성합니다.

      기존 메뉴얼의 모든 콘텐츠를 복사하여 새로운 DRAFT 상태의 메뉴얼을 생성합니다.
      이를 통해 사용자는 APPROVED/DEPRECATED 메뉴얼도 편집할 수 있습니다.
    operationId: create_manual_version_api_v1_manuals__manual_id__create_version_post
    parameters:
      - name: manual_id
        in: path
        required: true
        schema:
          type: string
          format: uuid
          title: Manual Id
    requestBody:
      required: false
      content:
        application/json:
          schema:
            type: object
            properties:
              reason:
                type: string
                title: Reason
                description: Optional reason for creating new version
    responses:
      '201':
        description: Manual version created successfully
        content:
          application/json:
            schema:
              $ref: '#/components/schemas/ManualEntryResponse'
      '400':
        description: Invalid request
      '404':
        description: Manual not found
      '422':
        description: Validation Error
```

---

## 질문 및 확인 사항

1. **버전 번호 관리**
   - 기존 버전 시스템(v1, v2 등)과 어떻게 통합할지?
   - 새 버전 번호는 자동 증가하는지?

2. **source_consultation_id**
   - 새 버전도 원본 메뉴얼의 `source_consultation_id` 유지해야 하는지?
   - 아니면 원본 메뉴얼의 ID를 참조해야 하는지?

3. **권한 검증**
   - 누가 버전을 생성할 수 있는지? (관리자만? 모든 인증 사용자?)

4. **추가 메타데이터**
   - version_id, business_type, error_code 등을 새 버전에서도 유지해야 하는지?

---

## 타임라인
- **우선순위**: High (메뉴얼 편집 기능 완성을 위해 필수)
- **예상 영향 범위**: 메뉴얼 관리 모듈만
- **테스트 필요**: APPROVED → 수정 시나리오, DEPRECATED → 수정 시나리오

