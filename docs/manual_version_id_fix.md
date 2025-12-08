# Manual version_id 관리 및 list_versions() 필터링 고정

## 문제 분석

사용자 이슈: `list_versions()` API가 특정 메뉴얼 그룹의 버전만 반환해야 하는데, DB에서 관계를 확인했더니 `manual_entries`와 `manual_versions` 사이에 제대로 된 필터링이 없어서 모든 시스템 버전이 반환되었음.

### 핵심 문제점

1. **version_id 설정 시점**
   - DRAFT 메뉴얼: `version_id = NULL` (승인 전이므로 버전 미정)
   - APPROVED 메뉴얼: `approve_manual()` 호출 시 새 버전 생성 후 `version_id` 할당
   - DEPRECATED 메뉴얼: 이전 승인된 버전의 `version_id` 유지

2. **list_versions() 구현의 결함**
   - `find_by_business_and_error()`를 호출할 때 **모든 상태의 메뉴얼**을 조회
   - DRAFT 메뉴얼의 `version_id`는 NULL이므로 실제 버전 조회 시 제외됨
   - 하지만 불필요한 데이터 처리로 인한 비효율

## 해결 방법

### 1. Repository 레벨 개선

`find_by_business_and_error()` 메서드에 **status 필터링** 추가:

```python
async def find_by_business_and_error(
    self,
    business_type: str | None,
    error_code: str | None,
    *,
    statuses: set[ManualStatus] | None = None,  # ← 새로 추가
) -> Sequence[ManualEntry]:
    """
    같은 business_type/error_code를 가진 메뉴얼들 조회 (선택적 status 필터링)
    """
    stmt = select(ManualEntry).where(
        ManualEntry.business_type == business_type,
        ManualEntry.error_code == error_code,
    )
    if statuses:
        stmt = stmt.where(ManualEntry.status.in_(list(statuses)))
    result = await self.session.execute(stmt)
    return result.scalars().all()
```

### 2. Service 레벨 개선

`list_versions()` 호출 시 **APPROVED/DEPRECATED만 명시적으로 조회**:

```python
async def list_versions(self, manual_id: UUID) -> list[ManualVersionResponse]:
    """특정 메뉴얼 그룹의 버전 목록 조회"""

    manual = await self.manual_repo.get_by_id(manual_id)
    if manual is None:
        raise RecordNotFoundError(...)

    # ✅ APPROVED/DEPRECATED 메뉴얼만 조회 (DRAFT 제외)
    group_entries = list(
        await self.manual_repo.find_by_business_and_error(
            business_type=manual.business_type,
            error_code=manual.error_code,
            statuses={ManualStatus.APPROVED, ManualStatus.DEPRECATED},  # ← 핵심 변경
        )
    )

    # 버전 ID 추출 및 정렬
    version_ids = {e.version_id for e in group_entries if e.version_id}
    all_versions = await self.version_repo.list_versions()
    group_versions = [v for v in all_versions if v.id in version_ids]

    # 응답 생성
    ...
```

## version_id 생명주기

```
DRAFT 메뉴얼 생성 (create_draft_from_consultation)
    ↓
version_id = NULL  ← 버전이 정해지지 않음
    ↓
메뉴얼 승인 (approve_manual)
    ↓
새 ManualVersion 생성
    ↓
manual.version_id = new_version.id  ← 버전 할당
    ↓
APPROVED 메뉴얼로 변경
    ↓
VectorStore에 인덱싱
```

### approve_manual() 구현

```python
async def approve_manual(
    self,
    manual_id: UUID,
    request: ManualApproveRequest,
) -> ManualVersionInfo:
    """FR-4/FR-5: 메뉴얼 승인 및 전체 버전 세트 갱신"""

    manual = await self.manual_repo.get_by_id(manual_id)

    # 새 버전 생성
    latest_version = await self.version_repo.get_latest_version()
    next_version_num = self._next_version_number(latest_version)
    next_version = ManualVersion(version=str(next_version_num))
    await self.version_repo.create(next_version)

    # 이전 버전의 같은 그룹 메뉴얼들을 DEPRECATED 처리
    await self._deprecate_previous_entries(manual)

    # 현재 메뉴얼에 버전 할당 및 승인
    manual.status = ManualStatus.APPROVED
    manual.version_id = next_version.id  # ← 핵심: 여기서 설정됨
    await self.manual_repo.update(manual)

    # VectorStore에 인덱싱
    await self._index_manual_vector(manual)

    return ManualVersionInfo(
        version=next_version.version,
        approved_at=next_version.created_at,
    )
```

## 테스트 시나리오

### 시나리오 1: DRAFT 메뉴얼은 버전 목록에 포함되지 않음

```python
# 같은 그룹: business_type="인터넷뱅킹", error_code="E001"
draft_manual.status = DRAFT
draft_manual.version_id = None

approved_manual.status = APPROVED
approved_manual.version_id = version_v2_1.id

# list_versions() 호출
result = await service.list_versions(draft_manual.id)

# 결과: DRAFT는 조회 대상에서 제외되고, APPROVED의 버전만 반환
assert len(result) == 1
assert result[0].value == "v2.1"
```

### 시나리오 2: 서로 다른 그룹의 메뉴얼은 버전이 격리됨

```python
# 그룹 1: business_type="인터넷뱅킹", error_code="E001"
group1_manual.version_id = version_v2_1.id

# 그룹 2: business_type="모바일뱅킹", error_code="E002"
group2_manual.version_id = version_v1_0.id

# 그룹 1의 버전 조회
result = await service.list_versions(group1_manual.id)

# 결과: 그룹 1의 버전(v2.1)만 반환
assert len(result) == 1
assert result[0].value == "v2.1"
```

## 변경 사항 요약

| 파일 | 변경 내용 |
|------|---------|
| `app/repositories/manual_rdb.py` | `find_by_business_and_error()`에 `statuses` 필터링 파라미터 추가 |
| `app/services/manual_service.py` | `list_versions()` 호출 시 명시적으로 `APPROVED/DEPRECATED` 필터링 추가 |
| `tests/unit/test_manual_version_api.py` | 2개의 새로운 테스트 케이스 추가 (DRAFT 제외, 그룹 격리) |

## 테스트 결과

```
✅ 14/14 tests passed
- test_parse_guideline_string_with_pairs
- test_parse_guideline_string_empty
- test_parse_guideline_string_with_extra_whitespace
- test_list_versions_success
- test_list_versions_empty
- test_list_versions_single_version
- test_list_versions_date_format
- test_get_manual_by_version_success
- test_get_manual_by_version_guideline_parsing
- test_get_manual_by_version_version_not_found
- test_get_manual_by_version_no_approved_entries
- test_get_manual_by_version_response_format
- test_list_versions_excludes_draft_entries ✨ NEW
- test_list_versions_multiple_groups_isolated ✨ NEW
```

## 결론

이제 `list_versions()` API는:
1. ✅ 특정 메뉴얼 그룹(business_type + error_code)의 버전만 반환
2. ✅ DRAFT 메뉴얼은 자동으로 제외 (version_id = NULL이므로)
3. ✅ APPROVED/DEPRECATED 상태의 메뉴얼만 조회하여 명시적이고 효율적
4. ✅ 서로 다른 그룹의 버전이 격리되어 데이터 무결성 보장
