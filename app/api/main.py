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
from app.core.db import close_db
from app.llm.embedder import get_embedding_service

# Import routers
from app.routers import auth, consultations, manuals, tasks, common_codes
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
        - Preload embedding service (E5 model)

    Shutdown:
        - Close database connections

    Unit Spec v1.1: LIFECYCLE INTEGRATION
    - Embedding service loaded at startup with warmup
    - Prevents first request from triggering slow model download
    - Fast-fail semantics: raises error if model loading fails
    """
    # Startup
    logger.info("application_startup", environment=settings.environment)
    configure_logging()

    # TODO: Only init_db in development, use Alembic in production
    if settings.environment == "development":
        logger.info("initializing_database_tables")
        # await init_db()  # Uncomment when models are ready

    # Preload embedding service with model warmup (Unit Spec v1.1)
    try:
        logger.info(
            "embedding_service_startup",
            model=settings.e5_model_name,
            device=settings.embedding_device,
        )
        embedding_service = get_embedding_service()
        await embedding_service.warmup()
        logger.info("embedding_service_ready", model=settings.e5_model_name)
    except Exception as e:
        logger.critical("embedding_service_startup_failed", error=str(e))
        raise

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
