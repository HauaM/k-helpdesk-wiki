from __future__ import annotations

from typing import Any

from sqlalchemy import JSON
from sqlalchemy.dialects.postgresql import ARRAY as PG_ARRAY, JSONB as PG_JSONB
from sqlalchemy.types import TypeDecorator


class JSONB(TypeDecorator):
    """
    Dialect-aware JSONB type that falls back to JSON on non-Postgres databases.
    """

    impl = JSON
    cache_ok = True

    def load_dialect_impl(self, dialect):
        if dialect.name == "postgresql":
            return dialect.type_descriptor(PG_JSONB())
        return dialect.type_descriptor(JSON())

    def process_bind_param(self, value: Any, dialect) -> Any:
        return value

    def process_result_value(self, value: Any, dialect) -> Any:
        return value


class PGArray(TypeDecorator):
    """
    Dialect-aware array type that uses native ARRAY on Postgres and JSON on others.
    """

    impl = JSON
    cache_ok = True

    def __init__(self, item_type: Any, dimensions: int = 1):
        super().__init__()
        self.item_type = item_type
        self.dimensions = dimensions

    def load_dialect_impl(self, dialect):
        if dialect.name == "postgresql":
            return dialect.type_descriptor(
                PG_ARRAY(self.item_type, dimensions=self.dimensions)
            )
        return dialect.type_descriptor(JSON())

    def process_bind_param(self, value: Any, dialect) -> Any:
        return value

    def process_result_value(self, value: Any, dialect) -> Any:
        return value
