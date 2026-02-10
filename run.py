#!/usr/bin/env python
"""Run script to start the application server.

For development: python run.py (uses uvicorn with reload)
For production: ./entrypoint.sh (uses gunicorn + uvicorn workers)
"""
import os
import uvicorn
from app.config import get_settings


def main():
    """Run the development application server."""
    settings = get_settings()
    
    print(f"Starting {settings.app_name} on http://{settings.host}:{settings.port}")
    print(f"Environment: {settings.environment}")
    
    uvicorn.run(
        "app.main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.is_development,
        log_level=settings.log_level.lower(),
    )


if __name__ == "__main__":
    main()
