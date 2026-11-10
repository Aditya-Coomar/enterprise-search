import hashlib
import json
import logging
import sys
from contextlib import contextmanager, nullcontext
from contextvars import ContextVar
from datetime import UTC, datetime
from threading import Lock
from time import perf_counter
from typing import Any

import structlog


def configure_logging(level: str) -> None:
    structlog.configure(
        logger_factory=structlog.PrintLoggerFactory(file=sys.stderr),
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(getattr(logging, level)),
    )


log = structlog.get_logger()


def now() -> str:
    return datetime.now(UTC).isoformat()


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def json_bytes(data: Any) -> bytes:
    return json.dumps(
        data, ensure_ascii=False, sort_keys=True, allow_nan=False, separators=(",", ":")
    ).encode()


class ServiceError(Exception):
    def __init__(self, code: str, message: str, stage: str, status: int = 422, retryable: bool = False):
        super().__init__(message)
        self.status = status
        self.detail = {"code": code, "message": message, "stage": stage, "retryable": retryable}


class Metrics:
    def __init__(self):
        self.lock = Lock()
        self.values: dict[str, float] = {}

    def add(self, name: str, amount: float = 1) -> None:
        with self.lock:
            self.values[name] = self.values.get(name, 0) + amount

    def snapshot(self) -> dict[str, float]:
        with self.lock:
            return self.values.copy()

    @contextmanager
    def measure(self, stage: str):
        start = perf_counter()
        log.info("stage_started", stage=stage)
        try:
            yield
        except Exception as exc:
            log.warning("stage_failed", stage=stage, exception=type(exc).__name__)
            raise
        finally:
            duration = perf_counter() - start
            self.add(stage + "_seconds_total", duration)
            self.add(stage + "_calls_total")
            log.info("stage_finished", stage=stage, duration=duration)


active_metrics: ContextVar[Metrics | None] = ContextVar("active_metrics", default=None)


@contextmanager
def record_metrics(metrics: Metrics):
    token = active_metrics.set(metrics)
    try:
        yield
    finally:
        active_metrics.reset(token)


def measure(stage: str):
    metrics = active_metrics.get()
    return metrics.measure(stage) if metrics else nullcontext()
