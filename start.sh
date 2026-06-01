#!/bin/sh
set -e

echo "Running database migrations..."
alembic upgrade head

echo "Starting supervisord..."
exec supervisord -c /etc/supervisor/supervisord.conf
