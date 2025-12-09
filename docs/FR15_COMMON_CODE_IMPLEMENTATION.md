# 📋 FR-15: 공통코드 관리 기능 구현 가이드

**문서 버전**: 1.0
**작성일**: 2025-12-08
**상태**: ✅ 구현 완료

---

## 📌 개요

FR-15 공통코드 관리 기능은 **업무 구분(business_type), 에러코드(error_code), 지점 코드(branch_code)** 등의 공통 코드들을 중앙에서 관리하고, 프론트엔드에서 API를 통해 사용할 수 있도록 제공하는 기능입니다.

### 주요 특징

- ✅ 공통코드 그룹(Group) 관리
- ✅ 공통코드 항목(Item) 관리
- ✅ 관리자용 CRUD API
- ✅ 프론트엔드용 조회 API
- ✅ 공통코드 일괄 조회(Bulk) API
- ✅ MCP 서버 통합
- ✅ 데이터베이스 마이그레이션

---

## 🏗️ 아키텍처

### 계층 구조

```
FastAPI Router (app/routers/common_codes.py)
    ↓
Service Layer (app/services/common_code_service.py)
    ↓
Repository Layer (app/repositories/common_code_rdb.py)
    ↓
SQLAlchemy Models (app/models/common_code.py)
    ↓
PostgreSQL Database
```

### 컴포넌트 분석

| 컴포넌트 | 파일 | 역할 |
|---------|------|------|
| **Model** | `app/models/common_code.py` | SQLAlchemy 도메인 모델 (CommonCodeGroup, CommonCodeItem) |
| **Repository** | `app/repositories/common_code_rdb.py` | CRUD 및 조회 로직 |
| **Service** | `app/services/common_code_service.py` | 비즈니스 로직 (FastAPI 독립적) |
| **Schema** | `app/schemas/common_code.py` | Pydantic 요청/응답 DTO |
| **Router** | `app/routers/common_codes.py` | FastAPI 엔드포인트 |
| **MCP Tools** | `app/mcp/tools.py` | MCP 서버 통합 도구 |
| **Migration** | `alembic/versions/20251208_*.py` | 데이터베이스 마이그레이션 |
| **Tests** | `tests/unit/test_common_code_service.py` | 단위 테스트 |

---

## 📂 구현 파일 목록

### 1. SQLAlchemy 모델

**파일**: `app/models/common_code.py`

```python
# CommonCodeGroup: 공통코드 그룹
- group_code: str (Unique) - 그룹 고유 코드
- group_name: str - 그룹 이름
- description: str (Optional) - 그룹 설명
- is_active: bool - 활성화 여부
- items: list[CommonCodeItem] - 하위 항목 (Relationship)

# CommonCodeItem: 공통코드 항목
- group_id: UUID (FK) - 상위 그룹 ID
- code_key: str - 코드 키
- code_value: str - 코드 값/표시명
- sort_order: int - 정렬 순서
- is_active: bool - 활성화 여부
- attributes: dict (JSONB) - 추가 메타데이터
- group: CommonCodeGroup - 상위 그룹 (Relationship)

제약조건:
- CommonCodeGroup.group_code: Unique
- CommonCodeItem: (group_id, code_key) Unique
```

### 2. Repository 계층

**파일**: `app/repositories/common_code_rdb.py`

#### CommonCodeGroupRepository

```python
async def create(group: CommonCodeGroup) -> CommonCodeGroup
async def get_by_id(id: UUID) -> CommonCodeGroup | None
async def get_by_group_code(group_code: str) -> CommonCodeGroup | None
async def get_by_group_code_with_items(group_code: str) -> CommonCodeGroup | None
async def get_active_groups(limit, offset) -> Sequence[CommonCodeGroup]
async def search_groups(keyword, is_active, limit, offset) -> Sequence[CommonCodeGroup]
async def count_active_groups() -> int
async def update(group: CommonCodeGroup) -> CommonCodeGroup
async def delete(group: CommonCodeGroup) -> None
```

#### CommonCodeItemRepository

