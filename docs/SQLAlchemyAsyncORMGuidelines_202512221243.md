## 목적

이 문서는 **SQL을 직접 작성하던 개발자**가 **async SQLAlchemy ORM**을 사용할 때,
- `MissingGreenlet`/N+1 같은 함정을 피하고
- “SQL 실행 시점”을 예측 가능하게 만들며
- Repository/Service/Router 레이어를 깔끔하게 유지하는

실전 가이드라인을 제공합니다.  
**Codex에게 그대로 전달 가능한 규칙 + 유즈케이스별 Repository 메서드 설계**를 포함합니다.

---

## 핵심 요약 (결론)

- async 환경에서 **lazy-load(관계 지연 로딩)는 기본 금지**한다.
- 관계 데이터가 필요하면 **조회 쿼리에서 eager-load를 명시**한다.
- “DB 조회”는 **Repository**에서 끝내고, Service/Router는 **이미 로딩된 데이터로만** 로직을 수행한다.
- API 응답은 ORM 엔티티를 그대로 반환하지 말고 **DTO(Pydantic)로 변환**한다.
- 리스트/검색은 **N+1 방지**를 위해 `selectinload`를 우선 고려한다.

---

## 용어: SQL 관점 번역

- **Lazy Load**: JOIN/IN을 처음에 하지 않고, 관계 속성 접근 시점에 FK로 추가 SELECT가 나감  
  - SQL로 보면: `SELECT manual` 후 나중에 `SELECT consultation WHERE id = fk`
- **Eager Load**: 처음 조회 시점에 관계를 함께 로딩  
  - `selectinload`: `SELECT manual` + `SELECT consultation WHERE id IN (...)`
  - `joinedload`: `SELECT ... FROM manual LEFT JOIN consultation ...` (한 방)

---

## async SQLAlchemy에서 문제가 되는 구조 (MissingGreenlet의 실체)

### 왜 터지나?
- `manual.source_consultation` 같은 **관계 속성 접근**이 lazy-load를 트리거하면 내부에서 DB I/O(SELECT)가 실행될 수 있다.
- 그런데 이 DB I/O가 `await session.execute(...)` 같은 **async 안전 구간** 밖에서 발생하면 `MissingGreenlet`가 발생한다.

### 원칙
- **속성 접근 중 DB I/O가 일어나지 않도록**(=lazy-load 금지) 설계한다.
- 필요한 관계는 **Repository 쿼리에서 미리 로딩**한다.

---

## 레이어 규칙 (SQL 개발자 관점의 “SQL 실행 위치 고정”)

### Repository
- “어떤 SQL이 나가는지”를 여기서 결정한다.
- 관계 로딩(eager-load), 컬럼 선택(load_only), 필터/정렬/페이지네이션은 Repository가 책임진다.

### Service
- 트랜잭션 경계 및 업무 규칙을 담당한다.
- Repository가 가져온 엔티티로 순수 로직 수행(가능한 DB 재조회 최소화).

### Router
- 입력/출력 스키마(DTO), 권한/예외 매핑만 담당한다.
- Router 안에서 임의 쿼리 추가/관계 접근으로 lazy-load 유발하지 않는다.

---

## Eager-load 선택 기준 (실전)

### selectinload를 기본으로 두는 이유
- 컬렉션(1:N, N:M)에서 JOIN 뻥튀기를 피하기 좋다.
- N+1을 안정적으로 방지한다.
- “조회 시점에 계획된 SQL”로 동작하여 async에서도 안전하다.

### joinedload를 쓰면 좋은 경우
- 관계가 단건(1:1, N:1)이고 결과 행이 뻥튀기되지 않는 경우
- SQL로 한 번에 JOIN이 더 명확할 때

---

## 절대 하지 말 것 (async ORM 금지 패턴)

- 권한 체크/검증 로직(`def`) 내부에서 관계 접근으로 lazy-load 유발
- 루프 안에서 관계 접근(N+1)  
  예: `for m in manuals: m.source_consultation.employee_id`
