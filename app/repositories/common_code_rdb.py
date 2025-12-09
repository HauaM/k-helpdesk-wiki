"""
FR-15: 공통코드 저장소 (Repository)

CommonCodeGroup과 CommonCodeItem의 데이터 접근 계층을 담당
"""

from typing import Sequence
from uuid import UUID

from sqlalchemy import select, and_, func, cast as sql_cast
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from structlog import get_logger

from app.core.exceptions import RecordNotFoundError, DuplicateRecordError
from app.models.common_code import CommonCodeGroup, CommonCodeItem
from app.repositories.base import BaseRepository

logger = get_logger(__name__)


class CommonCodeGroupRepository(BaseRepository[CommonCodeGroup]):
    """
    CommonCodeGroup CRUD 및 조회 기능
    """

    def __init__(self, session: AsyncSession):
        super().__init__(CommonCodeGroup, session)

    async def get_by_group_code(self, group_code: str) -> CommonCodeGroup | None:
        """
        그룹 코드로 그룹 조회

        Args:
            group_code: 그룹 코드 (예: BUSINESS_TYPE)

        Returns:
            CommonCodeGroup 또는 None
        """
        stmt = select(CommonCodeGroup).where(
            CommonCodeGroup.group_code == group_code
        )
        result = await self.session.execute(stmt)
        return result.scalars().first()

    async def get_by_group_code_with_items(self, group_code: str) -> CommonCodeGroup | None:
        """
        그룹 코드로 그룹과 하위 항목들 함께 조회

        Args:
            group_code: 그룹 코드

        Returns:
            항목들이 로드된 CommonCodeGroup 또는 None
        """
        stmt = (
            select(CommonCodeGroup)
            .options(selectinload(CommonCodeGroup.items))
            .where(CommonCodeGroup.group_code == group_code)
        )
        result = await self.session.execute(stmt)
        return result.scalars().first()

    async def get_active_groups(self, limit: int = 100, offset: int = 0) -> Sequence[CommonCodeGroup]:
        """
        활성 그룹 목록 조회

        Args:
            limit: 조회 제한 수
            offset: 건너뛸 레코드 수

        Returns:
            활성 CommonCodeGroup 리스트
        """
        stmt = (
            select(CommonCodeGroup)
            .where(CommonCodeGroup.is_active is True)
            .order_by(CommonCodeGroup.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def search_groups(
        self, keyword: str, is_active: bool | None = None, limit: int = 100, offset: int = 0
    ) -> Sequence[CommonCodeGroup]:
        """
        그룹 검색 (이름 또는 코드)

        Args:
            keyword: 검색 키워드
            is_active: 활성화 필터 (None이면 모두)
            limit: 조회 제한 수
            offset: 건너뛸 레코드 수

        Returns:
            검색된 CommonCodeGroup 리스트
        """
        conditions = [
            (CommonCodeGroup.group_code.ilike(f"%{keyword}%"))
            | (CommonCodeGroup.group_name.ilike(f"%{keyword}%"))
        ]

        if is_active is not None:
            conditions.append(CommonCodeGroup.is_active is is_active)

        stmt = (
            select(CommonCodeGroup)
            .where(and_(*conditions))
            .order_by(CommonCodeGroup.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def count_active_groups(self) -> int:
        """
        활성 그룹 총 개수

        Returns:
            활성 그룹 수
        """
        stmt = select(func.count()).select_from(CommonCodeGroup).where(
            CommonCodeGroup.is_active is True
        )
        result = await self.session.execute(stmt)
        return result.scalars().first() or 0


class CommonCodeItemRepository(BaseRepository[CommonCodeItem]):
    """
    CommonCodeItem CRUD 및 조회 기능
    """

    def __init__(self, session: AsyncSession):
        super().__init__(CommonCodeItem, session)

    async def get_by_group_id(
        self, group_id: UUID, is_active_only: bool = False, order_by_sort: bool = True
    ) -> Sequence[CommonCodeItem]:
        """
        특정 그룹의 모든 항목 조회

        Args:
            group_id: 그룹 ID
            is_active_only: True면 활성 항목만 조회
            order_by_sort: True면 정렬 순서대로 정렬

        Returns:
            CommonCodeItem 리스트
        """
        logger.info(
            "get_by_group_id_start",
            group_id=str(group_id),
            is_active_only=is_active_only,
            order_by_sort=order_by_sort,
        )

        # Use raw SQL due to SQLAlchemy ORM metadata caching issues
        from sqlalchemy import text

        group_id_str = str(group_id)
        sql = "SELECT * FROM common_code_items WHERE group_id = :group_id"
        params = {"group_id": group_id_str}

        if is_active_only:
            sql += " AND is_active = true"

        if order_by_sort:
            sql += " ORDER BY sort_order ASC"

        logger.debug("get_by_group_id_query", query=sql, params=params)
        result = await self.session.execute(text(sql), params)

        # Convert rows to CommonCodeItem objects
        items = []
        for row in result.mappings():
            item = CommonCodeItem(
                id=row['id'],
                group_id=row['group_id'],
                code_key=row['code_key'],
                code_value=row['code_value'],
                sort_order=row['sort_order'],
                is_active=row['is_active'],
                attributes=row['attributes'],
                created_at=row['created_at'],
                updated_at=row['updated_at'],
            )
            items.append(item)

        logger.info(
            "get_by_group_id_result",
            group_id=str(group_id),
            item_count=len(items) if items else 0,
        )
        return items

    async def get_by_group_code(
        self, group_code: str, is_active_only: bool = False
    ) -> Sequence[CommonCodeItem]:
        """
        그룹 코드로 해당 그룹의 항목들 조회

        Args:
            group_code: 그룹 코드 (예: BUSINESS_TYPE)
            is_active_only: True면 활성 항목만 조회

        Returns:
            CommonCodeItem 리스트
        """
        logger.info(
            "get_by_group_code_start",
            group_code=group_code,
            is_active_only=is_active_only,
        )

        # First, get the group by code
        group_stmt = select(CommonCodeGroup).where(
            CommonCodeGroup.group_code == group_code
        )
        group_result = await self.session.execute(group_stmt)
        group = group_result.scalars().first()

        logger.info(
            "get_by_group_code_group_found",
            group_code=group_code,
            group_id=str(group.id) if group else None,
            group_found=group is not None,
        )

        if not group:
            logger.warning("get_by_group_code_group_not_found", group_code=group_code)
            return []

        # Then, get items for this group
        items = await self.get_by_group_id(group.id, is_active_only=is_active_only)
        logger.info(
            "get_by_group_code_items_found",
            group_id=str(group.id),
            item_count=len(items) if items else 0,
        )
        return items

    async def get_by_code_key(
        self, group_id: UUID, code_key: str
    ) -> CommonCodeItem | None:
        """
        그룹 내에서 코드 키로 항목 조회

        Args:
            group_id: 그룹 ID
            code_key: 코드 키

        Returns:
            CommonCodeItem 또는 None
        """
        # Use raw SQL due to SQLAlchemy ORM metadata caching issues
        from sqlalchemy import text

        group_id_str = str(group_id)
        sql = "SELECT * FROM common_code_items WHERE group_id = :group_id AND code_key = :code_key LIMIT 1"
        params = {"group_id": group_id_str, "code_key": code_key}
        result = await self.session.execute(text(sql), params)

        row = result.mappings().first()
        if not row:
            return None

        item = CommonCodeItem(
            id=row['id'],
            group_id=row['group_id'],
            code_key=row['code_key'],
            code_value=row['code_value'],
            sort_order=row['sort_order'],
            is_active=row['is_active'],
            attributes=row['attributes'],
            created_at=row['created_at'],
            updated_at=row['updated_at'],
        )
        return item

    async def get_by_id_or_raise(self, id: UUID) -> CommonCodeItem:
        """
        ID로 항목 조회, 없으면 예외 발생

        Args:
            id: 항목 ID

        Returns:
            CommonCodeItem

        Raises:
            RecordNotFoundError: 항목을 찾을 수 없음
        """
        item = await self.get_by_id(id)
        if not item:
            raise RecordNotFoundError(f"CommonCodeItem with id {id} not found")
        return item

    async def check_duplicate_code_key(
        self, group_id: UUID, code_key: str, exclude_id: UUID | None = None
    ) -> bool:
        """
        같은 그룹 내에서 코드 키 중복 확인

        Args:
            group_id: 그룹 ID
            code_key: 코드 키
            exclude_id: 제외할 항목 ID (수정 시 자신은 제외)

        Returns:
            True면 중복 존재
        """
        # Use raw SQL due to SQLAlchemy ORM metadata caching issues
        from sqlalchemy import text

        group_id_str = str(group_id)
        sql = "SELECT COUNT(*) FROM common_code_items WHERE group_id = :group_id AND code_key = :code_key"
        params = {"group_id": group_id_str, "code_key": code_key}

        if exclude_id:
            sql += " AND id != :exclude_id"
            params["exclude_id"] = str(exclude_id)

        result = await self.session.execute(text(sql), params)
        count = result.scalars().first() or 0
        return count > 0

    async def count_by_group_id(self, group_id: UUID) -> int:
        """
        특정 그룹의 항목 개수

        Args:
            group_id: 그룹 ID

        Returns:
            항목 개수
        """
        # Use raw SQL due to SQLAlchemy ORM metadata caching issues
        from sqlalchemy import text

        group_id_str = str(group_id)
        sql = "SELECT COUNT(*) FROM common_code_items WHERE group_id = :group_id"
        params = {"group_id": group_id_str}
        result = await self.session.execute(text(sql), params)
        count = result.scalars().first()
        return count or 0

    async def delete_by_group_id(self, group_id: UUID) -> int:
        """
        그룹의 모든 항목 삭제

        Args:
            group_id: 그룹 ID

        Returns:
            삭제된 항목 수
        """
        # Use raw SQL due to SQLAlchemy ORM metadata caching issues
        from sqlalchemy import text

        group_id_str = str(group_id)
        sql = "DELETE FROM common_code_items WHERE group_id = :group_id"
        params = {"group_id": group_id_str}
        result = await self.session.execute(text(sql), params)
        return result.rowcount

    async def update_sort_order(self, id: UUID, sort_order: int) -> CommonCodeItem:
        """
        항목의 정렬 순서 업데이트

        Args:
            id: 항목 ID
            sort_order: 새로운 정렬 순서

        Returns:
            업데이트된 CommonCodeItem
        """
        item = await self.get_by_id_or_raise(id)
        item.sort_order = sort_order
        await self.session.flush()
        await self.session.refresh(item)
        return item
