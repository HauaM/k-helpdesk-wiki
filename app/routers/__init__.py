"""
API Routers
FastAPI route handlers
"""

from app.routers import (
    auth,
    common_codes,
    consultations,
    departments,
    manuals,
    tasks,
    users,
)

__all__ = [
    "auth",
    "common_codes",
    "consultations",
    "departments",
    "manuals",
    "tasks",
    "users",
]
