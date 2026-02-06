#!/usr/bin/env python
"""Run script to start both main app and metrics server."""
import asyncio
import uvicorn
from app.config import get_settings


async def run_servers():
    """Run main app and metrics server concurrently."""
    settings = get_settings()
    
    # Main app configuration
    main_config = uvicorn.Config(
        "app.main:app",
        host=settings.host,
        port=settings.port,
        log_level=settings.log_level.lower(),
    )
    
    # Metrics server configuration (internal only)
    metrics_config = uvicorn.Config(
        "app.main:metrics_app",
        host="127.0.0.1",  # Only bind to localhost for security
        port=settings.metrics_port,
        log_level="warning",  # Less verbose for metrics server
    )
    
    main_server = uvicorn.Server(main_config)
    metrics_server = uvicorn.Server(metrics_config)
    
    print(f"Starting main app on http://{settings.host}:{settings.port}")
    print(f"Starting metrics server on http://127.0.0.1:{settings.metrics_port}/metrics")
    
    # Run both servers concurrently
    await asyncio.gather(
        main_server.serve(),
        metrics_server.serve(),
    )


if __name__ == "__main__":
    asyncio.run(run_servers())
