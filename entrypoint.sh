#!/bin/bash
set -e

echo "=== Check Splitter Entrypoint ==="
echo "Environment: ${ENVIRONMENT:-development}"
echo "Port: ${PORT:-8000}"
echo "Workers: ${WORKERS:-2}"

# Run database migrations if enabled
if [ "${RUN_MIGRATIONS}" = "true" ]; then
    echo "Running database migrations..."
    alembic upgrade head
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
