# SQLAlchemy Async ORM 전체 마이그레이션 가이드

이 문서는 `SQLAlchemyAsyncORMGuidelines_202512221243.md`를 기반으로, 현재 프로젝트 전반을 **레포지토리 구조별**로 마이그레이션하기 위한 실행 가이드입니다.

## 1. 목적과 전제

- async 환경에서 **lazy-load 금지**를 기본 원칙으로 한다.
- **Service가 조회 + eager-load + 응답 구성**까지 담당한다.
- Repository는 **쿼리 정의와 관계 로딩 전략을 고정**한다.
- 응답은 **DTO(Pydantic)** 로 변환한다.
- 리스트/검색/태스크 조회는 **selectinload 우선**을 기본값으로 한다.

## 2. 공통 원칙 (전체 레이어)

- 관계 접근으로 추가 쿼리가 발생하지 않도록, **조회 시점에 eager-load를 명시**한다.
- Router는 입력/출력 매핑과 예외 매핑만 담당하고 **DB 조회/권한 체크를 직접 수행하지 않는다**.
- Service는 **권한 체크 + 조회 + 응답 구성**의 단일 진입점이 된다.
- Repository는 유즈케이스별로 **관계 로딩 옵션을 고정**한 메서드를 제공한다.

## 3. 레포지토리 구조별 마이그레이션 가이드

### 3.1 `app/models/`

- 관계는 기본적으로 lazy-load이므로, **Repository에서 eager-load 사용을 전제로 설계**한다.
- 모델 정의 자체는 변경 최소화, 다만 **관계 명칭/방향은 명확히** 한다.

체크리스트:
- [ ] 관계 필드 명이 사용처에서 혼동되지 않는가?
- [ ] 순환 관계 접근이 있을 경우 eager-load로 처리 가능한가?

### 3.2 `app/repositories/`

역할: **SQL과 eager-load를 고정**하는 위치

핵심 규칙:
- 유즈케이스별 메서드에 **selectinload/joinedload를 명시**한다.
- Service/Router에서 관계 접근이 발생하는 경우, 해당 Repository 메서드는 **관계 로딩을 포함**해야 한다.
- 검색/리스트/태스크 목록은 **selectinload 우선**으로 N+1을 방지한다.

권장 패턴:
- `get_by_id_with_consultation(...)`
- `list_tasks_with_entries(...)`
- `find_by_manual_id_with_entries(...)`

체크리스트:
- [ ] 라우터/서비스에서 관계 접근이 있는가?
- [ ] 해당 관계는 Repository에서 eager-load로 준비되는가?
- [ ] 리스트/검색/태스크 조회에서 N+1이 발생하지 않는가?

### 3.3 `app/services/`

역할: **권한 체크 + 조회 + 응답 구성**을 전담

핵심 규칙:
- 권한 체크는 Service에서 수행한다.
- Service는 **Repository의 eager-load 메서드를 호출**한다.
- DTO 변환을 Service에서 수행하고 Router로 반환한다.

권장 패턴:
- `get_manual(manual_id, current_user)` 처럼 사용자 컨텍스트를 받는 메서드
- `diff_draft_with_active(draft_id, current_user, ...)` 처럼 권한 체크 포함

체크리스트:
- [ ] Service가 권한 체크를 수행하는가?
- [ ] Service가 eager-load된 모델로만 로직을 수행하는가?
- [ ] 응답 DTO 변환이 Service에서 끝나는가?

### 3.4 `app/api/routers/`

역할: **입력 검증/예외 매핑/응답 반환**

핵심 규칙:
- Router에서 **Repository 직접 호출 금지**
- Router는 Service 호출 결과를 반환한다.
- 권한 체크는 Service로 위임한다.

체크리스트:
- [ ] Router에 DB 조회 코드가 있는가?
- [ ] 권한 체크가 Router에서 수행되는가?
- [ ] 예외 매핑만 수행하는가?

### 3.5 `app/schemas/`

역할: **DTO 정의와 API 계약 고정**

핵심 규칙:
- ORM 엔티티를 그대로 반환하지 않는다.
- 필요한 필드만 스키마에 노출한다.

체크리스트:
- [ ] 응답 스키마가 관계 필드를 직접 노출하지 않는가?
- [ ] ORM → DTO 변환 경로가 일관적인가?

### 3.6 `app/vectorstore/` 및 `app/llm/`

역할: **외부 I/O 의존성 분리**

핵심 규칙:
- DB 로직을 포함하지 않는다.
- 서비스가 외부 I/O를 조율한다.

체크리스트:
- [ ] 서비스 외부에서 DB 접근이 발생하지 않는가?

### 3.7 `app/queue/` 및 `app/mcp/`

역할: **비동기 작업/도구 인터페이스**

핵심 규칙:
- 조회/권한 체크는 Service로 위임한다.
- Repository를 직접 호출하지 않는다.

체크리스트:
- [ ] Queue/MCP에서 Repository 직접 호출이 없는가?
- [ ] Service 호출만으로 기능이 완결되는가?

### 3.8 `app/core/`

역할: **DB 세션/예외/의존성**

핵심 규칙:
- 세션 주입은 Router 단에서만 이루어지고, Service에서 활용한다.
- 예외는 Service에서 발생시키고 Router에서 매핑한다.

체크리스트:
- [ ] Service가 예외를 발생시키고 Router가 매핑하는 구조인가?

### 3.9 `tests/`

역할: **레이어별 검증**

핵심 규칙:
- Service 레벨에서 권한/로딩 로직 검증
- Repository 레벨에서 eager-load 전략 검증

체크리스트:
- [ ] lazy-load로 인한 오류가 테스트에서 재현/차단되는가?
- [ ] N+1 방지 시나리오가 있는가?

## 4. 마이그레이션 단계

1) **라우터 점검**
- Repository 직접 호출 제거
- Service 호출로 위임

2) **서비스 점검**
- 권한 체크 이동
- eager-load 메서드 호출
- DTO 변환 통합

3) **Repository 점검**
- 유즈케이스별 eager-load 메서드 추가
- selectinload 기본화

4) **테스트 보강**
- 권한/로딩/N+1 테스트 추가

## 5. 빠른 체크리스트

- [ ] Router에서 DB 조회 제거
- [ ] Service가 권한 체크 수행
- [ ] Repository에서 eager-load 명시
- [ ] 리스트/검색/태스크에 selectinload 적용
- [ ] ORM 엔티티 직접 응답 금지

## 6. 예시 패턴

### Service 권한 체크 + eager-load

```py
manual = await manual_repo.get_by_id_with_consultation(manual_id)
ensure_draft_view_allowed(manual, current_user)
response = ManualEntryResponse.model_validate(manual)
```

### Repository selectinload

```py
stmt = select(ManualReviewTask).options(
    selectinload(ManualReviewTask.old_entry),
    selectinload(ManualReviewTask.new_entry),
)
```

---

이 문서는 프로젝트 전반의 async ORM 사용을 **예측 가능하고 안전하게** 유지하기 위한 기준 문서로 사용한다.
