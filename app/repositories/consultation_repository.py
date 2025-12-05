"""
Consultation Repository Layer

이미 정의된 SQLAlchemy 모델을 대상으로 한 기본 CRUD/검색 뼈대입니다.
서비스 레이어에서 트랜잭션을 관리하므로 이 레이어에서는 flush/refresh만 수행합니다.
"""

from dataclasses import dataclass
from typing import Sequence
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.consultation import Consultation
from app.schemas.consultation import ConsultationCreate


@dataclass(slots=True)
class ConsultationSearchFilters:
    """컨설테이션 검색 시 메타데이터 필터."""

    branch_code: str | None = None
    business_type: str | None = None
    error_code: str | None = None


class ConsultationRepository:
    """상담 도메인의 기본 CRUD 쿼리를 담당하는 Repository."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def create_consultation(self, data: ConsultationCreate) -> Consultation:
        """상담 생성."""

        consultation = Consultation(**data.model_dump())
        self.session.add(consultation)
        await self.session.flush()
        await self.session.refresh(consultation)
        return consultation

    async def get_by_id(self, id: UUID) -> Consultation | None:
        """PK 기반 단건 조회."""

        stmt = select(Consultation).where(Consultation.id == id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def search_by_ids(
        self,
        ids: list[UUID],
        filters: ConsultationSearchFilters,
    ) -> list[Consultation]:
        """
        Vector 검색 결과로 받은 ID 목록을 메타 필터로 재조회.

        입력 순서를 유지해 반환합니다.
        """

        if not ids:
            return []

        conditions = [Consultation.id.in_(ids)]
        if filters.branch_code:
            conditions.append(Consultation.branch_code == filters.branch_code)
        if filters.business_type:
            conditions.append(Consultation.business_type == filters.business_type)
        if filters.error_code:
            conditions.append(Consultation.error_code == filters.error_code)

        stmt = select(Consultation).where(*conditions)
        result = await self.session.execute(stmt)
        records: Sequence[Consultation] = result.scalars().all()

        record_map = {item.id: item for item in records}
        return [record_map[id] for id in ids if id in record_map]
