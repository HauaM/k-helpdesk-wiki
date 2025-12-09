"""
API Routers
FastAPI route handlers
"""

from app.routers import auth, consultations, manuals, tasks, common_codes

__all__ = ["auth", "consultations", "manuals", "tasks", "common_codes"]
