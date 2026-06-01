from contextlib import asynccontextmanager
import logging
from time import perf_counter
from uuid import uuid4

from fastapi import FastAPI, Request
from sqlalchemy.exc import SQLAlchemyError

from app.api.routes import auth, customers, health, imports
from app.config import settings
from app.database import SessionLocal
from app.services.logging import configure_logging
from app.services.metrics import record_request
from app.services.users import seed_demo_users

_INSECURE_SECRETS = {
    "change-this-secret-before-deploying",
    "local-development-secret",
    "replace-with-a-random-secret",
}

configure_logging()
logger = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    if settings.jwt_secret_key in _INSECURE_SECRETS:
        logger.warning(
            "insecure_jwt_secret",
            extra={"detail": "JWT_SECRET_KEY is set to a known placeholder. "
                             "Generate a secret with: python3 -c \"import secrets; print(secrets.token_hex(32))\""},
        )
    with SessionLocal() as db:
        seed_demo_users(db)
    yield


app = FastAPI(
    title="Partner Customer Import API",
    version="0.1.0",
    lifespan=lifespan,
)
app.state.session_factory = SessionLocal


@app.middleware("http")
async def log_requests(request: Request, call_next):
    request_id = request.headers.get("X-Request-ID", str(uuid4()))
    started_at = perf_counter()
    response = await call_next(request)
    duration_ms = round((perf_counter() - started_at) * 1000, 2)
    response.headers["X-Request-ID"] = request_id
    try:
        with request.app.state.session_factory() as db:
            record_request(db, request.method, request.url.path, response.status_code)
    except SQLAlchemyError:
        logger.warning("request_metric_persistence_failed")
    logger.info(
        "request_completed",
        extra={
            "request_id": request_id,
            "method": request.method,
            "path": request.url.path,
            "status_code": response.status_code,
            "duration_ms": duration_ms,
        },
    )
    return response


app.include_router(auth.router, prefix="/auth", tags=["auth"])
app.include_router(health.router, tags=["health"])
app.include_router(customers.router, prefix="/customers", tags=["customers"])
app.include_router(imports.router, prefix="/imports", tags=["imports"])
