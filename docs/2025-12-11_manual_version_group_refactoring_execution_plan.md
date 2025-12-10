# 메뉴얼 버전 그룹 관리 실행 계획 (실제 구현)

**문서 작성일:** 2025-12-11
**목적:** 계획 문서(2025-12-10)와 실제 코드의 불일치를 해결하기 위한 구체적 실행 계획
**상태:** 🟢 즉시 구현 가능 (복사-붙여넣기 준비 완료)

---

## 📋 목차

1. [현황 재분석](#현황-재분석)
2. [3-Phase 구현 전략](#3-phase-구현-전략)
3. [Phase 1: 모델 + Repository](#phase-1-모델--repository)
4. [Phase 2: Service + API](#phase-2-service--api)
5. [Phase 3: 테스트 + 마이그레이션](#phase-3-테스트--마이그레이션)
6. [검증 및 롤백](#검증-및-롤백)

---

## 현황 재분석

### 계획 vs 실제 상태

| 항목 | 계획 (2025-12-10) | 실제 코드 | 상태 |
|------|------------------|---------|------|
| ManualVersion 필드 | business_type, error_code 추가 | ❌ 없음 | ❌ 미구현 |
| Unique 제약 | (business_type, error_code, version) | ❌ (version)만 | ❌ 미구현 |
| Repository.get_latest_version() | 그룹 필터 파라미터 | ❌ 없음 | ❌ 미구현 |
| Repository.list_versions() | 그룹 필터 파라미터 | ❌ 없음 | ❌ 미구현 |
| ManualService.approve_manual() | 그룹별 버전 생성 | ❌ 전역 버전 | ❌ 미구현 |
| /manuals/{manual_id}/diff | UUID 기반 | ❌ str 기반 | ❌ 미구현 |
| _resolve_versions_for_diff() | 그룹 필터 | ❌ 없음 | ❌ 미구현 |
| 마이그레이션 파일 | SQL 제공 | ❌ 없음 | ❌ 미구현 |
| 테스트 (T1~T5) | 상세 코드 제공 | ❌ 기본만 | ⚠️ 부분 |

### 불일치 파일 목록

```
실제 코드:
  app/models/manual.py (106-123)
  app/repositories/manual_rdb.py (167-203)
  app/services/manual_service.py (331-369, 371-441, 458-500, 813-850)
  app/routers/manuals.py (153-177)

계획 문서:
  docs/2025-12-10_manual_version_group_refactoring.md
  (168-233: 모델, 214-310: Repository, 365-441: Service, 668-715: API)
```

---

## 3-Phase 구현 전략

### 왜 3-Phase인가?

**대형 변경을 작은 단위로 나누어** 각 단계마다 검증하고 필요시 롤백할 수 있게 합니다.

```
Phase 1: 데이터 구조 변경 (모델 + Repository)
  ✅ DB 스키마 변경
  ✅ Repository 메소드 추가/수정
  ❌ Service/API는 아직 미사용
  → 기존 코드는 그대로 작동

Phase 2: 비즈니스 로직 변경 (Service + API)
  ✅ Service가 새로운 Repository 메소드 사용
  ✅ API 경로 변경
  ❌ 테스트는 아직 준비 중
  → 기능 동작 검증

Phase 3: 테스트 + 검증 (Test + Migration 파일)
  ✅ 통합 테스트 추가
  ✅ 마이그레이션 파일 생성
  ✅ 롤백 계획 검증
  → 프로덕션 배포 준비
```

---

## Phase 1: 모델 + Repository

### 예상 시간: 1.5시간
### 영향도: 중간 (DB 스키마 변경)
### 주의: Phase 1 완료 후 **테스트 실행 필수**

---

### 1.1 ManualVersion 모델 수정

**파일:** `app/models/manual.py`

**현재 코드 (lines 106-123):**
```python
class ManualVersion(BaseModel):
    """
    FR-5: 메뉴얼 버전 관리
    """

    __tablename__ = "manual_versions"

    version: Mapped[str] = mapped_column(String(50), nullable=False, unique=True)
    description: Mapped[str | None] = mapped_column(Text)
    changelog: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    entries: Mapped[list[ManualEntry]] = relationship(
        "ManualEntry",
        back_populates="version",
    )

    def __repr__(self) -> str:
        return f"<ManualVersion(id={self.id}, version={self.version})>"
```

**변경 코드:**
```python
from sqlalchemy import UniqueConstraint

class ManualVersion(BaseModel):
    """
    FR-5: 메뉴얼 버전 관리 (그룹별 독립적)

    변경사항 (2025-12-11):
    - business_type, error_code 필드 추가 (메뉴얼 그룹 식별)
    - 유니크 제약을 (business_type, error_code, version)으로 변경
    - 같은 그룹 내에서만 version이 유일하게 유지

    예시:
      그룹 A (인터넷뱅킹::ERR_LOGIN_001) → v1, v2, v3
      그룹 B (모바일뱅킹::ERR_OTP_002) → v1, v2
      (둘 다 "v1"을 가지지만 다른 버전 레코드)
    """

    __tablename__ = "manual_versions"

    # 메뉴얼 그룹 정보 (필수: 그룹 식별)
    business_type: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
        index=True,
        comment="업무구분 (그룹 식별용, nullable은 기존 데이터 호환성)",
    )
    error_code: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
        index=True,
        comment="에러코드 (그룹 식별용, nullable은 기존 데이터 호환성)",
    )

    # 버전 정보
    version: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        comment="버전 번호 (그룹 내에서 유일, unique=True 제거됨)",
    )
    description: Mapped[str | None] = mapped_column(Text)
    changelog: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    # 관계
    entries: Mapped[list[ManualEntry]] = relationship(
        "ManualEntry",
        back_populates="version",
    )

    # 유니크 제약: (business_type, error_code, version) 조합만 유일
    __table_args__ = (
        UniqueConstraint(
            "business_type",
            "error_code",
            "version",
            name="uq_manual_version_group",
            comment="같은 그룹 내에서만 버전이 유일",
        ),
    )

    def __repr__(self) -> str:
        group_key = f"{self.business_type}::{self.error_code}" if self.business_type else "unknown"
        return (
            f"<ManualVersion("
            f"id={self.id}, "
            f"group={group_key}, "
            f"version={self.version}"
            f")>"
        )
```

**변경 요점:**
- ✅ `business_type`, `error_code` 필드 추가 (nullable=True는 마이그레이션 시 기존 데이터 호환)
- ✅ `version` 컬럼에서 `unique=True` 제거
- ✅ `UniqueConstraint` 추가 (3개 컬럼 조합)
- ✅ 인덱스 자동 생성 (index=True로)

---

### 1.2 ManualVersionRepository 메소드 수정

**파일:** `app/repositories/manual_rdb.py`

**현재 코드 (lines 167-203):**
```python
class ManualVersionRepository(BaseRepository[ManualVersion]):
    def __init__(self, session: AsyncSession):
        super().__init__(ManualVersion, session)

    async def get_latest_version(self) -> ManualVersion | None:
        """최신 버전 조회"""
        stmt = (
            select(ManualVersion)
            .order_by(ManualVersion.created_at.desc())
            .limit(1)
        )
        result = await self.session.execute(stmt)
        return result.scalars().first()

    async def get_by_version(self, version: str) -> ManualVersion | None:
        """버전 번호로 조회"""
        stmt = select(ManualVersion).where(ManualVersion.version == version)
        result = await self.session.execute(stmt)
        return result.scalars().first()

    async def list_versions(self, limit: int = 100) -> Sequence[ManualVersion]:
        """버전 목록 조회 (최신순)"""
        stmt = (
            select(ManualVersion)
            .order_by(ManualVersion.created_at.desc())
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return result.scalars().all()
```

**변경 코드:**
```python
class ManualVersionRepository(BaseRepository[ManualVersion]):
    """
    ManualVersion 저장소 (그룹별 버전 관리)

    변경사항 (2025-12-11):
    - get_latest_version(): business_type, error_code 파라미터 추가 (그룹 필터)
    - get_by_version(): 그룹 필터 파라미터 추가 (더 정확한 검색)
    - list_versions(): 그룹 필터 파라미터 추가
    """

    def __init__(self, session: AsyncSession):
        super().__init__(ManualVersion, session)

    async def get_latest_version(
        self,
        business_type: str | None = None,
        error_code: str | None = None,
    ) -> ManualVersion | None:
        """
        그룹별 최신 버전 조회

        Args:
            business_type: 업무코드 (그룹 필터)
            error_code: 에러코드 (그룹 필터)

        Returns:
            해당 그룹의 최신 버전 또는 None

        예시:
            # 인터넷뱅킹::ERR_LOGIN_001 그룹의 최신 버전
            v = await repo.get_latest_version(
                business_type="인터넷뱅킹",
                error_code="ERR_LOGIN_001",
            )
            # → ManualVersion(version="2", business_type="인터넷뱅킹", error_code="ERR_LOGIN_001")

            # 필터 없이 호출 (전역, 기존 호환성)
            v = await repo.get_latest_version()
            # → 가장 최근에 생성된 버전 (그룹 무관)
        """
        stmt = select(ManualVersion)

        # 그룹 필터링 (둘 다 None이면 필터링 안 함 = 기존 동작)
        if business_type is not None:
            stmt = stmt.where(ManualVersion.business_type == business_type)
        if error_code is not None:
            stmt = stmt.where(ManualVersion.error_code == error_code)

        # 최신순 정렬
        stmt = stmt.order_by(ManualVersion.created_at.desc()).limit(1)
        result = await self.session.execute(stmt)
        return result.scalars().first()

    async def get_by_version(
        self,
        version: str,
        business_type: str | None = None,
        error_code: str | None = None,
    ) -> ManualVersion | None:
        """
        버전 번호로 조회 (그룹 필터링 가능)

        Args:
            version: 버전 번호 (예: "1", "2", "v1")
            business_type: 업무코드 (선택, 더 정확한 검색)
            error_code: 에러코드 (선택, 더 정확한 검색)

        Returns:
            해당 버전 또는 None

        예시:
            # 인터넷뱅킹::ERR_LOGIN_001 그룹의 v2
            v = await repo.get_by_version(
                "2",
                business_type="인터넷뱅킹",
                error_code="ERR_LOGIN_001",
            )

            # 필터 없이 호출 (기존 호환성, 다중 결과 가능)
            v = await repo.get_by_version("1")
            # → 첫 번째 결과만 반환 (version="1"인 모든 그룹)
        """
        stmt = select(ManualVersion).where(ManualVersion.version == version)

        # 그룹 필터링 (optional)
        if business_type is not None:
            stmt = stmt.where(ManualVersion.business_type == business_type)
        if error_code is not None:
            stmt = stmt.where(ManualVersion.error_code == error_code)

        result = await self.session.execute(stmt)
        return result.scalars().first()

    async def list_versions(
        self,
        business_type: str | None = None,
        error_code: str | None = None,
        limit: int = 100,
    ) -> Sequence[ManualVersion]:
        """
        버전 목록 조회 (최신순, 그룹별 필터링 가능)

        Args:
            business_type: 업무코드 (그룹 필터)
            error_code: 에러코드 (그룹 필터)
            limit: 최대 결과 수

        Returns:
            버전 목록 (최신순)

        예시:
            # 인터넷뱅킹::ERR_LOGIN_001 그룹의 모든 버전
            versions = await repo.list_versions(
                business_type="인터넷뱅킹",
                error_code="ERR_LOGIN_001",
            )
            # → [v3, v2, v1] (최신순)

            # 필터 없이 호출 (전체 버전, 기존 호환성)
            versions = await repo.list_versions()
            # → 모든 버전 (그룹 무관, 최신순)
        """
        stmt = select(ManualVersion)

        # 그룹 필터링
        if business_type is not None:
            stmt = stmt.where(ManualVersion.business_type == business_type)
        if error_code is not None:
            stmt = stmt.where(ManualVersion.error_code == error_code)

        # 정렬 및 제한
        stmt = stmt.order_by(ManualVersion.created_at.desc()).limit(limit)
        result = await self.session.execute(stmt)
        return result.scalars().all()
```

**변경 요점:**
- ✅ 3개 메소드 모두 `business_type`, `error_code` 파라미터 추가
- ✅ 파라미터가 None이면 필터링 안 함 (기존 호환성)
- ✅ 상세한 docstring과 예시

---

### 1.3 검증 쿼리 (Phase 1 완료 후)

**실행:** `alembic upgrade head` 후 다음 쿼리 확인

```sql
-- 1. 테이블 구조 확인
\d manual_versions;

-- 예상 결과:
-- Column       |            Type             | Collation | Nullable | Default
-- id           | uuid                        |           |          |
-- created_at   | timestamp without time zone |           | not null |
-- updated_at   | timestamp without time zone |           | not null |
-- version      | character varying(50)       |           | not null |
-- description  | text                        |           |          |
-- changelog    | jsonb                       |           |          |
-- business_type| character varying(50)       |           |          | ← 신규
-- error_code   | character varying(50)       |           |          | ← 신규

-- 2. 유니크 제약 확인
SELECT constraint_name, constraint_type
FROM information_schema.table_constraints
WHERE table_name = 'manual_versions';

-- 예상 결과:
-- constraint_name        | constraint_type
-- manual_versions_pkey   | PRIMARY KEY
-- uq_manual_version_group| UNIQUE                    ← 신규

-- 3. 인덱스 확인
SELECT indexname FROM pg_indexes WHERE tablename = 'manual_versions';

-- 예상 결과:
-- ix_manual_versions_business_type  ← 신규
-- ix_manual_versions_error_code     ← 신규
```

---

## Phase 2: Service + API

### 예상 시간: 2시간
### 영향도: 높음 (API 경로 변경)
### 주의: Phase 1이 성공적으로 배포된 후에만 시작

---

### 2.1 ManualService.approve_manual() 수정

**파일:** `app/services/manual_service.py`

**현재 코드 (lines 331-369):**
```python
async def approve_manual(
    self,
    manual_id: UUID,
    request: ManualApproveRequest,
) -> ManualVersionInfo:
    """FR-4/FR-5: 메뉴얼 승인 및 전체 버전 세트 갱신.

    금융권 정책집: 전체 버전 일괄 적용 컨셉을 반영해 모든 승인 시 Version을
    1씩 증가시키며, 동일 키(업무구분/에러코드) 기존 항목은 DEPRECATED 처리한다.
    APPROVED 항목만 VectorStore에 인덱싱한다.
    """

    manual = await self.manual_repo.get_by_id(manual_id)
    if manual is None:
        raise RecordNotFoundError(f"ManualEntry(id={manual_id}) not found")

    logger.info(
        "manual_approve_start",
        manual_id=str(manual_id),
        approver_id=str(request.approver_id),
    )

    latest_version = await self.version_repo.get_latest_version()
    next_version_num = self._next_version_number(latest_version)
    next_version = ManualVersion(version=str(next_version_num))
    await self.version_repo.create(next_version)

    await self._deprecate_previous_entries(manual)

    manual.status = ManualStatus.APPROVED
    manual.version_id = next_version.id
    await self.manual_repo.update(manual)

    await self._index_manual_vector(manual)

    return ManualVersionInfo(
        version=next_version.version,
        approved_at=next_version.created_at,
    )
```

**변경 코드:**
```python
async def approve_manual(
    self,
    manual_id: UUID,
    request: ManualApproveRequest,
) -> ManualVersionInfo:
    """
    FR-4/FR-5: 메뉴얼 승인 및 그룹별 버전 관리

    변경사항 (2025-12-11):
    - 전역 버전 대신 그룹별 독립적 버전 관리
    - 같은 그룹(business_type + error_code)의 최신 버전만 조회
    - ManualVersion 생성 시 그룹 정보(business_type, error_code) 저장

    정책:
    - 각 메뉴얼 그룹은 독립적인 버전 시퀀스 유지
    - 예: 인터넷뱅킹::ERR_LOGIN_001 → v1, v2, v3
         모바일뱅킹::ERR_OTP_002 → v1, v2 (독립적)
    """

    manual = await self.manual_repo.get_by_id(manual_id)
    if manual is None:
        raise RecordNotFoundError(f"ManualEntry(id={manual_id}) not found")

    logger.info(
        "manual_approve_start",
        manual_id=str(manual_id),
        approver_id=str(request.approver_id),
        group=f"{manual.business_type}::{manual.error_code}",
    )

    # ✅ 변경: 같은 그룹의 최신 버전만 조회
    latest_version = await self.version_repo.get_latest_version(
        business_type=manual.business_type,
        error_code=manual.error_code,
    )
    next_version_num = self._next_version_number(latest_version)

    # ✅ 변경: 신규 버전에 그룹 정보 저장
    next_version = ManualVersion(
        version=str(next_version_num),
        business_type=manual.business_type,
        error_code=manual.error_code,
    )
    await self.version_repo.create(next_version)

    logger.info(
        "manual_version_created",
        manual_id=str(manual_id),
        group=f"{manual.business_type}::{manual.error_code}",
        version=next_version.version,
        version_id=str(next_version.id),
    )

    await self._deprecate_previous_entries(manual)

    manual.status = ManualStatus.APPROVED
    manual.version_id = next_version.id
    await self.manual_repo.update(manual)

    await self._index_manual_vector(manual)

    return ManualVersionInfo(
        version=next_version.version,
        approved_at=next_version.created_at,
    )
```

**변경 요점:**
- ✅ `get_latest_version()` 호출 시 business_type, error_code 전달
- ✅ `ManualVersion` 생성 시 그룹 정보 저장
- ✅ 로깅 개선 (그룹 정보 추가)

---

### 2.2 ManualService.list_versions() 수정

**파일:** `app/services/manual_service.py`

**현재 코드 (lines 371-441):**
```python
async def list_versions(self, manual_id: UUID) -> list[ManualVersionResponse]:
    """FR-14: 특정 메뉴얼 그룹의 버전 목록 조회 (최신순, 현재 버전 표시 포함).

    같은 business_type/error_code를 가진 메뉴얼들의 버전을 모두 반환합니다.
    """

    # 1. 기준 메뉴얼 조회
    manual = await self.manual_repo.get_by_id(manual_id)
    if manual is None:
        raise RecordNotFoundError(f"ManualEntry(id={manual_id}) not found")

    # 2. 같은 그룹의 APPROVED/DEPRECATED 메뉴얼만 조회 (business_type + error_code)
    # DRAFT는 version_id가 NULL이므로 버전 목록에 포함되지 않음
    group_entries = list(
        await self.manual_repo.find_by_business_and_error(
            business_type=manual.business_type,
            error_code=manual.error_code,
            statuses={ManualStatus.APPROVED, ManualStatus.DEPRECATED},
        )
    )

    if not group_entries:
        return []

    # 3. 그룹 메뉴얼들의 버전 ID 추출 (중복 제거)
    version_ids = set()
    for entry in group_entries:
        if entry.version_id is not None:
            version_ids.add(entry.version_id)

    if not version_ids:
        return []

    # 4. 버전 정보 조회 및 정렬 (최신순)
    all_versions = await self.version_repo.list_versions()
    group_versions = [v for v in all_versions if v.id in version_ids]

    if not group_versions:
        return []

    result: list[ManualVersionResponse] = []
    for idx, v in enumerate(group_versions):
        # 가장 최신 버전(첫 번째 항목)에만 "(현재 버전)" 표시
        label = f"{v.version} (현재 버전)" if idx == 0 else v.version

        # created_at을 YYYY-MM-DD 형식으로 변환
        date_str = v.created_at.strftime("%Y-%m-%d")

        result.append(
            ManualVersionResponse(
                version=v.version,  # alias "version" used here
                label=label,
                date=date_str,
                id=v.id,
                created_at=v.created_at,
                updated_at=v.updated_at,
            )
        )

    return result
```

**변경 코드:**
```python
async def list_versions(self, manual_id: UUID) -> list[ManualVersionResponse]:
    """
    FR-14: 특정 메뉴얼 그룹의 버전 목록 조회 (최신순, 현재 버전 표시)

    변경사항 (2025-12-11):
    - Repository의 그룹 필터링 활용 (수동 필터링 제거)
    - 그룹별 버전만 직접 조회하므로 쿼리 효율성 개선
    - 코드 가독성 향상
    """

    # 1. 기준 메뉴얼 조회 (그룹 정보 추출)
    manual = await self.manual_repo.get_by_id(manual_id)
    if manual is None:
        raise RecordNotFoundError(f"ManualEntry(id={manual_id}) not found")

    # ✅ 변경: Repository의 그룹 필터링 활용
    # 이전: 모든 버전을 조회 후 version_id로 필터링 (비효율)
    # 현재: Repository가 그룹 필터링을 담당 (효율적)
    group_versions = list(
        await self.version_repo.list_versions(
            business_type=manual.business_type,
            error_code=manual.error_code,
        )
    )

    if not group_versions:
        return []

    result: list[ManualVersionResponse] = []
    for idx, v in enumerate(group_versions):
        # 가장 최신 버전(첫 번째 항목)에만 "(현재 버전)" 표시
        label = f"{v.version} (현재 버전)" if idx == 0 else v.version

        # created_at을 YYYY-MM-DD 형식으로 변환
        date_str = v.created_at.strftime("%Y-%m-%d")

        result.append(
            ManualVersionResponse(
                version=v.version,
                label=label,
                date=date_str,
                id=v.id,
                created_at=v.created_at,
                updated_at=v.updated_at,
            )
        )

    return result
```

**변경 요점:**
- ✅ 수동 필터링 제거 (Repository 사용)
- ✅ 쿼리 간소화 (find_by_business_and_error + 버전 수동 필터링 제거)
- ✅ 코드 길이 단축 (38줄 → 22줄)

---

### 2.3 ManualService._resolve_versions_for_diff() 수정

**파일:** `app/services/manual_service.py`

**현재 코드 (lines 813-850):**
```python
async def _resolve_versions_for_diff(
    self,
    *,
    base_version: str | None,
    compare_version: str | None,
) -> tuple[ManualVersion | None, ManualVersion | None]:
    """Diff 시나리오별 base/compare 버전 결정."""

    if compare_version and base_version is None:
        raise ValidationError("compare_version을 사용할 때는 base_version을 함께 지정하세요.")

    if base_version and compare_version:
        base = await self.version_repo.get_by_version(base_version)
        compare = await self.version_repo.get_by_version(compare_version)
        if base is None:
            raise RecordNotFoundError(f"Base version {base_version} not found")
        if compare is None:
            raise RecordNotFoundError(f"Compare version {compare_version} not found")
        return base, compare

    if base_version and compare_version is None:
        base = await self.version_repo.get_by_version(base_version)
        if base is None:
            raise RecordNotFoundError(f"Base version {base_version} not found")
        latest = await self.version_repo.get_latest_version()
        if latest is None:
            raise RecordNotFoundError("비교할 최신 버전이 없습니다.")
        if latest.id == base.id:
            versions = await self.version_repo.list_versions(limit=2)
            if len(versions) < 2:
                raise ValidationError("동일 버전을 비교할 수 없습니다. 다른 버전을 지정하세요.")
            return versions[1], versions[0]
        return base, latest

    versions = await self.version_repo.list_versions(limit=2)
    if len(versions) < 2:
        raise ValidationError("최신/직전 비교를 위해 최소 2개 버전이 필요합니다.")
    return versions[1], versions[0]
```

**변경 코드:**
```python
async def _resolve_versions_for_diff(
    self,
    *,
    business_type: str | None,
    error_code: str | None,
    base_version: str | None,
    compare_version: str | None,
) -> tuple[ManualVersion | None, ManualVersion | None]:
    """
    Diff 시나리오별 base/compare 버전 결정 (그룹 기반)

    변경사항 (2025-12-11):
    - business_type, error_code 파라미터 추가 (그룹 필터)
    - 모든 버전 조회에 그룹 필터링 적용
    - 해당 그룹의 버전만 비교

    시나리오:
    1. base_version + compare_version: 두 버전 모두 명시
    2. base_version만: base_version vs 최신 버전
    3. 없음: 최신 버전 vs 직전 버전
    """

    if compare_version and base_version is None:
        raise ValidationError("compare_version을 사용할 때는 base_version을 함께 지정하세요.")

    if base_version and compare_version:
        # ✅ 변경: 그룹 필터 추가
        base = await self.version_repo.get_by_version(
            base_version,
            business_type=business_type,
            error_code=error_code,
        )
        compare = await self.version_repo.get_by_version(
            compare_version,
            business_type=business_type,
            error_code=error_code,
        )
        if base is None:
            raise RecordNotFoundError(f"Base version '{base_version}' not found in group {business_type}::{error_code}")
        if compare is None:
            raise RecordNotFoundError(f"Compare version '{compare_version}' not found in group {business_type}::{error_code}")
        return base, compare

    if base_version and compare_version is None:
        # ✅ 변경: 그룹 필터 추가
        base = await self.version_repo.get_by_version(
            base_version,
            business_type=business_type,
            error_code=error_code,
        )
        if base is None:
            raise RecordNotFoundError(f"Base version '{base_version}' not found in group {business_type}::{error_code}")

        # ✅ 변경: 같은 그룹의 최신 버전
        latest = await self.version_repo.get_latest_version(
            business_type=business_type,
            error_code=error_code,
        )
        if latest is None:
            raise RecordNotFoundError("비교할 최신 버전이 없습니다.")
        if latest.id == base.id:
            # base가 이미 최신이면 이전 버전과 비교
            versions = await self.version_repo.list_versions(
                business_type=business_type,
                error_code=error_code,
                limit=2,
            )
            if len(versions) < 2:
                raise ValidationError("동일 버전을 비교할 수 없습니다. 다른 버전을 지정하세요.")
            return versions[1], versions[0]
        return base, latest

    # base_version도 없으면 최신 2개 버전 (같은 그룹)
    # ✅ 변경: 그룹 필터 추가
    versions = await self.version_repo.list_versions(
        business_type=business_type,
        error_code=error_code,
        limit=2,
    )
    if len(versions) < 2:
        raise ValidationError("최신/직전 비교를 위해 최소 2개 버전이 필요합니다.")
    return versions[1], versions[0]
```

**변경 요점:**
- ✅ `business_type`, `error_code` 파라미터 추가
- ✅ 모든 버전 조회에 그룹 필터링 적용
- ✅ 오류 메시지에 그룹 정보 추가

---

### 2.4 ManualService.diff_versions() 수정

**파일:** `app/services/manual_service.py`

**현재 코드 (lines 458-500):**
```python
async def diff_versions(
    self,
    manual_group_id: str,
    *,
    base_version: str | None,
    compare_version: str | None,
    summarize: bool = False,
) -> ManualVersionDiffResponse:
    """FR-14 시나리오 A/B: 버전 간 Diff."""

    base, compare = await self._resolve_versions_for_diff(
        base_version=base_version,
        compare_version=compare_version,
    )
    # ... 나머지 코드
```

**변경 코드:**
```python
async def diff_versions(
    self,
    manual_id: UUID,  # ✅ 변경: manual_group_id (str) → manual_id (UUID)
    *,
    base_version: str | None,
    compare_version: str | None,
    summarize: bool = False,
) -> ManualVersionDiffResponse:
    """
    FR-14: 버전 간 Diff (그룹별)

    변경사항 (2025-12-11):
    - manual_group_id (str) 대신 manual_id (UUID) 사용
    - manual_id로부터 그룹 정보(business_type, error_code) 추출
    - 해당 그룹의 버전만 비교

    시나리오:
    A. base_version + compare_version: 두 버전 비교
    B. base_version만: base vs 최신
    C. 없음: 최신 vs 직전
    """

    # ✅ 변경: manual_id로부터 그룹 정보 추출
    manual = await self.manual_repo.get_by_id(manual_id)
    if manual is None:
        raise RecordNotFoundError(f"ManualEntry(id={manual_id}) not found")

    base, compare = await self._resolve_versions_for_diff(
        business_type=manual.business_type,  # ✅ 변경: 그룹 정보 전달
        error_code=manual.error_code,
        base_version=base_version,
        compare_version=compare_version,
    )
    # ... 나머지 코드는 동일
```

**변경 요점:**
- ✅ 파라미터: `manual_group_id: str` → `manual_id: UUID`
- ✅ manual_id로부터 그룹 정보 추출
- ✅ `_resolve_versions_for_diff()` 호출 시 그룹 정보 전달

---

### 2.5 API 라우트 수정

**파일:** `app/routers/manuals.py`

**현재 코드 (lines 153-177):**
```python
@router.get(
    "/{manual_group_id}/diff",
    response_model=ManualVersionDiffResponse,
    summary="Diff manual versions",
)
async def diff_manual_versions(
    manual_group_id: str,
    base_version: str | None = None,
    compare_version: str | None = None,
    summarize: bool = False,
    service: ManualService = Depends(get_manual_service),
) -> ManualVersionDiffResponse:
    """FR-14: 최신/임의 버전 간 Diff."""

    try:
        return await service.diff_versions(
            manual_group_id,
            base_version=base_version,
            compare_version=compare_version,
            summarize=summarize,
        )
    except RecordNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ValidationError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
```

**변경 코드:**
```python
@router.get(
    "/{manual_id}/diff",
    response_model=ManualVersionDiffResponse,
    summary="Diff manual versions in the same group",
)
async def diff_manual_versions(
    manual_id: UUID,  # ✅ 변경: str → UUID
    base_version: str | None = None,
    compare_version: str | None = None,
    summarize: bool = False,
    service: ManualService = Depends(get_manual_service),
) -> ManualVersionDiffResponse:
    """
    FR-14: 같은 그룹의 메뉴얼 버전 간 Diff

    변경사항 (2025-12-11):
    - 경로: /{manual_group_id}/diff → /{manual_id}/diff
    - 파라미터 타입: str → UUID (명확성)
    - manual_id로부터 자동으로 그룹 정보 추출

    매개변수:
    - manual_id: 메뉴얼 ID (그룹 정보 추출용)
    - base_version: 기준 버전 (예: "1", "2") (선택)
    - compare_version: 비교 버전 (예: "2", "3") (선택)
    - summarize: LLM 요약 포함 여부 (선택)

    응답:
    - base_version: 기준 버전 (또는 null)
    - compare_version: 비교 버전
    - added_entries: 추가된 메뉴얼
    - removed_entries: 제거된 메뉴얼
    - modified_entries: 수정된 메뉴얼
    - llm_summary: LLM 요약 (optional)

    예시:
    GET /manuals/550e8400-e29b-41d4-a716-446655440000/diff
      → 최신 vs 직전 버전 비교

    GET /manuals/550e8400-e29b-41d4-a716-446655440000/diff?base_version=1&compare_version=2
      → v1 vs v2 비교

    GET /manuals/550e8400-e29b-41d4-a716-446655440000/diff?base_version=1&summarize=true
      → v1 vs 최신 버전, LLM 요약 포함
    """

    try:
        return await service.diff_versions(
            manual_id,  # ✅ 변경: manual_group_id → manual_id
            base_version=base_version,
            compare_version=compare_version,
            summarize=summarize,
        )
    except RecordNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ValidationError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
```

**변경 요점:**
- ✅ 경로: `/{manual_group_id}/diff` → `/{manual_id}/diff`
- ✅ 파라미터: `str` → `UUID` (타입 명확화)
- ✅ 상세한 docstring 추가 (사용 예시 포함)

---

### 2.6 검증 쿼리 (Phase 2 완료 후)

**실행:** Phase 2 배포 후 다음 시나리오 검증

```python
# 테스트 시나리오
import asyncio
from httpx import AsyncClient

async def test_phase2():
    client = AsyncClient(base_url="http://localhost:8000")

    # 1. 메뉴얼 생성 (그룹 A)
    response = await client.post(
        "/manuals/draft",
        json={
            "consultation_id": "...",
            "enforce_hallucination_check": False,
        }
    )
    manual_a_id = response.json()["id"]
    print(f"Manual A created: {manual_a_id}")

    # 2. 메뉴얼 승인
    response = await client.post(
        f"/manuals/approve/{manual_a_id}",
        json={"approver_id": "reviewer1"}
    )
    version_a_1 = response.json()["version"]
    print(f"Manual A approved: v{version_a_1}")  # → "1"

    # 3. 메뉴얼 수정 및 재승인
    response = await client.put(
        f"/manuals/{manual_a_id}",
        json={"topic": "수정된 주제"}
    )
    # 상태: DRAFT 유지

    response = await client.post(
        f"/manuals/approve/{manual_a_id}",
        json={"approver_id": "reviewer1"}
    )
    version_a_2 = response.json()["version"]
    print(f"Manual A updated version: v{version_a_2}")  # → "2"

    # 4. 다른 그룹의 메뉴얼 생성 및 승인
    response = await client.post(
        "/manuals/draft",
        json={
            "consultation_id": "...",  # 다른 그룹 (업무코드B, 에러코드Y)
            "enforce_hallucination_check": False,
        }
    )
    manual_b_id = response.json()["id"]
    response = await client.post(
        f"/manuals/approve/{manual_b_id}",
        json={"approver_id": "reviewer1"}
    )
    version_b_1 = response.json()["version"]
    print(f"Manual B approved: v{version_b_1}")  # → "1" (그룹 B의 v1)

    # 5. 버전 목록 확인
    response = await client.get(f"/manuals/{manual_a_id}/versions")
    versions_a = response.json()
    print(f"Manual A versions: {[v['value'] for v in versions_a]}")
    # → ["2", "1"] (그룹 A의 버전만)

    response = await client.get(f"/manuals/{manual_b_id}/versions")
    versions_b = response.json()
    print(f"Manual B versions: {[v['value'] for v in versions_b]}")
    # → ["1"] (그룹 B의 버전만)

    # 6. Diff 확인
    response = await client.get(f"/manuals/{manual_a_id}/diff")
    diff = response.json()
    print(f"Diff A (v2 vs v1): {diff['base_version']} -> {diff['compare_version']}")
    # → "1" -> "2"

asyncio.run(test_phase2())
```

---

## Phase 3: 테스트 + 마이그레이션

### 예상 시간: 1.5시간
### 영향도: 낮음 (검증 및 기록)
### 주의: Phase 1, 2가 모두 배포된 후에만 시작

---

### 3.1 마이그레이션 파일 생성

**명령어:**
```bash
cd /home/hauam/workspace/k-helpdesk-wiki

# 1. 마이그레이션 파일 자동 생성
uv run alembic revision --autogenerate -m "Add business_type and error_code to ManualVersion, change unique constraint"

# 2. 생성된 파일 확인 (예: alembic/versions/20251211_XXXX_add_group_fields.py)
ls -la alembic/versions/ | tail -5
```

**파일 검토:**
```bash
# 마이그레이션 파일 내용 확인
cat alembic/versions/20251211_*_add_group_fields.py
```

**파일 수정 (필요시):**

생성된 파일을 다음과 같이 검토:

```python
# alembic/versions/20251211_XXXX_add_group_fields_to_manual_version.py

"""Add business_type and error_code to ManualVersion, change unique constraint."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '[auto-generated]'
down_revision = '[previous-revision]'
branch_labels = None
depends_on = None

def upgrade() -> None:
    # 1. 기존 UNIQUE 제약 제거
    op.drop_constraint(
        'manual_versions_version_key',  # ← Alembic이 자동 생성한 이름
        'manual_versions',
        type_='unique'
    )

    # 2. 새 컬럼 추가
    op.add_column(
        'manual_versions',
        sa.Column(
            'business_type',
            sa.String(50),
            nullable=True,
            comment='업무구분 (그룹 식별용)'
        )
    )
    op.add_column(
        'manual_versions',
        sa.Column(
            'error_code',
            sa.String(50),
            nullable=True,
            comment='에러코드 (그룹 식별용)'
        )
    )

    # 3. 인덱스 생성
    op.create_index(
        'ix_manual_versions_business_type',
        'manual_versions',
        ['business_type']
    )
    op.create_index(
        'ix_manual_versions_error_code',
        'manual_versions',
        ['error_code']
    )

    # 4. 새로운 UNIQUE 제약 생성
    op.create_unique_constraint(
        'uq_manual_version_group',
        'manual_versions',
        ['business_type', 'error_code', 'version']
    )

def downgrade() -> None:
    # 역순으로 제거
    op.drop_constraint(
        'uq_manual_version_group',
        'manual_versions',
        type_='unique'
    )

    op.drop_index(
        'ix_manual_versions_error_code',
        table_name='manual_versions'
    )
    op.drop_index(
        'ix_manual_versions_business_type',
        table_name='manual_versions'
    )

    op.drop_column('manual_versions', 'error_code')
    op.drop_column('manual_versions', 'business_type')

    op.create_unique_constraint(
        'manual_versions_version_key',
        'manual_versions',
        ['version']
    )
```

---

### 3.2 테스트 작성

**파일:** `tests/unit/test_manual_version_group_management.py`

**새 파일 생성:**

```python
"""
테스트: 메뉴얼 그룹별 독립적 버전 관리

변경사항 (2025-12-11):
- Repository가 business_type, error_code로 필터링하는지 확인
- Service가 그룹별 버전을 생성하는지 확인
- 동시 승인 시 버전이 겹치지 않는지 확인
"""

import pytest
import asyncio
from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession
from app.models.manual import ManualEntry, ManualStatus, ManualVersion
from app.models.task import ManualReviewTask
from app.repositories.manual_rdb import (
    ManualVersionRepository,
    ManualEntryRDBRepository,
)
from app.services.manual_service import ManualService
from app.schemas.manual import ManualApproveRequest
from app.llm.mock import MockLLMClient
from app.vectorstore.mock import MockVectorStore


# ===== T1: Repository - 그룹별 독립적 버전 =====
@pytest.mark.asyncio
async def test_repo_manual_version_unique_constraint_per_group(session: AsyncSession):
    """
    T1: 같은 버전 번호가 다른 그룹에 존재할 수 있는지 확인

    예:
    - v1 (그룹 A: 인터넷뱅킹::ERR_LOGIN_001)
    - v1 (그룹 B: 모바일뱅킹::ERR_OTP_002)
    (둘 다 유효함)
    """
    repo = ManualVersionRepository(session)

    # 그룹 A의 v1
    version_a = ManualVersion(
        version="1",
        business_type="인터넷뱅킹",
        error_code="ERR_LOGIN_001",
    )
    session.add(version_a)
    await session.flush()

    # 그룹 B의 v1 (같은 버전 번호이지만 다른 그룹)
    version_b = ManualVersion(
        version="1",
        business_type="모바일뱅킹",
        error_code="ERR_OTP_002",
    )
    session.add(version_b)
    await session.flush()

    # 검증
    assert version_a.version == version_b.version == "1"
    assert version_a.id != version_b.id
    print("✅ T1 passed: 같은 버전 번호, 다른 그룹에서 유효")


# ===== T2: Repository - 그룹 필터링 =====
@pytest.mark.asyncio
async def test_repo_get_latest_version_with_group_filter(session: AsyncSession):
    """
    T2: get_latest_version()이 그룹별로 정확히 필터링하는지 확인

    시나리오:
    - 그룹 A: v1 (created_at: 2025-01-01), v2 (created_at: 2025-01-02)
    - 그룹 B: v1 (created_at: 2025-01-03)

    예상:
    - 그룹 A의 최신 = v2
    - 그룹 B의 최신 = v1
    """
    repo = ManualVersionRepository(session)
    from datetime import datetime

    # 그룹 A의 v1, v2
    version_a1 = ManualVersion(
        version="1",
        business_type="인터넷뱅킹",
        error_code="ERR_LOGIN_001",
    )
    version_a2 = ManualVersion(
        version="2",
        business_type="인터넷뱅킹",
        error_code="ERR_LOGIN_001",
    )
    session.add_all([version_a1, version_a2])
    await session.flush()

    # 그룹 B의 v1
    version_b1 = ManualVersion(
        version="1",
        business_type="모바일뱅킹",
        error_code="ERR_OTP_002",
    )
    session.add(version_b1)
    await session.flush()

    # 검증: 그룹 A의 최신은 v2
    latest_a = await repo.get_latest_version(
        business_type="인터넷뱅킹",
        error_code="ERR_LOGIN_001",
    )
    assert latest_a.version == "2"
    assert latest_a.id == version_a2.id
    print("✅ T2.1 passed: 그룹 A의 최신 = v2")

    # 검증: 그룹 B의 최신은 v1
    latest_b = await repo.get_latest_version(
        business_type="모바일뱅킹",
        error_code="ERR_OTP_002",
    )
    assert latest_b.version == "1"
    assert latest_b.id == version_b1.id
    print("✅ T2.2 passed: 그룹 B의 최신 = v1")


# ===== T3: Service - 승인 시 버전 할당 =====
@pytest.mark.asyncio
async def test_service_approve_manual_assigns_group_version(session: AsyncSession):
    """
    T3: 메뉴얼 승인 시 올바른 그룹별 버전이 할당되는지 확인

    시나리오:
    1. 그룹 A의 메뉴얼 생성 (DRAFT)
    2. 그룹 A의 메뉴얼 승인
    3. 그룹 B의 메뉴얼 생성 (DRAFT)
    4. 그룹 B의 메뉴얼 승인

    예상:
    - 그룹 A: v1 할당
    - 그룹 B: v1 할당 (독립적)
    """
    manual_repo = ManualEntryRDBRepository(session)
    version_repo = ManualVersionRepository(session)

    service = ManualService(
        session=session,
        llm_client=MockLLMClient(),
        vectorstore=MockVectorStore(),
        manual_repo=manual_repo,
        version_repo=version_repo,
    )

    # 그룹 A의 메뉴얼 생성
    consultation_id_a = uuid4()
    manual_a = ManualEntry(
        topic="로그인 오류",
        keywords=["로그인", "오류"],
        background="배경",
        guideline="가이드",
        business_type="인터넷뱅킹",
        error_code="ERR_LOGIN_001",
        source_consultation_id=consultation_id_a,
        status=ManualStatus.DRAFT,
    )
    session.add(manual_a)
    await session.flush()

    # 그룹 A 메뉴얼 승인
    result_a = await service.approve_manual(
        manual_a.id,
        ManualApproveRequest(approver_id="reviewer1"),
    )
    assert result_a.version == "1"
    print("✅ T3.1 passed: 그룹 A 메뉴얼 승인, v1 할당")

    # 그룹 B의 메뉴얼 생성
    consultation_id_b = uuid4()
    manual_b = ManualEntry(
        topic="OTP 오류",
        keywords=["OTP", "인증"],
        background="배경",
        guideline="가이드",
        business_type="모바일뱅킹",
        error_code="ERR_OTP_002",
        source_consultation_id=consultation_id_b,
        status=ManualStatus.DRAFT,
    )
    session.add(manual_b)
    await session.flush()

    # 그룹 B 메뉴얼 승인
    result_b = await service.approve_manual(
        manual_b.id,
        ManualApproveRequest(approver_id="reviewer1"),
    )
    assert result_b.version == "1"  # 그룹 B의 v1 (독립적)
    print("✅ T3.2 passed: 그룹 B 메뉴얼 승인, v1 할당 (독립적)")


# ===== T4: Service - 다중 그룹 동시 승인 =====
@pytest.mark.asyncio
async def test_service_concurrent_approval_multiple_groups(session: AsyncSession):
    """
    T4: 여러 그룹의 메뉴얼을 동시에 승인해도 버전 충돌이 없는지 확인

    시나리오:
    1. 그룹 A, B의 메뉴얼 2개 생성
    2. 동시에 승인
    3. 버전 번호 확인

    예상:
    - 그룹 A: v1
    - 그룹 B: v1 (동시 승인이지만 다른 그룹이므로 충돌 없음)
    """
    manual_repo = ManualEntryRDBRepository(session)
    version_repo = ManualVersionRepository(session)

    service = ManualService(
        session=session,
        llm_client=MockLLMClient(),
        vectorstore=MockVectorStore(),
        manual_repo=manual_repo,
        version_repo=version_repo,
    )

    # 메뉴얼 2개 생성 (다른 그룹)
    manual_a = ManualEntry(
        topic="로그인 오류",
        keywords=["로그인"],
        background="배경",
        guideline="가이드",
        business_type="인터넷뱅킹",
        error_code="ERR_LOGIN_001",
        source_consultation_id=uuid4(),
        status=ManualStatus.DRAFT,
    )
    manual_b = ManualEntry(
        topic="OTP 오류",
        keywords=["OTP"],
        background="배경",
        guideline="가이드",
        business_type="모바일뱅킹",
        error_code="ERR_OTP_002",
        source_consultation_id=uuid4(),
        status=ManualStatus.DRAFT,
    )
    session.add_all([manual_a, manual_b])
    await session.flush()

    # 동시 승인
    results = await asyncio.gather(
        service.approve_manual(
            manual_a.id,
            ManualApproveRequest(approver_id="reviewer1"),
        ),
        service.approve_manual(
            manual_b.id,
            ManualApproveRequest(approver_id="reviewer1"),
        ),
    )

    # 검증: 둘 다 v1
    assert results[0].version == "1"
    assert results[1].version == "1"
    print("✅ T4 passed: 동시 승인, 각각 v1 (충돌 없음)")


# ===== T5: Service - 버전 목록 조회 =====
@pytest.mark.asyncio
async def test_service_list_versions_returns_group_versions_only(session: AsyncSession):
    """
    T5: list_versions()가 해당 그룹의 버전만 반환하는지 확인

    시나리오:
    - 그룹 A: v1, v2, v3 (3개)
    - 그룹 B: v1, v2 (2개)

    예상:
    - 그룹 A 조회 시: [v3, v2, v1] (3개)
    - 그룹 B 조회 시: [v2, v1] (2개)
    """
    manual_repo = ManualEntryRDBRepository(session)
    version_repo = ManualVersionRepository(session)

    service = ManualService(
        session=session,
        llm_client=MockLLMClient(),
        vectorstore=MockVectorStore(),
        manual_repo=manual_repo,
        version_repo=version_repo,
    )

    # 그룹 A: 메뉴얼 생성 및 3번 승인 (v1, v2, v3)
    manual_a = ManualEntry(
        topic="로그인 오류",
        keywords=["로그인"],
        background="배경",
        guideline="가이드",
        business_type="인터넷뱅킹",
        error_code="ERR_LOGIN_001",
        source_consultation_id=uuid4(),
        status=ManualStatus.DRAFT,
    )
    session.add(manual_a)
    await session.flush()

    for i in range(3):
        await service.approve_manual(
            manual_a.id,
            ManualApproveRequest(approver_id="reviewer1"),
        )
        if i < 2:
            # 다시 DRAFT 상태로 (테스트용)
            manual_a.status = ManualStatus.DRAFT
            await session.flush()

    # 그룹 B: 메뉴얼 생성 및 2번 승인 (v1, v2)
    manual_b = ManualEntry(
        topic="OTP 오류",
        keywords=["OTP"],
        background="배경",
        guideline="가이드",
        business_type="모바일뱅킹",
        error_code="ERR_OTP_002",
        source_consultation_id=uuid4(),
        status=ManualStatus.DRAFT,
    )
    session.add(manual_b)
    await session.flush()

    for i in range(2):
        await service.approve_manual(
            manual_b.id,
            ManualApproveRequest(approver_id="reviewer1"),
        )
        if i < 1:
            manual_b.status = ManualStatus.DRAFT
            await session.flush()

    # 검증: 그룹 A는 3개 버전
    versions_a = await service.list_versions(manual_a.id)
    assert len(versions_a) == 3
    assert [v["value"] for v in versions_a] == ["3", "2", "1"]
    print("✅ T5.1 passed: 그룹 A, 3개 버전 반환")

    # 검증: 그룹 B는 2개 버전
    versions_b = await service.list_versions(manual_b.id)
    assert len(versions_b) == 2
    assert [v["value"] for v in versions_b] == ["2", "1"]
    print("✅ T5.2 passed: 그룹 B, 2개 버전 반환")
```

**실행:**
```bash
# 개별 테스트 실행
uv run pytest tests/unit/test_manual_version_group_management.py::test_repo_manual_version_unique_constraint_per_group -v
uv run pytest tests/unit/test_manual_version_group_management.py::test_repo_get_latest_version_with_group_filter -v
uv run pytest tests/unit/test_manual_version_group_management.py::test_service_approve_manual_assigns_group_version -v
uv run pytest tests/unit/test_manual_version_group_management.py::test_service_concurrent_approval_multiple_groups -v
uv run pytest tests/unit/test_manual_version_group_management.py::test_service_list_versions_returns_group_versions_only -v

# 전체 테스트
uv run pytest tests/unit/test_manual_version_group_management.py -v
```

---

### 3.3 마이그레이션 적용

**단계별 실행:**

```bash
# 1. 마이그레이션 파일 확인
cd /home/hauam/workspace/k-helpdesk-wiki
ls -la alembic/versions/ | grep "20251211"

# 2. 현재 리비전 확인
uv run alembic current

# 3. 마이그레이션 Dry-run (실제 적용 전 확인)
uv run alembic upgrade --sql head | tail -50

# 4. 실제 마이그레이션 적용
uv run alembic upgrade head

# 5. 적용 후 확인
uv run alembic current

# 6. 데이터베이스 스키마 확인
# PostgreSQL에 접속하여:
# \d manual_versions;
# SELECT * FROM pg_indexes WHERE tablename = 'manual_versions';
```

---

## 검증 및 롤백

### 3.4 마이그레이션 검증

**체크리스트:**

```bash
# 1. 테이블 구조 확인
echo "SELECT column_name, data_type FROM information_schema.columns WHERE table_name = 'manual_versions' ORDER BY ordinal_position;" | psql khw

# 예상:
# column_name   |           data_type
# id            | uuid
# created_at    | timestamp without time zone
# updated_at    | timestamp without time zone
# version       | character varying
# description   | text
# changelog     | jsonb
# business_type | character varying           ← 신규
# error_code    | character varying           ← 신규

# 2. 유니크 제약 확인
echo "SELECT constraint_name FROM information_schema.table_constraints WHERE table_name = 'manual_versions' AND constraint_type = 'UNIQUE';" | psql khw

# 예상:
# uq_manual_version_group

# 3. 인덱스 확인
echo "SELECT indexname FROM pg_indexes WHERE tablename = 'manual_versions' ORDER BY indexname;" | psql khw

# 예상:
# ix_manual_versions_business_type
# ix_manual_versions_error_code
# manual_versions_pkey
```

---

### 3.5 롤백 계획

**상황:** 마이그레이션 후 문제 발생

```bash
# 1. 즉시 이전 리비전으로 롤백
uv run alembic downgrade -1

# 2. 리비전 확인
uv run alembic current

# 3. 테이블 구조 복원 확인
echo "\d manual_versions;" | psql khw
# version이 UNIQUE 제약만 있어야 함

# 4. 필요시 코드도 롤백
git revert [commit-hash]

# 5. 애플리케이션 재시작
# Phase 1 적용 전 상태로 돌아옴
```

---

## 최종 체크리스트

### Phase 1 완료 기준
- [ ] ManualVersion 모델 수정 완료
- [ ] ManualVersionRepository 메소드 3개 수정 완료
- [ ] mypy 타입 체크 통과 (`uv run mypy app/`)
- [ ] 마이그레이션 파일 검토 완료
- [ ] 마이그레이션 적용 완료
- [ ] DB 스키마 검증 완료
- [ ] 기존 테스트 통과 확인

### Phase 2 완료 기준
- [ ] ManualService.approve_manual() 수정 완료
- [ ] ManualService.list_versions() 수정 완료
- [ ] ManualService._resolve_versions_for_diff() 수정 완료
- [ ] ManualService.diff_versions() 수정 완료
- [ ] API 라우트 수정 완료
- [ ] 모든 파일 mypy 체크 통과
- [ ] 통합 테스트 실행 (test_phase2() 함수)

### Phase 3 완료 기준
- [ ] 테스트 파일 생성 완료 (T1~T5)
- [ ] 모든 테스트 통과 (`uv run pytest tests/unit/test_manual_version_group_management.py -v`)
- [ ] 롤백 계획 검증 완료
- [ ] 마이그레이션 파일 최종 리뷰 완료
- [ ] 기술 문서 업데이트 (BACKEND_API_GUIDE.md 등)

---

## 예상 일정 (재정의)

| Phase | 작업 | 예상 시간 | 담당 |
|-------|------|---------|------|
| 1 | 모델 + Repository | 1.5시간 | 개발자 |
| 2 | Service + API | 2시간 | 개발자 |
| 3 | 테스트 + 마이그레이션 | 1.5시간 | 개발자 |
| **합계** | | **5시간** | |

---

## 다음 단계

1. **Phase 1 시작**
   - [ ] 이 문서의 1.1 ~ 1.2 섹션 따라하기
   - [ ] 1.3 검증 쿼리 실행
   - [ ] GitHub에 PR 생성 (제목: "Phase 1: 메뉴얼 버전 모델/레포지토리 그룹화")

2. **Phase 1 리뷰 완료 후**
   - [ ] Phase 2 시작 (2.1 ~ 2.6)
   - [ ] GitHub에 PR 생성 (제목: "Phase 2: 메뉴얼 버전 서비스/API 그룹화")

3. **Phase 2 리뷰 완료 후**
   - [ ] Phase 3 시작 (3.1 ~ 3.5)
   - [ ] GitHub에 PR 생성 (제목: "Phase 3: 메뉴얼 버전 테스트/마이그레이션")

---

**작성자:** Claude Code
**최종 검토일:** 2025-12-11
**상태:** 🟢 즉시 구현 가능
