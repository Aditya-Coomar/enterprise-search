from contextlib import asynccontextmanager
from hmac import compare_digest
from uuid import uuid4

import psutil
import structlog
from fastapi import Depends, FastAPI, Request, Security
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.security import APIKeyHeader
from starlette.concurrency import run_in_threadpool

from src.api.limits import LimitJSONBody
from src.api.routes import routes
from src.core.config import Settings
from src.core.lifecycle import runtime
from src.core.runtime import ServiceError, configure_logging, log


def create_app(settings: Settings | None = None) -> FastAPI:
    cfg = settings or Settings()
    configure_logging("DEBUG" if cfg.debug else cfg.log_level)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        manager = runtime(cfg)
        app.state.runtime = await run_in_threadpool(manager.__enter__)
        try:
            yield
        finally:
            await run_in_threadpool(manager.__exit__, None, None, None)

    app = FastAPI(title=cfg.app_name, version="1.0.0", lifespan=lifespan)

    @app.middleware("http")
    async def request_context(request: Request, call_next):
        request_id = uuid4().hex
        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(request_id=request_id)
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        return response

    @app.exception_handler(ServiceError)
    async def handle_error(request: Request, exc: ServiceError):
        log.warning("request_failed", **exc.detail)
        return JSONResponse(
            {"error": exc.detail, **structlog.contextvars.get_contextvars()}, status_code=exc.status
        )

    @app.exception_handler(RequestValidationError)
    async def invalid_request(request: Request, exc: RequestValidationError):
        return await handle_error(
            request,
            ServiceError(
                "invalid_request",
                "Invalid fields: " + ", ".join(".".join(map(str, e["loc"])) for e in exc.errors()[:10]),
                "request",
            ),
        )

    @app.exception_handler(Exception)
    async def unexpected(request: Request, exc: Exception):
        log.error("unexpected_failure", exception=type(exc).__name__)
        return await handle_error(
            request, ServiceError("internal_error", "Internal service error.", "service", 500)
        )

    header = APIKeyHeader(name="X-Internal-Key", auto_error=False)

    def authenticate(key: str | None = Security(header)) -> None:
        if not key or not compare_digest(key.encode(), cfg.internal_api_key.get_secret_value().encode()):
            raise ServiceError("unauthorized", "Internal service key required.", "auth", 401)

    @app.get("/health")
    @app.get("/health/live")
    def live() -> dict[str, str]:
        """Return liveness without loading dependencies."""
        return {"status": "live"}

    @app.get("/health/ready")
    def ready(request: Request) -> dict:
        """Verify configured storage and required model availability."""
        rt = request.app.state.runtime
        try:
            storage_ready = rt.store.ready()
        except ServiceError as exc:
            raise ServiceError(
                "not_ready", "Required storage unavailable.", "readiness", 503, True
            ) from exc
        if not storage_ready or any(
            rt.models.status()[k]["state"] != "ready" for k in cfg.ai_required_models
        ):
            raise ServiceError("not_ready", "Required dependencies unavailable.", "readiness", 503, True)
        return {"status": "ready"}

    @app.get(cfg.api_prefix + "/metrics", dependencies=[Depends(authenticate)])
    def metrics(request: Request) -> dict:
        """Return process-local counters, durations and host memory."""
        counters = request.app.state.runtime.metrics.snapshot()
        return {
            "counters": counters,
            "average_processing_seconds": counters.get("processing_seconds_total", 0)
            / max(1, counters.get("processing_calls_total", 0)),
            "available_memory_bytes": psutil.virtual_memory().available,
        }

    app.include_router(
        routes(),
        prefix=cfg.api_prefix,
        dependencies=[Depends(authenticate)],
        responses={
            401: {"description": "Internal key required"},
            413: {"description": "Input exceeds limit"},
            422: {"description": "Invalid input"},
            429: {"description": "Worker at capacity"},
            503: {"description": "Dependency unavailable"},
            504: {"description": "Inference timeout"},
        },
    )
    app.add_middleware(LimitJSONBody, limit=cfg.max_request_bytes)
    return app