```python
async def create(item: CommonCodeItem) -> CommonCodeItem
async def get_by_id(id: UUID) -> CommonCodeItem | None
async def get_by_id_or_raise(id: UUID) -> CommonCodeItem  # RecordNotFoundError if not found
async def get_by_group_id(group_id, is_active_only, order_by_sort) -> Sequence[CommonCodeItem]
async def get_by_group_code(group_code, is_active_only) -> Sequence[CommonCodeItem]
async def get_by_code_key(group_id, code_key) -> CommonCodeItem | None
async def check_duplicate_code_key(group_id, code_key, exclude_id) -> bool
async def count_by_group_id(group_id) -> int
async def delete_by_group_id(group_id) -> int
async def update_sort_order(id, sort_order) -> CommonCodeItem
async def update(item: CommonCodeItem) -> CommonCodeItem
async def delete(item: CommonCodeItem) -> None
```

### 3. Service 계층

**파일**: `app/services/common_code_service.py`

**특징**:
- FastAPI 독립적 (순수 Python 타입만 사용)
- MCP 서버에서 직접 호출 가능
- Pydantic 스키마로 입출력
- 구조화된 로깅

#### 주요 메서드

**Group Management:**
```python
async def create_group(payload: CommonCodeGroupCreate) -> CommonCodeGroupResponse
async def get_group(group_id: UUID) -> CommonCodeGroupResponse
async def get_group_by_code(group_code: str) -> CommonCodeGroupResponse
async def get_group_with_items(group_code: str) -> CommonCodeGroupDetailResponse
async def list_groups(page, page_size, is_active) -> CommonCodeGroupListResponse
async def search_groups(keyword, page, page_size) -> CommonCodeGroupListResponse
async def update_group(group_id, payload) -> CommonCodeGroupResponse
async def delete_group(group_id) -> None
```

**Item Management:**
```python
async def create_item(group_id, payload) -> CommonCodeItemResponse
async def get_item(item_id) -> CommonCodeItemResponse
async def list_items_by_group(group_id, page, page_size, is_active_only) -> CommonCodeItemListResponse
async def update_item(item_id, payload) -> CommonCodeItemResponse
async def delete_item(item_id) -> None
```

**Public Search (Frontend):**
```python
async def get_codes_by_group_code(group_code, is_active_only) -> CommonCodeGroupSimpleResponse
async def get_multiple_code_groups(group_codes, is_active_only) -> BulkCommonCodeResponse
```

---

## 🔌 API 엔드포인트

### 관리자용 API (`/admin/common-codes/`)

#### 그룹 관리

```bash
# 그룹 생성
POST /api/v1/admin/common-codes/groups
{
  "group_code": "BUSINESS_TYPE",
  "group_name": "업무 구분",
  "description": "비즈니스 타입 코드",
  "is_active": true
}

# 그룹 목록 조회
GET /api/v1/admin/common-codes/groups?page=1&page_size=20&is_active=true

# 그룹 검색
GET /api/v1/admin/common-codes/groups/search?keyword=BUSINESS&page=1

# 그룹 조회 (ID)
GET /api/v1/admin/common-codes/groups/{group_id}

# 그룹 수정
PUT /api/v1/admin/common-codes/groups/{group_id}
{
  "group_name": "새로운 이름",
  "description": "새로운 설명"
}

# 그룹 삭제
DELETE /api/v1/admin/common-codes/groups/{group_id}
```

#### 항목 관리

```bash
# 항목 생성
POST /api/v1/admin/common-codes/groups/{group_id}/items
{
  "code_key": "RETAIL",
  "code_value": "리테일",
  "sort_order": 1,
  "is_active": true,
  "attributes": {}
}

# 항목 목록 조회
GET /api/v1/admin/common-codes/groups/{group_id}/items?page=1&page_size=100

# 항목 조회 (ID)
GET /api/v1/admin/common-codes/items/{item_id}

# 항목 수정
PUT /api/v1/admin/common-codes/items/{item_id}
{
  "code_value": "새로운 값",
  "sort_order": 2
}

# 항목 삭제
DELETE /api/v1/admin/common-codes/items/{item_id}
```

### 프론트엔드용 API (`/common-codes/`)

