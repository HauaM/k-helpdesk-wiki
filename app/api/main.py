"""
FastAPI Application Factory

Creates and configures FastAPI application
"""

from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.core.logging import configure_logging, get_logger
from app.core.db import async_session_maker, close_db
from app.llm.embedder import get_embedding_service
from app.services.system_bootstrap_service import SystemBootstrapService

# Import routers
from app.routers import (
    auth,
    common_codes,
    consultations,
    departments,
    manuals,
    tasks,
    users,
)
from app.api.error_handlers import register_exception_handlers
from app.api.response_middleware import SuccessEnvelopeMiddleware

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """
    Application lifespan events

    Startup:
        - Configure logging
        - Initialize database (dev only)
        - Schedule embedding service warmup as background task

    Shutdown:
        - Close database connections

    Unit Spec v1.1: LIFECYCLE INTEGRATION
    - Embedding service loaded at startup with warmup (async background task)
    - Allows server to start without waiting for slow model download
    - Lazy initialization: first request waits if model not ready
    """
    # Startup
    logger.info("application_startup", environment=settings.environment)
    configure_logging()

    # TODO: Only init_db in development, use Alembic in production
    if settings.environment == "development":
        logger.info("initializing_database_tables")
        # await init_db()  # Uncomment when models are ready

    if not settings.admin_id or not settings.admin_pw:
        logger.warning("system_admin_bootstrap_skipped", reason="missing_admin_credentials")
    else:
        async with async_session_maker() as session:
            bootstrap_service = SystemBootstrapService(session)
            try:
                await bootstrap_service.ensure_system_admin(
                    settings.admin_id,
                    settings.admin_pw,
                )
                await session.commit()
                logger.info(
                    "system_admin_bootstrap_complete",
                    employee_id=settings.admin_id,
                )
            except Exception as exc:  # noqa: BLE001
                await session.rollback()
                logger.error(
                    "system_admin_bootstrap_failed",
                    employee_id=settings.admin_id,
                    error=str(exc),
                )

    # Schedule embedding service warmup as background task (non-blocking)
    import asyncio
    import time
    async def warmup_embedding_service() -> None:
        """Background task to preload embedding service with progress tracking."""
        t0 = time.perf_counter()
        try:
            logger.info(
                "embedding_service_background_warmup_start",
                model=settings.e5_model_name,
                device=settings.embedding_device,
            )
            embedding_service = get_embedding_service()
            await embedding_service.warmup()

            elapsed = time.perf_counter() - t0
            logger.info(
                "embedding_service_background_warmup_complete",
                model=settings.e5_model_name,
                elapsed_seconds=f"{elapsed:.2f}",
            )

        except Exception as e:
            elapsed = time.perf_counter() - t0
            logger.error(
                "embedding_service_background_warmup_failed",
                error=str(e),
                elapsed_seconds=f"{elapsed:.2f}",
            )
            # Don't raise - allow server to start, lazy init will handle it

    # Create background task but don't await it
    asyncio.create_task(warmup_embedding_service())

    yield

    # Shutdown
    logger.info("application_shutdown")
    await close_db()


def create_app() -> FastAPI:
    """
    Create FastAPI application

    Returns:
        Configured FastAPI app instance

    Usage:
        app = create_app()
        uvicorn.run(app, host="0.0.0.0", port=8000)
    """
    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        description="Customer Support Knowledge Management System",
        lifespan=lifespan,
        docs_url="/docs" if settings.debug else None,
        redoc_url="/redoc" if settings.debug else None,
    )

    # Success envelope middleware
    app.add_middleware(SuccessEnvelopeMiddleware)

    # CORS Middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.allowed_hosts,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Include routers
    app.include_router(
        consultations.router,
        prefix=settings.api_v1_prefix,
    )
    app.include_router(
        manuals.router,
        prefix=settings.api_v1_prefix,
    )
    app.include_router(
        tasks.router,
        prefix=settings.api_v1_prefix,
    )
    app.include_router(
        auth.router,
        prefix=settings.api_v1_prefix,
    )
    app.include_router(
        common_codes.router,
        prefix=settings.api_v1_prefix,
    )
    app.include_router(
        departments.router,
        prefix=settings.api_v1_prefix,
    )
    app.include_router(
        users.router,
        prefix=settings.api_v1_prefix,
    )

    register_exception_handlers(app)

    # Health check endpoint
    @app.get("/health", tags=["health"])
    async def health_check() -> dict:
        """
        Health check endpoint

        Returns:
            Status dict
        """
        return {
            "status": "ok",
            "app": settings.app_name,
            "version": settings.app_version,
            "environment": settings.environment,
        }

    logger.info("fastapi_app_created", routes=len(app.routes))

    return app


# Application instance
app = create_app()
