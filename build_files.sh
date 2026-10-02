#!/usr/bin/env bash
# Vercel Build Script for Hostel Allocation Engine
set -e

echo "Installing requirements..."
python3 -m pip install -r requirements.txt

echo "Collecting static assets..."
python3 manage.py collectstatic --noinput --clear

echo "Vercel build complete!"