```bash
# 단일 그룹 조회
GET /api/v1/common-codes/BUSINESS_TYPE
응답:
{
  "group_code": "BUSINESS_TYPE",
  "items": [
    {"code_key": "RETAIL", "code_value": "리테일"},
    {"code_key": "LOAN", "code_value": "대출"}
  ]
}

# 다중 그룹 조회 (Bulk)
POST /api/v1/common-codes/bulk
["BUSINESS_TYPE", "ERROR_CODE"]

응답:
{
  "data": {
    "BUSINESS_TYPE": {
      "group_code": "BUSINESS_TYPE",
      "items": [...]
    },
    "ERROR_CODE": {
      "group_code": "ERROR_CODE",
      "items": [...]
    }
  }
}
```

---

## 🔌 MCP 서버 통합

### 사용 가능한 MCP 도구

#### 1. get_common_codes_tool

```python
async def get_common_codes_tool(group_code: str) -> str

# 사용 예시
result = await get_common_codes_tool(group_code="BUSINESS_TYPE")
# 응답: {"status": "success", "group_code": "BUSINESS_TYPE", "items": [...]}
```

#### 2. get_multiple_common_codes_tool

```python
async def get_multiple_common_codes_tool(group_codes: list[str]) -> str

# 사용 예시
result = await get_multiple_common_codes_tool(
    group_codes=["BUSINESS_TYPE", "ERROR_CODE"]
)
# 응답: {"status": "success", "data": {...}}
```

#### 3. create_common_code_group_tool

```python
async def create_common_code_group_tool(
    group_code: str,
    group_name: str,
    description: str | None = None
) -> str

# 사용 예시
result = await create_common_code_group_tool(
    group_code="NEW_GROUP",
    group_name="새로운 그룹",
    description="설명"
)
```

#### 4. create_common_code_item_tool

```python
async def create_common_code_item_tool(
    group_code: str,
    code_key: str,
    code_value: str,
    sort_order: int = 0
) -> str

# 사용 예시
result = await create_common_code_item_tool(
    group_code="BUSINESS_TYPE",
    code_key="RETAIL",
    code_value="리테일",
    sort_order=1
)
```

---

## 📊 데이터베이스 스키마

### CommonCodeGroup 테이블

```sql
CREATE TABLE common_code_groups (
  id UUID PRIMARY KEY,
  group_code VARCHAR(100) UNIQUE NOT NULL,
  group_name VARCHAR(200) NOT NULL,
  description TEXT,
  is_active BOOLEAN NOT NULL DEFAULT true,
  created_at TIMESTAMP WITH TIME ZONE NOT NULL,
  updated_at TIMESTAMP WITH TIME ZONE NOT NULL,

  INDEX idx_group_code (group_code),
  INDEX idx_is_active (is_active)
);
```

### CommonCodeItem 테이블

```sql
CREATE TABLE common_code_items (
  id UUID PRIMARY KEY,
  group_id UUID NOT NULL REFERENCES common_code_groups(id) ON DELETE CASCADE,
  code_key VARCHAR(100) NOT NULL,
  code_value VARCHAR(200) NOT NULL,
  sort_order INTEGER NOT NULL DEFAULT 0,
  is_active BOOLEAN NOT NULL DEFAULT true,
  attributes JSONB NOT NULL DEFAULT '{}',
  created_at TIMESTAMP WITH TIME ZONE NOT NULL,
  updated_at TIMESTAMP WITH TIME ZONE NOT NULL,

  UNIQUE (group_id, code_key),
  INDEX idx_group_id (group_id),
  INDEX idx_is_active (is_active)
);
```

---

## 🧪 테스트

### 테스트 파일

**파일**: `tests/unit/test_common_code_service.py`

### 테스트 커버리지

- ✅ 그룹 생성/조회/수정/삭제
- ✅ 그룹 코드로 조회
- ✅ 그룹 목록 조회 (페이징)
- ✅ 그룹 검색
- ✅ 중복 검사
- ✅ 항목 생성/조회/수정/삭제
- ✅ 항목 목록 조회 (그룹별)
- ✅ 속성(attributes) 관리
- ✅ 프론트엔드 API (단일/다중 조회)

### 테스트 실행

```bash
# 모든 테스트 실행
uv run pytest tests/unit/test_common_code_service.py -v

# 특정 테스트 실행
uv run pytest tests/unit/test_common_code_service.py::test_create_group -v

# 커버리지 리포트
uv run pytest tests/unit/test_common_code_service.py --cov=app.services.common_code_service
```

