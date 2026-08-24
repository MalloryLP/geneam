#!/bin/sh
set -e

echo "==> Applying database migrations..."
python manage.py migrate --noinput

echo "==> Ensuring default superuser exists..."
python manage.py create_default_superuser || true

echo "==> Collecting static files..."
python manage.py collectstatic --noinput

echo "==> Starting gunicorn..."
exec gunicorn geneam.wsgi:application --bind 0.0.0.0:8000 --workers 3
