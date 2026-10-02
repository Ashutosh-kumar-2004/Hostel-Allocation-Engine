#!/bin/sh
set -e

echo "=========================================================="
echo "Hostel Allocation Engine Container Startup"
echo "ENVIRONMENT: ${ENVIRONMENT:-development}"
echo "=========================================================="

# 1. Run database migrations
echo "Applying database migrations..."
python manage.py migrate --noinput

# 2. Collect static files
echo "Collecting static assets..."
python manage.py collectstatic --noinput || true

# 3. Automatic seeding if database is empty
# Note: post_migrate signal and AutoSeedMiddleware also handle this,
# but calling it explicitly at startup provides clear container logs.
echo "Verifying database seed state..."
python manage.py shell -c "
from apps.inventory.models import Hostel
from apps.applications.models import AllocationCycle
from django.core.management import call_command
if not Hostel.objects.exists() or not AllocationCycle.objects.exists():
    print('[Startup] Database is not seeded. Seeding standard P03 v2.0 data...')
    call_command('seed_sample_data')
else:
    print('[Startup] Database is already seeded. Ready.')
" || true

# 4. Start Server
if [ "$ENVIRONMENT" = "development" ]; then
    echo "Starting development server on 0.0.0.0:8000..."
    exec python manage.py runserver 0.0.0.0:8000
else
    echo "Starting production Gunicorn server on 0.0.0.0:${PORT:-8000}..."
    exec gunicorn config.wsgi:application \
        --bind 0.0.0.0:${PORT:-8000} \
        --workers 2 \
        --threads 4 \
        --worker-class gthread \
        --timeout 60 \
        --access-logfile - \
        --error-logfile -
fi