---

## 🔧 마이그레이션

### 마이그레이션 파일

**파일**: `alembic/versions/20251208_2257_b9e54cc56a05_fr_15_add_common_code_management.py`

### 마이그레이션 실행

```bash
# 최신 마이그레이션 적용
uv run alembic upgrade head

# 특정 마이그레이션까지 적용
uv run alembic upgrade 20251208_2257

# 이전 마이그레이션으로 롤백
uv run alembic downgrade -1
```

---

## 🚀 사용 예시

### 1. 관리자가 공통코드 그룹 생성

```python
# API 호출
POST /api/v1/admin/common-codes/groups
{
  "group_code": "BUSINESS_TYPE",
  "group_name": "업무 구분",
  "description": "고객 상담 업무의 분류"
}

# 응답 (201 Created)
{
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "group_code": "BUSINESS_TYPE",
  "group_name": "업무 구분",
  "description": "고객 상담 업무의 분류",
  "is_active": true,
  "created_at": "2025-12-08T10:00:00Z",
  "updated_at": "2025-12-08T10:00:00Z"
}
```

### 2. 관리자가 항목 추가

```python
# API 호출
POST /api/v1/admin/common-codes/groups/550e8400-e29b-41d4-a716-446655440000/items
{
  "code_key": "RETAIL",
  "code_value": "리테일",
  "sort_order": 1
}

# 응답 (201 Created)
{
  "id": "550e8400-e29b-41d4-a716-446655440001",
  "group_id": "550e8400-e29b-41d4-a716-446655440000",
  "code_key": "RETAIL",
  "code_value": "리테일",
  "sort_order": 1,
  "is_active": true,
  "attributes": {},
  "created_at": "2025-12-08T10:05:00Z",
  "updated_at": "2025-12-08T10:05:00Z"
}
```

### 3. 프론트엔드가 공통코드 조회

```python
# API 호출
GET /api/v1/common-codes/BUSINESS_TYPE

# 응답
{
  "group_code": "BUSINESS_TYPE",
  "items": [
    {"code_key": "RETAIL", "code_value": "리테일"},
    {"code_key": "LOAN", "code_value": "대출"},
    {"code_key": "INSURANCE", "code_value": "보험"}
  ]
}
```

### 4. 프론트엔드가 다중 공통코드 조회

```python
# API 호출
POST /api/v1/common-codes/bulk
["BUSINESS_TYPE", "ERROR_CODE"]

# 응답
{
  "data": {
    "BUSINESS_TYPE": {
      "group_code": "BUSINESS_TYPE",
      "items": [
        {"code_key": "RETAIL", "code_value": "리테일"},
        {"code_key": "LOAN", "code_value": "대출"}
      ]
    },
    "ERROR_CODE": {
      "group_code": "ERROR_CODE",
      "items": [
        {"code_key": "ERROR_001", "code_value": "시스템 오류"},
        {"code_key": "ERROR_002", "code_value": "데이터베이스 오류"}
      ]
    }
  }
}
```

### 5. MCP를 통한 조회

```python
# Claude가 MCP 도구 사용
result = await mcp_get_common_codes_tool(group_code="BUSINESS_TYPE")

# 응답
{
  "status": "success",
  "group_code": "BUSINESS_TYPE",
  "items": [...]
}
```

---

## 📋 Pydantic 스키마

### 요청 스키마

```python
# 그룹 생성
class CommonCodeGroupCreate:
    group_code: str          # 필수
    group_name: str          # 필수
    description: str | None  # 선택
    is_active: bool          # 기본값: True

# 그룹 수정
class CommonCodeGroupUpdate:
    group_code: str | None
    group_name: str | None
    description: str | None
    is_active: bool | None

# 항목 생성
class CommonCodeItemCreate:
    code_key: str            # 필수
    code_value: str          # 필수
    sort_order: int          # 기본값: 0
    is_active: bool          # 기본값: True
    attributes: dict | None  # 선택

# 항목 수정
class CommonCodeItemUpdate:
    code_key: str | None
    code_value: str | None
    sort_order: int | None
    is_active: bool | None
    attributes: dict | None
```

### 응답 스키마