- ORM 엔티티를 API 응답으로 그대로 반환 (직렬화 과정에서 관계 접근 → lazy-load 가능)
- “필요한 관계”를 쿼리에서 명시하지 않고, 나중에 객체 그래프 탐색으로 가져오려는 습관

---

## 유즈케이스별 Repository 메서드 설계 (권장)

아래 설계 목표:
1) “이 유즈케이스는 어떤 관계가 필요한지”를 메서드 이름/옵션으로 드러낸다.  
2) Router/Service에서 관계 접근으로 DB I/O가 새지 않게 한다.  
3) API별로 “필요한 eager-load”를 고정한다.

---

## 도메인/관계 가정 (예시)

- `ManualEntry.source_consultation` (N:1 또는 1:1 성격의 단건 관계)
- `ManualEntry`에는 `business_type`, `error_code`, `status`, `version_id` 등이 존재
- 상세/검색/리뷰/권한체크 등의 유즈케이스가 존재

---

## Repository 메서드 목록 (권장 시그니처)

### 1) 단건 조회: 권한 체크(초안 DRAFT)용
- 목적: `_ensure_draft_view_allowed()` 같은 순수 로직에서 관계 접근이 필요할 때, **미리 consultation을 로딩**해 두기

```py
async def get_by_id_with_consultation(self, manual_id: UUID) -> ManualEntry | None:
    ...
```

- eager-load:
  - `selectinload(ManualEntry.source_consultation)` (권장)
  - 단건이고 JOIN이 단순하면 `joinedload`도 가능

---

### 2) 단건 조회: 상세 화면(응답 DTO 구성)용
- 목적: 상세 응답에 필요한 모든 관계를 한 번에 준비

```py
async def get_detail_by_id(
    self,
    manual_id: UUID,
    *,
    include_consultation: bool = False,
    include_version: bool = False,
) -> ManualEntry | None:
    ...
```

- eager-load 옵션을 유즈케이스에 맞게 선택:
  - `include_consultation=True`이면 `selectinload(source_consultation)`
  - 버전/그룹/콘텐츠 테이블이 있다면 필요한 것만 추가

---

### 3) 리스트 조회: 목록 화면(가벼운 필드만)
- 목적: 목록에는 과한 관계 로딩을 피하고 필요한 컬럼만

```py
async def list_compact(
    self,
    *,
    status: ManualStatus | None,
    limit: int,
    employee_id: str | None = None,
) -> list[ManualEntry]:
    ...
```

- 전략:
  - 기본적으로 관계 eager-load 없음
  - (권한 정책 때문에 필요하면) `employee_id`를 조건으로 직접 필터링해서 “초안은 본인 것만” 반환
  - 필요한 경우 `load_only(ManualEntry.id, ManualEntry.topic, ...)` 고려

---

### 4) 검색: 벡터 검색 결과 매핑용(IDs → DB 조회)
- 목적: VectorStore에서 `manual_id` 리스트를 얻고, DB에서 상세를 가져와 결합

```py
async def get_many_for_search_results(
    self,
    manual_ids: list[UUID],
    *,
    include_names: bool = True,
) -> list[ManualEntry]:
    ...
```

- 전략:
  - `WHERE id IN (...)`
  - 결과 순서를 manual_ids와 동일하게 맞출 필요가 있으면 정렬 로직 추가
  - 검색 결과 화면에 필요한 관계만 selectinload

---

### 5) 그룹/버전 목록 조회
- 목적: (business_type, error_code) 그룹에 속한 버전 리스트/운영 버전 조회

```py
async def list_versions_by_group(
    self,
    *,
    business_type: str,
    error_code: str,
    include_deprecated: bool,
) -> list[ManualEntry]:
    ...
```

- 전략:
  - `status IN (...)` 필터
  - 최신순 정렬 (`updated_at` 또는 version_sort_key)

---

