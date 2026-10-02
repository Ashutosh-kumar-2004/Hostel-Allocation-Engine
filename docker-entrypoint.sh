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

# 3. Synchronize demonstrator accounts and seed data
echo "Ensuring demonstrator accounts and seed state..."
python manage.py shell -c "
from django.contrib.auth import get_user_model
from django.core.management import call_command
User = get_user_model()
if not User.objects.filter(username='admin').exists() or not User.objects.filter(username='warden').exists():
    print('[Startup] Seeding demonstrator accounts...')
    call_command('seed_sample_data')
else:
    print('[Startup] Demonstrator accounts active.')
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
