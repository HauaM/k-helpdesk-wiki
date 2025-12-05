"""
Base Repository Classes
Generic CRUD operations for RDB
"""

from typing import Generic, TypeVar, Type, Sequence
from uuid import UUID

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import Base
from app.core.exceptions import RecordNotFoundError

ModelType = TypeVar("ModelType", bound=Base)


class BaseRepository(Generic[ModelType]):
    """
    Generic repository for CRUD operations

    Provides common database operations for any SQLAlchemy model
    """

    def __init__(self, model: Type[ModelType], session: AsyncSession):
        """
        Initialize repository

        Args:
            model: SQLAlchemy model class
            session: AsyncSession for database operations
        """
        self.model = model
        self.session = session

    async def create(self, obj: ModelType) -> ModelType:
        """
        Create new record

        Args:
            obj: Model instance to create

        Returns:
            Created model instance
        """
        self.session.add(obj)
        await self.session.flush()
        await self.session.refresh(obj)
        return obj

    async def get_by_id(self, id: UUID) -> ModelType | None:
        """
        Get record by ID

        Args:
            id: Record UUID

        Returns:
            Model instance or None if not found
        """
        stmt = select(self.model).where(self.model.id == id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_id_or_raise(self, id: UUID) -> ModelType:
        """
        Get record by ID or raise exception

        Args:
            id: Record UUID

        Returns:
            Model instance

        Raises:
            RecordNotFoundError: If record not found
        """
        obj = await self.get_by_id(id)
        if obj is None:
            raise RecordNotFoundError(
                f"{self.model.__name__} with id={id} not found"
            )
        return obj

    async def get_all(
        self,
        limit: int = 100,
        offset: int = 0,
    ) -> Sequence[ModelType]:
        """
        Get all records with pagination

        Args:
            limit: Maximum number of records
            offset: Number of records to skip

        Returns:
            List of model instances
        """
        stmt = select(self.model).limit(limit).offset(offset)
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def count(self) -> int:
        """
        Count total records

        Returns:
            Total number of records
        """
        stmt = select(func.count()).select_from(self.model)
        result = await self.session.execute(stmt)
        return result.scalar_one()

    async def update(self, obj: ModelType) -> ModelType:
        """
        Update existing record

        Args:
            obj: Model instance with updated fields

        Returns:
            Updated model instance
        """
        await self.session.flush()
        await self.session.refresh(obj)
        return obj

    async def delete(self, obj: ModelType) -> None:
        """
        Delete record

        Args:
            obj: Model instance to delete
        """
        await self.session.delete(obj)
        await self.session.flush()

    async def delete_by_id(self, id: UUID) -> None:
        """
        Delete record by ID

        Args:
            id: Record UUID

        Raises:
            RecordNotFoundError: If record not found
        """
        obj = await self.get_by_id_or_raise(id)
        await self.delete(obj)