### 6) 승인 플로우: “기존 APPROVED 후보 조회” (정책 준수)
- 목적: 승인 시 “(업무코드, 에러코드) APPROVED 전체 후보 중 best_match 선정 → SIMILAR/SUPPLEMENT/NEW 판정”
- 이후 “SIMILAR/SUPPLEMENT일 경우 best_match만 DEPRECATED 처리” 정책 반영

```py
async def list_approved_candidates(
    self,
    *,
    business_type: str,
    error_code: str,
) -> list[ManualEntry]:
    ...
```

- 전략:
  - `status == APPROVED`만 조회
  - 비교 서비스에서 best_match 선정(Repository는 후보 제공만)

---

## Repository 구현 스켈레톤 (예시)

```py
from sqlalchemy import select
from sqlalchemy.orm import selectinload, joinedload

class ManualEntryRDBRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_by_id(self, manual_id: UUID) -> ManualEntry | None:
        stmt = select(ManualEntry).where(ManualEntry.id == manual_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_id_with_consultation(self, manual_id: UUID) -> ManualEntry | None:
        stmt = (
            select(ManualEntry)
            .where(ManualEntry.id == manual_id)
            .options(selectinload(ManualEntry.source_consultation))
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_compact(self, *, status: ManualStatus | None, limit: int, employee_id: str | None = None):
        stmt = select(ManualEntry)
        if status is not None:
            stmt = stmt.where(ManualEntry.status == status)

        # (권한 정책) DRAFT는 본인 것만 (예시: consultation.employee_id로 제한)
        # employee_id 필터가 필요하면, 여기서 JOIN 또는 서브쿼리로 "명시적으로" 처리한다.
        # lazy-load로 employee_id를 읽어오지 않는다.

        stmt = stmt.limit(limit)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())
```

---

## Router/Service 적용 규칙 (Codex에게 지시)

### 권한 체크 함수는 “순수 로직”으로 유지
- `_ensure_draft_view_allowed()`는 계속 `def`로 유지한다.
- 단, 이 함수가 접근하는 관계(`manual.source_consultation`)는 **반드시 repo에서 eager-load로 준비**한다.

### Router에서의 적용 예 (기존 코드 개선)
- `get_by_id()` 대신 `get_by_id_with_consultation()` 사용:

```py
repo = ManualEntryRDBRepository(service.session)
manual_entry = await repo.get_by_id_with_consultation(draft_id)
_ensure_draft_view_allowed(manual_entry, current_user)
```

### “조회 2번” 방지 권장
- Router에서 `repo.get_by_id(...)`로 한 번 조회한 뒤,
  `service.get_manual(...)`에서 또 조회하는 구조가 있다면 유즈케이스별로 정리한다.
- 권장 방향:
  - service가 “상세 조회 + 필요한 eager-load”까지 담당하고
  - Router는 service 결과로 권한 체크/응답만 수행

---

## 실전 체크리스트

- [ ] 이 API는 SQL이 몇 번 나가는가? (1~3번 내로 예측 가능한가?)
- [ ] 권한 체크/검증 로직에서 관계 접근이 있는가? (있으면 eager-load로 미리 준비했는가?)
- [ ] 리스트/검색에서 루프 안 관계 접근이 있는가? (N+1 위험)
- [ ] 엔티티를 그대로 응답으로 내보내는가? (직렬화 lazy-load 위험)
- [ ] eager-load가 “항상” 필요한 관계인가? (필요할 때만 켜는가?)

---

## Codex 작업 지시 요약

1) async 환경에서 lazy-load 발생 가능 지점을 찾아 제거한다.  
2) `_ensure_draft_view_allowed()` 같은 순수 로직 함수 내부에서 DB I/O가 발생하지 않도록,
   필요한 관계는 repository에서 eager-load 한다.  
3) 유즈케이스별 repo 메서드를 추가하고, Router/Service에서 해당 메서드를 사용하도록 교체한다.  
4) 리스트/검색 API에서 N+1이 발생하지 않도록 `selectinload` 기반의 조회를 우선 적용한다.
