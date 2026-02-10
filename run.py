#!/usr/bin/env python
"""Run script to start the application server."""
import uvicorn
from app.config import get_settings


def main():
    """Run the main application server."""
    settings = get_settings()
    
    print(f"Starting {settings.app_name} on http://{settings.host}:{settings.port}")
    
    uvicorn.run(
        "app.main:app",
        host=settings.host,
        port=settings.port,
        log_level=settings.log_level.lower(),
    )


if __name__ == "__main__":
    main()
