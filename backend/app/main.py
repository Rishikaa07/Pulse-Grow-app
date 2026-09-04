from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.exc import SQLAlchemyError

from .api.routes import auth, market, watchlists
from .config import settings
from .db.session import init_db
from .worker import worker

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-7s %(name)s :: %(message)s",
)
log = logging.getLogger("pulse")


@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_db()
    await worker.start()
    log.info("Pulse API ready (env=%s, cache=%s)", settings.environment, "redis" if settings.redis_url else "memory")
    try:
        yield
    finally:
        await worker.stop()


app = FastAPI(
    title="Pulse API",
    version="1.0.0",
    description="A market attention engine. Tells you what changed, how unusual it was, and why.",
    lifespan=lifespan,
    docs_url="/api/docs",
    openapi_url="/api/openapi.json",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=list(settings.cors_origins),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(RequestValidationError)
async def validation_error(_request: Request, exc: RequestValidationError):
    """Return one readable message instead of a wall of pydantic internals."""
    first = exc.errors()[0] if exc.errors() else {}
    field = ".".join(str(p) for p in first.get("loc", [])[1:]) or "request"
    return JSONResponse(
        status_code=422,
        content={"detail": f"{field}: {first.get('msg', 'is invalid')}"},
    )


@app.exception_handler(SQLAlchemyError)
async def database_error(_request: Request, exc: SQLAlchemyError):
    log.exception("database error", exc_info=exc)
    return JSONResponse(
        status_code=503,
        content={"detail": "The database is temporarily unavailable. Try again in a moment."},
    )


@app.exception_handler(Exception)
async def unhandled_error(_request: Request, exc: Exception):
    log.exception("unhandled error", exc_info=exc)
    return JSONResponse(
        status_code=500,
        content={"detail": "Something went wrong on our side. The team has been notified."},
    )


app.include_router(auth.router, prefix="/api")
app.include_router(watchlists.router, prefix="/api")
app.include_router(market.router, prefix="/api")


@app.get("/", include_in_schema=False)
def root():
    return {"service": "pulse-api", "docs": "/api/docs"}