```python
# 그룹 응답
class CommonCodeGroupResponse:
    id: UUID
    group_code: str
    group_name: str
    description: str | None
    is_active: bool
    created_at: datetime
    updated_at: datetime

# 항목 응답
class CommonCodeItemResponse:
    id: UUID
    group_id: UUID
    code_key: str
    code_value: str
    sort_order: int
    is_active: bool
    attributes: dict
    created_at: datetime
    updated_at: datetime

# 프론트엔드 축약 응답
class CommonCodeSimpleResponse:
    code_key: str
    code_value: str

class CommonCodeGroupSimpleResponse:
    group_code: str
    items: list[CommonCodeSimpleResponse]
```

---

## ⚠️ 에러 처리

### HTTP 상태 코드

| 코드 | 상황 | 예시 |
|------|------|------|
| 200 | 성공 | GET, PUT 성공 |
| 201 | 생성됨 | POST 성공 |
| 204 | 콘텐츠 없음 | DELETE 성공 |
| 400 | 잘못된 요청 | 중복 코드, 검증 실패 |
| 404 | 찾을 수 없음 | 그룹/항목 미존재 |
| 422 | 검증 실패 | 필드 검증 오류 |
| 500 | 서버 오류 | 예상치 못한 오류 |

### 예외 처리

```python
# 중복 생성 시도
DuplicateRecordError: "CommonCodeGroup with code 'BUSINESS_TYPE' already exists"

# 삭제 시도하는 그룹 없음
RecordNotFoundError: "CommonCodeGroup with id {uuid} not found"

# 검증 실패
ValidationError: "Invalid data"
```

---

## 🔒 보안 및 권한

### 관리자 API 보호 (향후)

```python
# 구현 예정
@router.post("/admin/common-codes/groups")
async def create_group(
    payload: CommonCodeGroupCreate,
    current_user: User = Depends(require_role("ADMIN")),
    service = Depends(get_common_code_service),
):
    # 관리자만 접근 가능
```

### 프론트엔드 API (공개)

- 프론트엔드용 조회 API는 인증 불필요
- 활성화된 항목만 반환
- 캐싱 가능

---

## 📝 주의사항

### 1. 중복 확인

- **그룹 코드**: 시스템 전체에서 고유
- **항목 코드 키**: 각 그룹 내에서 고유

### 2. 활성/비활성 처리

- `is_active=True`인 항목만 프론트엔드에 반환
- 삭제 대신 soft delete (비활성화) 권장

### 3. 정렬 순서

- `sort_order` 필드로 UI에서의 표시 순서 제어
- 기본값: 0, 오름차순 정렬

### 4. 속성(Attributes)

- JSONB 필드로 추가 메타데이터 저장 가능
- 확장성을 위해 구조화되지 않은 데이터 저장

### 5. 캐싱 (향후)

```python
# Redis 캐싱 권장
CACHE_KEY_PATTERN = f"common_codes:{group_code}"
CACHE_TTL = 3600  # 1시간
```

---

## 📚 관련 문서

- [RFP 명세서](../RFP_KHW_v5.md#-fr-15-공통코드-관리-기능-common-code-management)
- [API 가이드](./BACKEND_API_GUIDE.md)
- [아키텍처 설계](./README.md)

---

## ✅ 체크리스트

### 구현 완료

- [x] SQLAlchemy 모델 정의
- [x] Repository 계층 구현
- [x] Service 계층 구현
- [x] Pydantic 스키마 정의
- [x] FastAPI Router 구현
- [x] 관리자용 API 엔드포인트
- [x] 프론트엔드용 API 엔드포인트
- [x] Bulk 조회 API
- [x] MCP 서버 통합
- [x] 데이터베이스 마이그레이션
- [x] 단위 테스트

### 향후 개선

- [ ] RBAC 권한 제어 추가
- [ ] Redis 캐싱 적용
- [ ] 공통코드 변경 이력 추적
- [ ] 공통코드 임포트/익스포트 기능
- [ ] 비활성 항목 숨김/표시 옵션
- [ ] 성능 최적화 (배치 처리)

---

## 📞 문의 및 지원

FR-15 구현에 대한 문의사항은 프로젝트의 Issue 탭을 참고하세요.
