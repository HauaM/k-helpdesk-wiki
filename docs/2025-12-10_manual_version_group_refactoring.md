# 메뉴얼 버전 관리 개선: 그룹별 독립적 버전 관리 (옵션 A)

**문서 작성일:** 2025-12-10
**우선순위:** P0 (즉시 처리 필요)
**예상 작업량:** 2-3일 (1개 스프린트)

---

## 📋 목차

1. [현황 분석](#현황-분석)
2. [구현 계획](#구현-계획)
3. [상세 구현 단계](#상세-구현-단계)
4. [코드 변경사항](#코드-변경사항)
5. [테스트 계획](#테스트-계획)
6. [마이그레이션](#마이그레이션)
7. [롤백 계획](#롤백-계획)

---

## 현황 분석

### 문제점

**현재 구현:**
```python
# app/services/manual_service.py:353
latest_version = await self.version_repo.get_latest_version()  # ← 전역 최신 버전
next_version_num = self._next_version_number(latest_version)
next_version = ManualVersion(version=str(next_version_num))
```

**결과:**
```
메뉴얼_A (업무코드A::에러코드X) 승인 → v1
메뉴얼_A' (업무코드A::에러코드X) 승인 → v2
메뉴얼_B (업무코드B::에러코드Y) 승인 → v3 ← 잘못된 버전!
                                      (B의 v1이어야 함)
```

**현재 테이블 구조:**
```sql
-- manual_versions
CREATE TABLE manual_versions (
    id UUID PRIMARY KEY,
    version VARCHAR(50) UNIQUE NOT NULL,  -- "1", "2", "3", ...
    description TEXT,
    changelog JSONB,
    created_at TIMESTAMP,
    updated_at TIMESTAMP
);

-- manual_entries
CREATE TABLE manual_entries (
    id UUID PRIMARY KEY,
    version_id UUID REFERENCES manual_versions(id),
    business_type VARCHAR(50),
    error_code VARCHAR(50),
    -- ...
);
```

**문제:** version이 전역 유일 (UNIQUE), 그룹 정보 없음

---

## 구현 계획

### 목표

✅ 각 메뉴얼 그룹(업무코드 + 에러코드)이 **독립적인 버전 번호** 유지
✅ 버전 조회 시 자동으로 그룹별 필터링
✅ 기존 API 호환성 유지
✅ 데이터 무결성 보장

### 변경 범위

| 컴포넌트 | 변경 | 영향도 |
|---------|------|--------|
| 데이터베이스 스키마 | 컬럼 추가 + 제약 변경 | 높음 |
| ManualVersion 모델 | 필드 추가 | 중간 |
| ManualVersionRepository | 메소드 수정 | 중간 |
| ManualService | 승인 로직 수정 | 높음 |
| 마이그레이션 | 신규 생성 | 필수 |

---

## 상세 구현 단계

### Phase 1: 모델 변경 (1시간)

#### 1.1 ManualVersion 모델 수정

**파일:** `app/models/manual.py`

**현재 코드:**
```python
class ManualVersion(BaseModel):
    __tablename__ = "manual_versions"

    version: Mapped[str] = mapped_column(String(50), nullable=False, unique=True)
    description: Mapped[str | None] = mapped_column(Text)
    changelog: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
```

**변경 코드:**
```python
from sqlalchemy import UniqueConstraint

class ManualVersion(BaseModel):
    """
    FR-5: 메뉴얼 버전 관리 (그룹별 독립적)

    변경사항:
    - business_type, error_code 필드 추가 (메뉴얼 그룹 식별)
    - 유니크 제약을 (business_type, error_code, version)으로 변경
    - 같은 그룹 내에서만 version이 유일
    """

    __tablename__ = "manual_versions"

    # 메뉴얼 그룹 정보
    business_type: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
        index=True,
        comment="업무구분 (그룹 식별용)",
    )
    error_code: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
        index=True,
        comment="에러코드 (그룹 식별용)",
    )

    # 버전 정보
    version: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        comment="버전 번호 (그룹 내에서 유일)",
    )
    description: Mapped[str | None] = mapped_column(Text)
    changelog: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    # 유니크 제약: (business_type, error_code, version) 조합
    __table_args__ = (
        UniqueConstraint(
            "business_type",
            "error_code",
            "version",
            name="uq_manual_version_group",
        ),
    )

    def __repr__(self) -> str:
        return (
            f"<ManualVersion("
            f"id={self.id}, "
            f"group={self.business_type}::{self.error_code}, "
            f"version={self.version}"
            f")>"
        )
```

**변경 요점:**
- ✅ `business_type`, `error_code` 추가
- ✅ `unique=True` 제거 (version에서)
- ✅ `UniqueConstraint` 추가 (3개 컬럼 조합)
- ✅ 주석 명확화

---

### Phase 2: Repository 변경 (1시간)

#### 2.1 ManualVersionRepository 메소드 수정

**파일:** `app/repositories/manual_rdb.py`

**현재 코드:**
```python
class ManualVersionRepository(BaseRepository[ManualVersion]):
    def __init__(self, session: AsyncSession):
        super().__init__(ManualVersion, session)

    async def get_latest_version(self) -> ManualVersion | None:
        """최신 버전 조회 (전역)"""
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
            business_type: 업무코드 (필터링)
            error_code: 에러코드 (필터링)

        Returns:
            해당 그룹의 최신 버전 또는 None

        예시:
            # 인터넷뱅킹::ERR_LOGIN_001 그룹의 최신 버전
            v = await repo.get_latest_version(
                business_type="인터넷뱅킹",
                error_code="ERR_LOGIN_001",
            )
        """
        stmt = select(ManualVersion)

        # 그룹 필터링
        if business_type is not None:
            stmt = stmt.where(ManualVersion.business_type == business_type)
        if error_code is not None:
            stmt = stmt.where(ManualVersion.error_code == error_code)

        # 최신순 정렬 및 제한
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
            version: 버전 번호 (예: "1", "2")
            business_type: 업무코드 (선택, 더 정확한 검색)
            error_code: 에러코드 (선택, 더 정확한 검색)

        Returns:
            해당 버전 또는 None
        """
        stmt = select(ManualVersion).where(ManualVersion.version == version)

        # 그룹 필터링 (있으면)
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
            business_type: 업무코드 (필터링)
            error_code: 에러코드 (필터링)
            limit: 최대 결과 수

        Returns:
            버전 목록 (최신순)
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
- ✅ `get_latest_version()`: business_type, error_code 파라미터 추가
- ✅ `get_by_version()`: 그룹 필터링 옵션 추가
- ✅ `list_versions()`: 그룹 필터링 옵션 추가
- ✅ 상세한 docstring

---

### Phase 3: Service 변경 (2시간)

#### 3.1 ManualService.approve_manual() 수정

**파일:** `app/services/manual_service.py`

**현재 코드 (331-369):**
```python
async def approve_manual(
    self,
    manual_id: UUID,
    request: ManualApproveRequest,
) -> ManualVersionInfo:
    """FR-4/FR-5: 메뉴얼 승인 및 전체 버전 세트 갱신."""

    manual = await self.manual_repo.get_by_id(manual_id)
    if manual is None:
        raise RecordNotFoundError(f"ManualEntry(id={manual_id}) not found")

    logger.info(
        "manual_approve_start",
        manual_id=str(manual_id),
        approver_id=str(request.approver_id),
    )

    # ❌ 문제: 전역 최신 버전
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

    변경사항:
    - 그룹별(business_type + error_code) 독립적인 버전 관리
    - 같은 그룹의 최신 버전만 조회
    - 버전 번호는 그룹 내에서만 유일

    워크플로우:
    1. 메뉴얼 조회
    2. 같은 그룹의 최신 버전 조회
    3. 신규 버전 생성 (해당 그룹용)
    4. 기존 APPROVED 메뉴얼 DEPRECATED 처리
    5. 신규 메뉴얼 APPROVED 상태로 변경
    6. VectorStore 인덱싱
    """

    manual = await self.manual_repo.get_by_id(manual_id)
    if manual is None:
        raise RecordNotFoundError(f"ManualEntry(id={manual_id}) not found")

    logger.info(
        "manual_approve_start",
        manual_id=str(manual_id),
        approver_id=str(request.approver_id),
        business_type=manual.business_type,
        error_code=manual.error_code,
    )

    # ✅ 변경: 같은 그룹의 최신 버전 조회
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

#### 3.2 ManualService.list_versions() 수정

**파일:** `app/services/manual_service.py` (371-441)

**현재 코드:**
```python
async def list_versions(self, manual_id: UUID) -> list[ManualVersionResponse]:
    """FR-14: 특정 메뉴얼 그룹의 버전 목록 조회 (최신순, 현재 버전 표시 포함)."""

    # 1. 기준 메뉴얼 조회
    manual = await self.manual_repo.get_by_id(manual_id)

    # 2. 같은 그룹의 APPROVED/DEPRECATED 메뉴얼만 조회
    group_entries = list(
        await self.manual_repo.find_by_business_and_error(
            business_type=manual.business_type,
            error_code=manual.error_code,
            statuses={ManualStatus.APPROVED, ManualStatus.DEPRECATED},
        )
    )

    # 3. 그룹 메뉴얼들의 버전 ID 추출
    version_ids = set()
    for entry in group_entries:
        if entry.version_id is not None:
            version_ids.add(entry.version_id)

    # 4. 버전 정보 조회 (수동으로)
    all_versions = await self.version_repo.list_versions()
    group_versions = [v for v in all_versions if v.id in version_ids]
```

**변경 코드:**
```python
async def list_versions(self, manual_id: UUID) -> list[ManualVersionResponse]:
    """
    FR-14: 특정 메뉴얼 그룹의 버전 목록 조회 (최신순, 현재 버전 표시 포함)

    변경사항:
    - Repository의 그룹 필터링 활용 (수동 필터링 제거)
    - 그룹별 버전만 조회하므로 효율성 개선
    """

    # 1. 기준 메뉴얼 조회
    manual = await self.manual_repo.get_by_id(manual_id)
    if manual is None:
        raise RecordNotFoundError(f"ManualEntry(id={manual_id}) not found")

    # ✅ 변경: 그룹 필터링을 Repository에 위임
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
- ✅ 쿼리 간소화 및 효율성 개선
- ✅ 이전 코드보다 가독성 향상

---

#### 3.3 ManualService.diff_versions() 수정

**파일:** `app/services/manual_service.py` (458-510)

**현재 코드:**
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
```

**문제:** manual_group_id 사용 안 함 (파라미터로는 받지만 사용하지 않음)

**변경 코드:**
```python
async def diff_versions(
    self,
    manual_id: UUID,  # ← manual_group_id 대신 manual_id
    *,
    base_version: str | None,
    compare_version: str | None,
    summarize: bool = False,
) -> ManualVersionDiffResponse:
    """
    FR-14 시나리오 A/B: 버전 간 Diff (그룹별)

    변경사항:
    - manual_id를 기준으로 그룹 정보 추출
    - 해당 그룹의 버전만 비교
    """

    # 기준 메뉴얼 조회 (그룹 정보 추출용)
    manual = await self.manual_repo.get_by_id(manual_id)
    if manual is None:
        raise RecordNotFoundError(f"ManualEntry(id={manual_id}) not found")

    base, compare = await self._resolve_versions_for_diff(
        business_type=manual.business_type,
        error_code=manual.error_code,
        base_version=base_version,
        compare_version=compare_version,
    )
    # ... (나머지는 동일)
```

**변경 메소드:**
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
    Diff 시나리오별 base/compare 버전 결정

    변경사항:
    - 그룹 필터링 파라미터 추가
    """

    if compare_version and base_version is None:
        raise ValidationError("compare_version을 사용할 때는 base_version을 함께 지정하세요.")

    if base_version and compare_version:
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
            raise RecordNotFoundError(f"Base version {base_version} not found")
        if compare is None:
            raise RecordNotFoundError(f"Compare version {compare_version} not found")
        return base, compare

    if base_version and compare_version is None:
        base = await self.version_repo.get_by_version(
            base_version,
            business_type=business_type,
            error_code=error_code,
        )
        if base is None:
            raise RecordNotFoundError(f"Base version {base_version} not found")

        # ✅ 같은 그룹의 최신 버전
        latest = await self.version_repo.get_latest_version(
            business_type=business_type,
            error_code=error_code,
        )
        if latest is None:
            raise RecordNotFoundError("비교할 최신 버전이 없습니다.")
        if latest.id == base.id:
            # 같은 버전이면 이전 버전과 비교
            versions = await self.version_repo.list_versions(
                business_type=business_type,
                error_code=error_code,
                limit=2,
            )
            if len(versions) < 2:
                raise ValidationError("동일 버전을 비교할 수 없습니다. 다른 버전을 지정하세요.")
            return versions[1], versions[0]
        return base, latest

    # base_version도 없으면 최신 2개 버전
    versions = await self.version_repo.list_versions(
        business_type=business_type,
        error_code=error_code,
        limit=2,
    )
    if len(versions) < 2:
        raise ValidationError("최신/직전 비교를 위해 최소 2개 버전이 필요합니다.")
    return versions[1], versions[0]
```

---

### Phase 4: API 라우트 변경 (30분)

#### 4.1 app/routers/manuals.py 수정

**파일:** `app/routers/manuals.py` (153-177)

**현재 코드:**
```python
@router.get(
    "/{manual_group_id}/diff",
    response_model=ManualVersionDiffResponse,
    summary="Diff manual versions",
)
async def diff_manual_versions(
    manual_group_id: str,  # ← str (불명확)
    base_version: str | None = None,
    compare_version: str | None = None,
    summarize: bool = False,
    service: ManualService = Depends(get_manual_service),
) -> ManualVersionDiffResponse:
```

**변경 코드:**
```python
@router.get(
    "/{manual_id}/diff",
    response_model=ManualVersionDiffResponse,
    summary="Diff manual versions in the same group",
)
async def diff_manual_versions(
    manual_id: UUID,  # ← UUID (명확)
    base_version: str | None = None,
    compare_version: str | None = None,
    summarize: bool = False,
    service: ManualService = Depends(get_manual_service),
) -> ManualVersionDiffResponse:
    """
    FR-14: 같은 그룹의 메뉴얼 버전 간 Diff

    매개변수:
    - manual_id: 메뉴얼 ID (그룹 정보 추출용)
    - base_version: 기준 버전 (선택)
    - compare_version: 비교 버전 (선택)
    - summarize: LLM 요약 포함 여부

    동작:
    1. manual_id로부터 그룹(business_type, error_code) 정보 추출
    2. 해당 그룹의 버전만 비교
    3. Diff 결과 반환
    """

    try:
        return await service.diff_versions(
            manual_id,
            base_version=base_version,
            compare_version=compare_version,
            summarize=summarize,
        )
    except RecordNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ValidationError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
```

---

## 코드 변경사항

### 파일별 변경 요약

| 파일 | 변경 내용 | 라인 | 영향도 |
|------|---------|------|--------|
| `app/models/manual.py` | ManualVersion 필드/제약 추가 | 106-124 | 높음 |
| `app/repositories/manual_rdb.py` | get_latest_version/get_by_version/list_versions 수정 | 전체 | 높음 |
| `app/services/manual_service.py` | approve_manual/list_versions/_resolve_versions_for_diff 수정 | 331, 371, 813 | 높음 |
| `app/routers/manuals.py` | diff_manual_versions 파라미터 변경 | 153-177 | 중간 |

---

## 테스트 계획

### Unit 테스트

#### T1. 그룹별 독립적 버전

```python
@pytest.mark.asyncio
async def test_manual_version_group_independence():
    """같은 버전 번호가 다른 그룹에 존재 가능"""

    # 그룹 A의 v1
    group_a_v1 = ManualVersion(
        version="1",
        business_type="인터넷뱅킹",
        error_code="ERR_LOGIN_001",
    )

    # 그룹 B의 v1 (동일한 버전 번호)
    group_b_v1 = ManualVersion(
        version="1",
        business_type="모바일뱅킹",
        error_code="ERR_OTP_002",
    )

    # 둘 다 DB에 저장 가능 (유니크 제약 통과)
    await session.add(group_a_v1)
    await session.add(group_b_v1)
    await session.commit()

    assert group_a_v1.version == group_b_v1.version
    assert group_a_v1.id != group_b_v1.id
```

#### T2. Repository 필터링

```python
@pytest.mark.asyncio
async def test_get_latest_version_with_group_filter():
    """get_latest_version()이 그룹별로 정확히 필터링"""

    # 그룹 A: v1, v2, v3
    # 그룹 B: v1, v2
    # 그룹 C: v1

    # 그룹 B의 최신 = v2
    latest_b = await repo.get_latest_version(
        business_type="모바일뱅킹",
        error_code="ERR_OTP_002",
    )

    assert latest_b.version == "2"
    assert latest_b.business_type == "모바일뱅킹"
    assert latest_b.error_code == "ERR_OTP_002"
```

#### T3. 승인 시 버전 할당

```python
@pytest.mark.asyncio
async def test_approve_manual_assigns_group_version():
    """메뉴얼 승인 시 올바른 버전 할당"""

    # 그룹 A의 v1 이미 존재
    existing_v1 = ManualVersion(
        version="1",
        business_type="인터넷뱅킹",
        error_code="ERR_LOGIN_001",
    )
    await session.add(existing_v1)
    await session.commit()

    # 그룹 A의 신규 메뉴얼 승인
    manual = ManualEntry(
        topic="로그인 오류 (수정)",
        keywords=["로그인", "오류"],
        background="수정된 배경",
        guideline="수정된 가이드",
        business_type="인터넷뱅킹",
        error_code="ERR_LOGIN_001",
        source_consultation_id=...,
        status=ManualStatus.DRAFT,
    )
    await session.add(manual)
    await session.commit()

    # 승인
    await service.approve_manual(
        manual.id,
        ManualApproveRequest(approver_id="reviewer1"),
    )

    # 검증
    updated_manual = await repo.get_by_id(manual.id)

    # v2 생성 및 할당
    assert updated_manual.version_id is not None
    version = await session.get(ManualVersion, updated_manual.version_id)
    assert version.version == "2"
    assert version.business_type == "인터넷뱅킹"
    assert version.error_code == "ERR_LOGIN_001"
```

### Integration 테스트

#### T4. 다중 그룹 동시 승인

```python
@pytest.mark.asyncio
async def test_multiple_groups_concurrent_approval():
    """여러 그룹의 메뉴얼을 동시에 승인해도 버전 충돌 없음"""

    # 그룹 A와 B의 메뉴얼 2개 준비
    manual_a = ManualEntry(
        business_type="인터넷뱅킹",
        error_code="ERR_LOGIN_001",
        status=ManualStatus.DRAFT,
        source_consultation_id=...,
    )
    manual_b = ManualEntry(
        business_type="모바일뱅킹",
        error_code="ERR_OTP_002",
        status=ManualStatus.DRAFT,
        source_consultation_id=...,
    )

    # 동시 승인
    results = await asyncio.gather(
        service.approve_manual(manual_a.id, ManualApproveRequest(...)),
        service.approve_manual(manual_b.id, ManualApproveRequest(...)),
    )

    # 검증: 버전 번호가 겹치지 않음
    version_a = await session.get(ManualVersion, results[0].version_id)
    version_b = await session.get(ManualVersion, results[1].version_id)

    # 둘 다 v1이어야 함 (각각의 그룹에서)
    assert version_a.version == "1"
    assert version_b.version == "1"
    assert version_a.id != version_b.id
```

#### T5. 버전 목록 조회

```python
@pytest.mark.asyncio
async def test_list_versions_returns_group_versions_only():
    """list_versions()는 해당 그룹의 버전만 반환"""

    # 그룹 A: v1, v2, v3
    # 그룹 B: v1, v2
    # 그룹 C: v1

    manual_a = ManualEntry(business_type="A", error_code="X")
    versions = await service.list_versions(manual_a.id)

    # 그룹 A의 v1, v2, v3만 반환 (3개)
    assert len(versions) == 3
    assert all(v["value"] in ["1", "2", "3"] for v in versions)
```

---

## 마이그레이션

### M1. 데이터베이스 마이그레이션 생성

```bash
uv run alembic revision --autogenerate -m "Add business_type and error_code to ManualVersion, change unique constraint"
```

### M2. 마이그레이션 파일 (생성됨)

**파일:** `alembic/versions/[timestamp]_add_group_fields_to_manual_version.py`

```python
"""Add business_type and error_code to ManualVersion, change unique constraint."""

from alembic import op
import sqlalchemy as sa

revision = "[auto-generated-hash]"
down_revision = "[previous-revision]"
branch_labels = None
depends_on = None

def upgrade() -> None:
    # 1. 임시로 unique 제약 제거
    op.drop_constraint(
        "manual_versions_version_key",
        "manual_versions",
        type_="unique",
    )

    # 2. 새 컬럼 추가
    op.add_column(
        "manual_versions",
        sa.Column(
            "business_type",
            sa.String(50),
            nullable=True,
            comment="업무구분 (그룹 식별용)",
        ),
    )
    op.add_column(
        "manual_versions",
        sa.Column(
            "error_code",
            sa.String(50),
            nullable=True,
            comment="에러코드 (그룹 식별용)",
        ),
    )

    # 3. 인덱스 생성
    op.create_index(
        "ix_manual_versions_business_type",
        "manual_versions",
        ["business_type"],
    )
    op.create_index(
        "ix_manual_versions_error_code",
        "manual_versions",
        ["error_code"],
    )

    # 4. 새로운 유니크 제약 생성 (3개 컬럼)
    op.create_unique_constraint(
        "uq_manual_version_group",
        "manual_versions",
        ["business_type", "error_code", "version"],
    )

def downgrade() -> None:
    # 역순으로 제거
    op.drop_constraint(
        "uq_manual_version_group",
        "manual_versions",
        type_="unique",
    )

    op.drop_index(
        "ix_manual_versions_error_code",
        "manual_versions",
    )
    op.drop_index(
        "ix_manual_versions_business_type",
        "manual_versions",
    )

    op.drop_column("manual_versions", "error_code")
    op.drop_column("manual_versions", "business_type")

    op.create_unique_constraint(
        "manual_versions_version_key",
        "manual_versions",
        ["version"],
    )
```

### M3. 마이그레이션 적용

```bash
# 적용
uv run alembic upgrade head

# 확인
uv run alembic current

# 롤백 (필요 시)
uv run alembic downgrade -1
```

---

## 롤백 계획

### 롤백 시나리오

**상황:** 마이그레이션 후 문제 발생

**단계별 롤백:**

1. **데이터베이스 롤백**
   ```bash
   uv run alembic downgrade -1
   ```

2. **코드 롤백**
   ```bash
   git revert [commit-hash]
   ```

3. **테스트**
   ```bash
   uv run pytest tests/
   ```

### 롤백 체크리스트

- [ ] 마이그레이션 롤백 성공
- [ ] 테이블 구조 확인 (version UNIQUE만 있는지)
- [ ] 코드 변경 제거됨 확인
- [ ] 기존 테스트 통과 확인

---

## 구현 체크리스트

### Phase 1: 모델 (1시간)
- [ ] ManualVersion 모델 수정
- [ ] mypy 타입 체크
- [ ] 모델 테스트 작성

### Phase 2: Repository (1시간)
- [ ] ManualVersionRepository 메소드 수정
- [ ] 단위 테스트 작성 (T1, T2)
- [ ] 통합 테스트 작성

### Phase 3: Service (2시간)
- [ ] approve_manual() 수정
- [ ] list_versions() 수정
- [ ] diff_versions() 및 헬퍼 메소드 수정
- [ ] 통합 테스트 작성 (T4, T5)

### Phase 4: API (30분)
- [ ] 라우트 파라미터 변경
- [ ] API 문서 갱신
- [ ] E2E 테스트

### Phase 5: 마이그레이션 (30분)
- [ ] 마이그레이션 파일 검토
- [ ] dry-run 실행
- [ ] 실제 적용

### Phase 6: 테스트 (1시간)
- [ ] 모든 테스트 통과 확인
- [ ] 기존 기능 회귀 테스트
- [ ] 성능 테스트

### Phase 7: 문서 (30분)
- [ ] README 갱신
- [ ] MANUAL_WORKFLOW_AND_VERSIONING.md 수정
- [ ] 개발자 가이드 업데이트

---

## 예상 일정

| Phase | 작업 | 예상 시간 | 담당 |
|-------|------|---------|------|
| 1 | 모델 변경 | 1시간 | 개발자 |
| 2 | Repository 변경 | 1시간 | 개발자 |
| 3 | Service 변경 | 2시간 | 개발자 |
| 4 | API 변경 | 30분 | 개발자 |
| 5 | 마이그레이션 | 30분 | DBA/개발자 |
| 6 | 테스트 | 1시간 | QA/개발자 |
| 7 | 문서 | 30분 | 개발자 |
| **합계** | | **6.5시간** | |

---

## 위험 요소 및 대응

| 위험 | 영향 | 대응 |
|------|------|------|
| 마이그레이션 실패 | 데이터 손상 | dry-run 먼저 실행 |
| 기존 데이터 호환성 | 쿼리 오류 | 롤백 계획 준비 |
| 동시성 문제 | 데이터 불일치 | 동시성 테스트 추가 |
| API 호환성 | 클라이언트 오류 | 문서 명확화 |

---

## 성공 기준

✅ 각 메뉴얼 그룹이 독립적인 버전 번호 유지
✅ 모든 테스트 통과 (Unit + Integration)
✅ 기존 API 호환성 유지
✅ 데이터 무결성 보장
✅ 마이그레이션 성공 및 롤백 가능

---

## 참고 자료

- 현재 문제 분석: [docs/MANUAL_WORKFLOW_ISSUES_AND_IMPROVEMENTS.md](MANUAL_WORKFLOW_ISSUES_AND_IMPROVEMENTS.md)
- 워크플로우 이해: [docs/MANUAL_WORKFLOW_AND_VERSIONING.md](MANUAL_WORKFLOW_AND_VERSIONING.md)
- 코드 위치:
  - 모델: [app/models/manual.py:106](../app/models/manual.py#L106)
  - Repository: [app/repositories/manual_rdb.py](../app/repositories/manual_rdb.py)
  - Service: [app/services/manual_service.py:331](../app/services/manual_service.py#L331)
  - API: [app/routers/manuals.py:153](../app/routers/manuals.py#L153)

---

**작성자:** Claude Code
**최종 검토:** 2025-12-10
**상태:** 🟢 준비 완료
