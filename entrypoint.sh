#!/bin/bash
set -e

echo "=== Check Splitter Entrypoint ==="
echo "Environment: ${ENVIRONMENT:-development}"
echo "Port: ${PORT:-8000}"
echo "Workers: ${WORKERS:-2}"

# Run database migrations if enabled
if [ "${RUN_MIGRATIONS}" = "true" ]; then
    echo "Running database migrations..."
    
    # Check if alembic_version table exists (indicates migrations have run before)
    if python -c "
import asyncio
from app.config import get_settings
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy import text

async def check():
    settings = get_settings()
    engine = create_async_engine(settings.effective_database_url)
    async with engine.connect() as conn:
        try:
            await conn.execute(text('SELECT 1 FROM alembic_version LIMIT 1'))
            return True
        except:
            return False
    await engine.dispose()

result = asyncio.run(check())
exit(0 if result else 1)
" 2>/dev/null; then
        echo "Existing database detected. Running alembic upgrade..."
        alembic upgrade head
    else
        echo "Fresh database detected. Creating tables and stamping migration..."
        python -c "
import asyncio
from app.database import engine, Base
from app.models import session, participant, item, assignment, discount

async def init():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    await engine.dispose()

asyncio.run(init())
print('Tables created.')
"
        alembic stamp head
        echo "Database initialized and stamped at head."
    fi
    
    echo "Migrations complete."
fi

# Start the application with gunicorn + uvicorn workers
exec gunicorn app.main:app \
    --worker-class uvicorn.workers.UvicornWorker \
    --workers "${WORKERS:-2}" \
    --bind "0.0.0.0:${PORT:-8000}" \
    --timeout 120 \
    --graceful-timeout 30 \
    --keep-alive 5 \
    --access-logfile - \
    --error-logfile - \
    --forwarded-allow-ips "*"
