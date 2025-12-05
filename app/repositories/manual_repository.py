"""
Manual Repository Layer

메뉴얼 엔트리/버전 모델에 대한 단순 CRUD 뼈대입니다.
서비스에서 트랜잭션을 제어하고 이 레이어는 flush/refresh만 수행합니다.
"""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.manual import ManualEntry, ManualStatus, ManualVersion
from app.schemas.manual import ManualEntryCreate


class ManualRepository:
    """메뉴얼 생성·승인 관련 기본 RDB 접근."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def create_draft(self, data: ManualEntryCreate) -> ManualEntry:
        """상담 기반 메뉴얼 초안 생성."""

        entry = ManualEntry(**data.model_dump(), status=ManualStatus.DRAFT)
        self.session.add(entry)
        await self.session.flush()
        await self.session.refresh(entry)
        return entry

    async def approve_manual(
        self,
        manual_entry: ManualEntry,
        version: ManualVersion | None = None,
    ) -> ManualEntry:
        """메뉴얼 승인 처리 및 버전 연결."""

        manual_entry.status = ManualStatus.APPROVED
        if version is not None:
            manual_entry.version_id = version.id
        await self.session.flush()
        await self.session.refresh(manual_entry)
        return manual_entry

    async def get_latest_version(self) -> ManualVersion | None:
        """가장 최근 버전을 조회."""

        stmt = select(ManualVersion).order_by(ManualVersion.created_at.desc()).limit(1)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_version_by_id(self, version_id: UUID) -> ManualVersion | None:
        """버전 PK 조회."""

        stmt = select(ManualVersion).where(ManualVersion.id == version_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()
