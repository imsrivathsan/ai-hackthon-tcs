try:
    import truststore
    truststore.inject_into_ssl()
except Exception:
    pass

from contextlib import asynccontextmanager
import logging
from typing import AsyncGenerator

from fastapi import APIRouter, FastAPI, HTTPException, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.config import get_settings, setup_logging
from app.db import SessionLocal, init_db
from app.models import Competitor
from app.routers import admin, ask, auth, battlecards, competitors, feed, overview
from app.schemas import ErrorResponse, HealthResponse
from app.services.seed import load_seed_data

setup_logging()
logger = logging.getLogger("meridian.main")
settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    # Initialize DB tables
    logger.info("Initializing database tables...")
    init_db()

    # Automatically seed initial 6 competitors if table is empty
    with SessionLocal() as db:
        existing_count = db.query(Competitor).count()
        if existing_count == 0:
            logger.info("Database is empty. Loading seed data for 6 competitors...")
            load_seed_data(db)
        else:
            logger.info("Found %d existing competitors in database.", existing_count)

    yield


app = FastAPI(
    title="Meridian API",
    description="AI Competitive Intelligence Analyst for US Insurance Brokerage",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS if isinstance(settings.CORS_ORIGINS, list) else [settings.CORS_ORIGINS],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Consistent error handlers: { "error": ..., "detail": ... }
@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    detail_str = exc.detail if isinstance(exc.detail, str) else str(exc.detail)
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": detail_str, "detail": detail_str},
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={
            "error": "Validation Error",
            "detail": "; ".join([f"{e.get('loc')}: {e.get('msg')}" for e in exc.errors()]),
        },
    )


@app.exception_handler(Exception)
async def generic_exception_handler(request: Request, exc: Exception):
    logger.exception("Unhandled server exception: %s", exc)
    detail_msg = str(exc) if settings.ENVIRONMENT == "development" else "Internal server error"
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"error": "Internal Server Error", "detail": detail_msg},
    )


# API v1 Router prefix
api_v1 = APIRouter(prefix="/api/v1")


@api_v1.get("/health", response_model=HealthResponse, tags=["health"], summary="Health check")
def health_check():
    """Health check endpoint to verify backend status."""
    return HealthResponse(status="ok", app="Meridian", version="1.0.0")


# Mount child routers under /api/v1
api_v1.include_router(competitors.router)
api_v1.include_router(battlecards.router)
api_v1.include_router(overview.router)
api_v1.include_router(feed.router)
api_v1.include_router(ask.router)
api_v1.include_router(admin.router)
api_v1.include_router(auth.router)

# Include in main app
app.include_router(api_v1)

