"""
Structured Logging & Monitoring Stubs
NFR-1/NFR-4: 성능/모니터링 훅을 위한 공통 헬퍼를 제공한다.
"""

import logging
import sys
import time
import inspect
import asyncio
from functools import wraps
from typing import Any

import structlog
from structlog.types import EventDict, Processor

from app.core.config import settings


def add_app_context(logger: Any, method_name: str, event_dict: EventDict) -> EventDict:
    """
    Add application context to log entries

    Args:
        logger: Logger instance
        method_name: Logging method name
        event_dict: Event dictionary

    Returns:
        Modified event dictionary
    """
    event_dict["app"] = settings.app_name
    event_dict["version"] = settings.app_version
    event_dict["environment"] = settings.environment
    return event_dict


def configure_logging() -> None:
    """
    Configure structured logging

    Sets up structlog with JSON output if enabled in settings,
    otherwise uses console output for development.
    """
    shared_processors: list[Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        add_app_context,
    ]

    if settings.log_json:
        # Production: JSON logging
        processors: list[Processor] = [
            *shared_processors,
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer(),
        ]
    else:
        # Development: Console logging with colors
        processors = [
            *shared_processors,
            structlog.processors.ExceptionPrettyPrinter(),
            structlog.dev.ConsoleRenderer(colors=True),
        ]

    structlog.configure(
        processors=processors,
        wrapper_class=structlog.make_filtering_bound_logger(
            logging.getLevelName(settings.log_level)
        ),
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )

    # Configure stdlib logging
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=logging.getLevelName(settings.log_level),
    )


def get_logger(name: str) -> structlog.stdlib.BoundLogger:
    """
    Get a structured logger instance

    Args:
        name: Logger name (typically __name__)

    Returns:
        Structured logger instance

    Usage:
        logger = get_logger(__name__)
        logger.info("event_happened", user_id=123, action="login")
    """
    return structlog.get_logger(name)


# --- Monitoring Stubs (Prometheus/OTEL 대체용) ---
_METRICS_COUNTER: dict[str, int] = {}


def metrics_counter(name: str, **labels: Any) -> None:
    """카운터 증가 Stub. 실제 메트릭 시스템 연동 시 교체.

    Args:
        name: metric name
        labels: arbitrary label key/values
    """

    key = name + str(sorted(labels.items()))
    _METRICS_COUNTER[key] = _METRICS_COUNTER.get(key, 0) + 1


def measure_latency(operation: str):
    """비동기/동기 함수에 대한 지연시간 측정 데코레이터."""

    def decorator(func):
        is_coro = inspect.iscoroutinefunction(func)

        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            start = time.perf_counter()
            try:
                return await func(*args, **kwargs)
            finally:
                elapsed_ms = (time.perf_counter() - start) * 1000
                logger = get_logger(func.__module__)
                logger.info("latency", operation=operation, latency_ms=elapsed_ms)

        @wraps(func)
        def sync_wrapper(*args, **kwargs):
            start = time.perf_counter()
            try:
                return func(*args, **kwargs)
            finally:
                elapsed_ms = (time.perf_counter() - start) * 1000
                logger = get_logger(func.__module__)
                logger.info("latency", operation=operation, latency_ms=elapsed_ms)

        return async_wrapper if is_coro else sync_wrapper

    return decorator


def log_llm_call(
    *,
    operation: str,
    model: str | None,
    latency_ms: float,
    tokens: dict | None = None,
    error: str | None = None,
) -> None:
    """LLM 호출 모니터링 로그 헬퍼."""

    logger = get_logger("llm")
    logger.info(
        "llm_call",
        operation=operation,
        model=model,
        latency_ms=latency_ms,
        tokens=tokens,
        error=error,
    )
