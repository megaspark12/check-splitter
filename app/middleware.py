"""Production middleware for security, logging, and rate limiting."""
import time
from typing import Callable
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response, JSONResponse

from app.logging_config import get_logger, generate_request_id, set_request_id
from app.config import get_settings

logger = get_logger("middleware")


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Add security headers to all responses."""
    
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        response = await call_next(request)
        
        # Security headers
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        
        # Content Security Policy (adjust as needed for your app)
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            "script-src 'self' 'unsafe-inline'; "
            "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
            "font-src 'self' https://fonts.gstatic.com; "
            "img-src 'self' data: blob:; "
            "connect-src 'self' ws: wss:; "
            "frame-ancestors 'none';"
        )
        
        # Only add HSTS in production with HTTPS
        settings = get_settings()
        if settings.is_production:
            response.headers["Strict-Transport-Security"] = (
                "max-age=31536000; includeSubDomains"
            )
        
        return response


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """Log all requests with timing and request ID."""
    
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        # Generate and set request ID
        request_id = request.headers.get("X-Request-ID") or generate_request_id()
        set_request_id(request_id)
        
        # Start timing
        start_time = time.perf_counter()
        
        # Get client IP
        forwarded = request.headers.get("X-Forwarded-For")
        client_ip = forwarded.split(",")[0].strip() if forwarded else (
            request.client.host if request.client else "unknown"
        )
        
        # Process request
        try:
            response = await call_next(request)
            
            # Calculate duration
            duration_ms = (time.perf_counter() - start_time) * 1000
            
            # Log request (skip health checks and static files in production)
            settings = get_settings()
            skip_paths = {"/health", "/metrics"}
            if not settings.is_production or (
                request.url.path not in skip_paths and 
                not request.url.path.startswith("/static/")
            ):
                logger.info(
                    f"{request.method} {request.url.path} {response.status_code} {duration_ms:.2f}ms",
                    extra={
                        "extra_fields": {
                            "method": request.method,
                            "path": request.url.path,
                            "status_code": response.status_code,
                            "duration_ms": round(duration_ms, 2),
                            "client_ip": client_ip,
                            "user_agent": request.headers.get("user-agent", ""),
                        }
                    }
                )
            
            # Add request ID to response headers
            response.headers["X-Request-ID"] = request_id
            
            return response
            
        except Exception as e:
            duration_ms = (time.perf_counter() - start_time) * 1000
            logger.error(
                f"{request.method} {request.url.path} ERROR {duration_ms:.2f}ms: {str(e)}",
                exc_info=True
            )
            raise


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Simple in-memory rate limiting middleware."""
    
    def __init__(self, app, requests_per_minute: int = 60):
        super().__init__(app)
        self.requests_per_minute = requests_per_minute
        self.requests: dict = defaultdict(list)
        self._cleanup_interval = 60  # seconds
        self._last_cleanup = datetime.now(timezone.utc)
    
    def _cleanup_old_requests(self) -> None:
        """Remove expired request timestamps."""
        now = datetime.now(timezone.utc)
        if (now - self._last_cleanup).seconds < self._cleanup_interval:
            return
        
        cutoff = now - timedelta(minutes=1)
        for ip in list(self.requests.keys()):
            self.requests[ip] = [
                ts for ts in self.requests[ip] if ts > cutoff
            ]
            if not self.requests[ip]:
                del self.requests[ip]
        
        self._last_cleanup = now
    
    def _get_client_ip(self, request: Request) -> str:
        """Get client IP, handling proxies."""
        forwarded = request.headers.get("X-Forwarded-For")
        if forwarded:
            return forwarded.split(",")[0].strip()
        return request.client.host if request.client else "unknown"
    
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        # Skip rate limiting for health checks
        if request.url.path in {"/health", "/metrics"}:
            return await call_next(request)
        
        self._cleanup_old_requests()
        
        client_ip = self._get_client_ip(request)
        now = datetime.now(timezone.utc)
        cutoff = now - timedelta(minutes=1)
        
        # Count recent requests
        recent_requests = [
            ts for ts in self.requests[client_ip] if ts > cutoff
        ]
        
        if len(recent_requests) >= self.requests_per_minute:
            logger.warning(
                f"Rate limit exceeded for {client_ip}",
                extra={"extra_fields": {"client_ip": client_ip}}
            )
            return JSONResponse(
                status_code=429,
                content={
                    "detail": "Too many requests. Please try again later.",
                    "retry_after": 60
                },
                headers={
                    "Retry-After": "60",
                    "X-RateLimit-Limit": str(self.requests_per_minute),
                    "X-RateLimit-Remaining": "0",
                }
            )
        
        # Record this request
        self.requests[client_ip].append(now)
        
        response = await call_next(request)
        
        # Add rate limit headers
        remaining = self.requests_per_minute - len(self.requests[client_ip])
        response.headers["X-RateLimit-Limit"] = str(self.requests_per_minute)
        response.headers["X-RateLimit-Remaining"] = str(max(0, remaining))
        
        return response
