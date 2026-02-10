"""FastAPI application entry point."""
import traceback
from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.database import init_db, close_db
from app.config import get_settings
from app.logging_config import setup_logging, get_logger
from app.middleware import (
    SecurityHeadersMiddleware,
    RequestLoggingMiddleware,
    RateLimitMiddleware,
)
from app.api import (
    sessions_router,
    items_router,
    participants_router,
    assignments_router,
    utilities_router,
    discounts_router,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan events."""
    settings = get_settings()
    logger = get_logger("main")
    
    # Setup logging
    setup_logging(
        log_level=settings.log_level,
        log_format="text" if settings.is_development else settings.log_format
    )
    
    logger.info(
        f"Starting {settings.app_name} v{settings.version}",
        extra={"extra_fields": {"environment": settings.environment}}
    )
    
    # Startup
    await init_db()
    logger.info("Database initialized")
    
    yield
    
    # Shutdown
    logger.info("Shutting down application")
    await close_db()


settings = get_settings()
logger = get_logger("main")

app = FastAPI(
    title=settings.app_name,
    description="Split restaurant bills easily among friends",
    version=settings.version,
    lifespan=lifespan,
    docs_url="/docs" if settings.is_development else None,
    redoc_url="/redoc" if settings.is_development else None,
    openapi_url="/openapi.json" if settings.is_development else None,
)


# ====== Exception Handlers ======

@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    """Handle HTTP exceptions with consistent format."""
    # Serve custom 404 page for browser requests
    if exc.status_code == 404:
        accept_header = request.headers.get("accept", "")
        if "text/html" in accept_header:
            return FileResponse(
                str(static_dir / "404.html"),
                status_code=404,
                media_type="text/html"
            )
    
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": True,
            "status_code": exc.status_code,
            "detail": exc.detail,
        }
    )


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Handle unexpected exceptions."""
    logger.error(f"Unhandled exception: {exc}", exc_info=True)
    
    # In development, show full error details
    if settings.is_development:
        return JSONResponse(
            status_code=500,
            content={
                "error": True,
                "status_code": 500,
                "detail": str(exc),
                "traceback": traceback.format_exc(),
            }
        )
    
    # In production, hide internal details
    return JSONResponse(
        status_code=500,
        content={
            "error": True,
            "status_code": 500,
            "detail": "An internal error occurred. Please try again later.",
        }
    )


# ====== Middleware (order matters - first added = outermost) ======

# Gzip compression for responses
app.add_middleware(GZipMiddleware, minimum_size=1000)

# Security headers
app.add_middleware(SecurityHeadersMiddleware)

# Request logging with request ID
app.add_middleware(RequestLoggingMiddleware)

# Rate limiting
app.add_middleware(RateLimitMiddleware, requests_per_minute=settings.rate_limit_per_minute)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)


# ====== Routers ======

app.include_router(sessions_router)
app.include_router(items_router)
app.include_router(participants_router)
app.include_router(assignments_router)
app.include_router(utilities_router)
app.include_router(discounts_router)


# ====== Static Files ======

static_dir = Path(__file__).parent.parent / "static"
app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")


# ====== Root Routes ======

@app.get("/manifest.json")
async def manifest():
    """Serve manifest.json from root for PWA compatibility."""
    return FileResponse(str(static_dir / "manifest.json"), media_type="application/manifest+json")


@app.get("/")
async def root():
    """Serve the main frontend page."""
    return FileResponse(str(static_dir / "index.html"))


@app.get("/health")
async def health_check():
    """Health check endpoint for Cloud Run and load balancers.
    
    Verifies database connectivity for readiness probes.
    """
    from app.database import async_session_maker
    
    health = {
        "status": "healthy",
        "version": settings.version,
        "environment": settings.environment,
    }
    
    # Check database connectivity
    try:
        async with async_session_maker() as session:
            from sqlalchemy import text
            await session.execute(text("SELECT 1"))
        health["database"] = "connected"
    except Exception as e:
        logger.error(f"Health check DB failure: {e}")
        health["status"] = "degraded"
        health["database"] = "disconnected"
        return JSONResponse(status_code=503, content=health)
    
    return health

