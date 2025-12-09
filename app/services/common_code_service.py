"""
FR-15: 공통코드 서비스 (Service Layer)

비즈니스 로직: 공통코드 그룹/항목의 CRUD, 검색, 중복 확인 등
FastAPI 독립적 - Service는 순수 Python 타입만 다룸
MCP 서버에서도 직접 호출 가능
"""

import math
from typing import Optional
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession
from structlog import get_logger

from app.core.exceptions import (
    RecordNotFoundError,
    DuplicateRecordError,
    ValidationError,
)
from app.models.common_code import CommonCodeGroup, CommonCodeItem
from app.repositories.common_code_rdb import (
    CommonCodeGroupRepository,
    CommonCodeItemRepository,
)
from app.schemas.common_code import (
    CommonCodeGroupCreate,
    CommonCodeGroupUpdate,
    CommonCodeGroupResponse,
    CommonCodeGroupDetailResponse,
    CommonCodeItemCreate,
    CommonCodeItemUpdate,
    CommonCodeItemResponse,
    CommonCodeGroupListResponse,
    CommonCodeItemListResponse,
    CommonCodeGroupSimpleResponse,
    CommonCodeSimpleResponse,
    BulkCommonCodeResponse,
)

logger = get_logger(__name__)


class CommonCodeService:
    """
    공통코드 관리 서비스
    - 그룹 및 항목의 CRUD
    - 검색 및 조회
    - 중복 확인
    - 캐싱 (옵션)
    """

    def __init__(self, session: AsyncSession):
        """
        서비스 초기화

        Args:
            session: AsyncSession (데이터베이스 세션)
        """
        self.session = session
        self.group_repo = CommonCodeGroupRepository(session)
        self.item_repo = CommonCodeItemRepository(session)
        logger.debug("CommonCodeService initialized")

    # ==================== Group Management ====================

    async def create_group(self, payload: CommonCodeGroupCreate) -> CommonCodeGroupResponse:
        """
        공통코드 그룹 생성

        Args:
            payload: 그룹 생성 요청 데이터

        Returns:
            생성된 그룹 응답

        Raises:
            DuplicateRecordError: 같은 그룹 코드가 이미 존재
            ValidationError: 입력 데이터 검증 실패
        """
        # 그룹 코드 중복 확인
        existing = await self.group_repo.get_by_group_code(payload.group_code)
        if existing:
            raise DuplicateRecordError(
                f"CommonCodeGroup with code '{payload.group_code}' already exists"
            )

        # 그룹 생성
        group = CommonCodeGroup(
            group_code=payload.group_code,
            group_name=payload.group_name,
            description=payload.description,
            is_active=payload.is_active,
        )

        group = await self.group_repo.create(group)
        await self.session.commit()

        logger.info(
            "common_code_group_created",
            group_id=str(group.id),
            group_code=group.group_code,
        )

        return CommonCodeGroupResponse.model_validate(group)

    async def get_group(self, group_id: UUID) -> CommonCodeGroupResponse:
        """
        ID로 그룹 조회

        Args:
            group_id: 그룹 ID

        Returns:
            그룹 응답

        Raises:
            RecordNotFoundError: 그룹을 찾을 수 없음
        """
        group = await self.group_repo.get_by_id(group_id)
        if not group:
            raise RecordNotFoundError(f"CommonCodeGroup with id {group_id} not found")

        return CommonCodeGroupResponse.model_validate(group)

    async def get_group_by_code(self, group_code: str) -> CommonCodeGroupResponse:
        """
        그룹 코드로 그룹 조회

        Args:
            group_code: 그룹 코드 (예: BUSINESS_TYPE)

        Returns:
            그룹 응답

        Raises:
            RecordNotFoundError: 그룹을 찾을 수 없음
        """
        group = await self.group_repo.get_by_group_code(group_code)
        if not group:
            raise RecordNotFoundError(
                f"CommonCodeGroup with code '{group_code}' not found"
            )

        return CommonCodeGroupResponse.model_validate(group)

    async def get_group_with_items(self, group_code: str) -> CommonCodeGroupDetailResponse:
        """
        그룹 코드로 그룹과 하위 항목 함께 조회

        Args:
            group_code: 그룹 코드

        Returns:
            항목이 포함된 그룹 상세 응답

        Raises:
            RecordNotFoundError: 그룹을 찾을 수 없음
        """
        group = await self.group_repo.get_by_group_code_with_items(group_code)
        if not group:
            raise RecordNotFoundError(
                f"CommonCodeGroup with code '{group_code}' not found"
            )

        return CommonCodeGroupDetailResponse.model_validate(group)

    async def list_groups(
        self, page: int = 1, page_size: int = 20, is_active: Optional[bool] = None
    ) -> CommonCodeGroupListResponse:
        """
        그룹 목록 조회 (페이징)

        Args:
            page: 페이지 번호 (1부터 시작)
            page_size: 페이지 크기
            is_active: 활성화 필터 (None이면 모두)

        Returns:
            그룹 목록 응답
        """
        # 전체 개수 조회
        if is_active is None:
            total = await self.group_repo.count()
        else:
            total = await self.group_repo.count_active_groups() if is_active else 0
            if not is_active:
                # 비활성 그룹 개수는 전체 - 활성
                total = await self.group_repo.count()
                total = total - await self.group_repo.count_active_groups()

        total_pages = math.ceil(total / page_size) if page_size > 0 else 1

        # 오프셋 계산
        offset = (page - 1) * page_size

        # 그룹 조회
        if is_active is None:
            groups = await self.group_repo.get_all(limit=page_size, offset=offset)
        elif is_active:
            groups = await self.group_repo.get_active_groups(limit=page_size, offset=offset)
        else:
            # 비활성 그룹만 조회 (별도 쿼리 필요)
            from sqlalchemy import select

            stmt = (
                select(CommonCodeGroup)
                .where(CommonCodeGroup.is_active is False)
                .order_by(CommonCodeGroup.created_at.desc())
                .limit(page_size)
                .offset(offset)
            )
            result = await self.session.execute(stmt)
            groups = result.scalars().all()

        items = [CommonCodeGroupResponse.model_validate(g) for g in groups]

        return CommonCodeGroupListResponse(
            items=items,
            total=total,
            page=page,
            page_size=page_size,
            total_pages=total_pages,
        )

    async def search_groups(
        self, keyword: str, page: int = 1, page_size: int = 20
    ) -> CommonCodeGroupListResponse:
        """
        그룹 검색 (이름 또는 코드)

        Args:
            keyword: 검색 키워드
            page: 페이지 번호
            page_size: 페이지 크기

        Returns:
            검색된 그룹 목록 응답
        """
        offset = (page - 1) * page_size

        # 먼저 검색 결과 개수 조회
        from sqlalchemy import select, and_, func

        conditions = [
            (CommonCodeGroup.group_code.ilike(f"%{keyword}%"))
            | (CommonCodeGroup.group_name.ilike(f"%{keyword}%"))
        ]
        count_stmt = (
            select(func.count()).select_from(CommonCodeGroup).where(and_(*conditions))
        )
        count_result = await self.session.execute(count_stmt)
        total = count_result.scalars().first() or 0

        # 검색 수행
        groups = await self.group_repo.search_groups(
            keyword, limit=page_size, offset=offset
        )

        items = [CommonCodeGroupResponse.model_validate(g) for g in groups]
        total_pages = math.ceil(total / page_size) if page_size > 0 else 1

        return CommonCodeGroupListResponse(
            items=items,
            total=total,
            page=page,
            page_size=page_size,
            total_pages=total_pages,
        )

    async def update_group(
        self, group_id: UUID, payload: CommonCodeGroupUpdate
    ) -> CommonCodeGroupResponse:
        """
        그룹 수정

        Args:
            group_id: 그룹 ID
            payload: 수정 데이터

        Returns:
            수정된 그룹 응답

        Raises:
            RecordNotFoundError: 그룹을 찾을 수 없음
            DuplicateRecordError: 새 그룹 코드가 이미 존재
        """
        group = await self.group_repo.get_by_id(group_id)
        if not group:
            raise RecordNotFoundError(f"CommonCodeGroup with id {group_id} not found")

        # 그룹 코드 변경 시 중복 확인
        if payload.group_code and payload.group_code != group.group_code:
            existing = await self.group_repo.get_by_group_code(payload.group_code)
            if existing:
                raise DuplicateRecordError(
                    f"CommonCodeGroup with code '{payload.group_code}' already exists"
                )
            group.group_code = payload.group_code

        # 필드 업데이트
        if payload.group_name:
            group.group_name = payload.group_name
        if payload.description is not None:
            group.description = payload.description
        if payload.is_active is not None:
            group.is_active = payload.is_active

        group = await self.group_repo.update(group)
        await self.session.commit()

        logger.info(
            "common_code_group_updated",
            group_id=str(group.id),
            group_code=group.group_code,
        )

        return CommonCodeGroupResponse.model_validate(group)

    async def delete_group(self, group_id: UUID) -> None:
        """
        그룹 삭제 (하위 항목도 함께 삭제 - CASCADE)

        Args:
            group_id: 그룹 ID

        Raises:
            RecordNotFoundError: 그룹을 찾을 수 없음
        """
        group = await self.group_repo.get_by_id(group_id)
        if not group:
            raise RecordNotFoundError(f"CommonCodeGroup with id {group_id} not found")

        # 먼저 모든 항목 삭제 (ORM cascade delete 문제 회피)
        deleted_items = await self.item_repo.delete_by_group_id(group_id)
        logger.info(
            "common_code_items_deleted",
            group_id=str(group_id),
            deleted_count=deleted_items,
        )

        # Raw SQL로 그룹 삭제 (ORM delete 문제 회피)
        from sqlalchemy import text

        sql = "DELETE FROM common_code_groups WHERE id = :group_id"
        params = {"group_id": str(group_id)}
        result = await self.session.execute(text(sql), params)
        await self.session.commit()

        logger.info(
            "common_code_group_deleted",
            group_id=str(group.id),
            group_code=group.group_code,
            deleted_rows=result.rowcount,
        )

    # ==================== Item Management ====================

    async def create_item(
        self, group_id: UUID, payload: CommonCodeItemCreate
    ) -> CommonCodeItemResponse:
        """
        항목 생성

        Args:
            group_id: 상위 그룹 ID
            payload: 항목 생성 요청 데이터

        Returns:
            생성된 항목 응답

        Raises:
            RecordNotFoundError: 그룹을 찾을 수 없음
            DuplicateRecordError: 같은 코드 키가 이미 존재
        """
        # 그룹 존재 확인
        group = await self.group_repo.get_by_id(group_id)
        if not group:
            raise RecordNotFoundError(f"CommonCodeGroup with id {group_id} not found")

        # 코드 키 중복 확인
        existing = await self.item_repo.get_by_code_key(group_id, payload.code_key)
        if existing:
            raise DuplicateRecordError(
                f"CommonCodeItem with key '{payload.code_key}' already exists in this group"
            )

        # 항목 생성 (group_id는 VARCHAR(36) 문자열로 저장)
        item = CommonCodeItem(
            group_id=str(group_id),
            code_key=payload.code_key,
            code_value=payload.code_value,
            sort_order=payload.sort_order,
            is_active=payload.is_active,
            attributes=payload.attributes or {},
        )

        item = await self.item_repo.create(item)
        await self.session.commit()

        logger.info(
            "common_code_item_created",
            item_id=str(item.id),
            group_id=str(group_id),
            code_key=item.code_key,
        )

        return CommonCodeItemResponse.model_validate(item)

    async def get_item(self, item_id: UUID) -> CommonCodeItemResponse:
        """
        ID로 항목 조회

        Args:
            item_id: 항목 ID

        Returns:
            항목 응답

        Raises:
            RecordNotFoundError: 항목을 찾을 수 없음
        """
        item = await self.item_repo.get_by_id_or_raise(item_id)
        return CommonCodeItemResponse.model_validate(item)

    async def list_items_by_group(
        self,
        group_id: UUID,
        page: int = 1,
        page_size: int = 100,
        is_active_only: bool = False,
    ) -> CommonCodeItemListResponse:
        """
        그룹의 항목 목록 조회

        Args:
            group_id: 그룹 ID
            page: 페이지 번호
            page_size: 페이지 크기
            is_active_only: True면 활성 항목만

        Returns:
            항목 목록 응답

        Raises:
            RecordNotFoundError: 그룹을 찾을 수 없음
        """
        # 그룹 존재 확인
        group = await self.group_repo.get_by_id(group_id)
        if not group:
            raise RecordNotFoundError(f"CommonCodeGroup with id {group_id} not found")

        offset = (page - 1) * page_size

        # 전체 개수
        total = await self.item_repo.count_by_group_id(group_id)

        # 항목 조회
        items = await self.item_repo.get_by_group_id(
            group_id,
            is_active_only=is_active_only,
            order_by_sort=True,
        )

        # 페이징 적용
        paginated_items = items[offset : offset + page_size]

        responses = [CommonCodeItemResponse.model_validate(i) for i in paginated_items]
        total_pages = math.ceil(total / page_size) if page_size > 0 else 1

        return CommonCodeItemListResponse(
            items=responses,
            total=total,
            page=page,
            page_size=page_size,
            total_pages=total_pages,
        )

    async def update_item(
        self, item_id: UUID, payload: CommonCodeItemUpdate
    ) -> CommonCodeItemResponse:
        """
        항목 수정

        Args:
            item_id: 항목 ID
            payload: 수정 데이터

        Returns:
            수정된 항목 응답

        Raises:
            RecordNotFoundError: 항목을 찾을 수 없음
            DuplicateRecordError: 새 코드 키가 이미 존재
        """
        item = await self.item_repo.get_by_id_or_raise(item_id)

        # 코드 키 변경 시 중복 확인
        if payload.code_key and payload.code_key != item.code_key:
            is_duplicate = await self.item_repo.check_duplicate_code_key(
                item.group_id, payload.code_key, exclude_id=item_id
            )
            if is_duplicate:
                raise DuplicateRecordError(
                    f"CommonCodeItem with key '{payload.code_key}' already exists in this group"
                )
            item.code_key = payload.code_key

        # 필드 업데이트
        if payload.code_value:
            item.code_value = payload.code_value
        if payload.sort_order is not None:
            item.sort_order = payload.sort_order
        if payload.is_active is not None:
            item.is_active = payload.is_active
        if payload.attributes is not None:
            item.attributes = payload.attributes

        item = await self.item_repo.update(item)
        await self.session.commit()

        logger.info(
            "common_code_item_updated",
            item_id=str(item.id),
            code_key=item.code_key,
        )

        return CommonCodeItemResponse.model_validate(item)

    async def delete_item(self, item_id: UUID) -> None:
        """
        항목 삭제

        Args:
            item_id: 항목 ID

        Raises:
            RecordNotFoundError: 항목을 찾을 수 없음
        """
        # 항목 존재 확인
        item = await self.item_repo.get_by_id_or_raise(item_id)

        # Raw SQL로 삭제 (ORM delete 문제 회피)
        from sqlalchemy import text

        sql = "DELETE FROM common_code_items WHERE id = :item_id"
        params = {"item_id": str(item_id)}
        result = await self.session.execute(text(sql), params)
        await self.session.commit()

        logger.info(
            "common_code_item_deleted",
            item_id=str(item.id),
            code_key=item.code_key,
            deleted_rows=result.rowcount,
        )

    # ==================== Public Search (Frontend API) ====================

    async def get_codes_by_group_code(
        self, group_code: str, is_active_only: bool = True
    ) -> CommonCodeGroupSimpleResponse:
        """
        그룹 코드로 공통코드 항목 조회 (프론트엔드용)

        Args:
            group_code: 그룹 코드 (예: BUSINESS_TYPE)
            is_active_only: True면 활성 항목만 조회

        Returns:
            축약된 그룹 응답 (id, timestamp 미포함)
            데이터가 없으면 빈 items 배열과 함께 반환
        """
        logger.info(
            "get_codes_by_group_code_start",
            group_code=group_code,
            is_active_only=is_active_only,
        )

        items = await self.item_repo.get_by_group_code(
            group_code, is_active_only=is_active_only
        )

        logger.info(
            "get_codes_by_group_code_result",
            group_code=group_code,
            item_count=len(items) if items else 0,
            items=str(items) if items else "empty",
        )

        # 데이터가 없어도 200 OK with empty items 반환
        return CommonCodeGroupSimpleResponse(
            group_code=group_code,
            items=[
                CommonCodeSimpleResponse(code_key=item.code_key, code_value=item.code_value)
                for item in items
            ] if items else []
        )

    async def get_multiple_code_groups(
        self, group_codes: list[str], is_active_only: bool = True
    ) -> BulkCommonCodeResponse:
        """
        여러 그룹의 공통코드 일괄 조회 (프론트엔드용)

        Args:
            group_codes: 그룹 코드 리스트 (예: ["BUSINESS_TYPE", "ERROR_CODE"])
            is_active_only: True면 활성 항목만 조회

        Returns:
            여러 그룹의 공통코드 응답

        Raises:
            RecordNotFoundError: 일부 그룹을 찾을 수 없음
        """
        result = {}

        for group_code in group_codes:
            try:
                group_response = await self.get_codes_by_group_code(
                    group_code, is_active_only=is_active_only
                )
                result[group_code] = group_response
            except RecordNotFoundError:
                # 그룹이 없으면 빈 항목으로 처리
                result[group_code] = CommonCodeGroupSimpleResponse(
                    group_code=group_code,
                    items=[],
                )

        return BulkCommonCodeResponse(data=result)
