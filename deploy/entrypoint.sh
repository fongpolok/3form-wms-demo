#!/bin/sh
# web | scheduler | gateway | any manage.py command
set -e
cd /app
case "$1" in
  web)
    python manage.py migrate --noinput
    python manage.py init_mongo
    python manage.py load_holidays
    python manage.py search_setup || echo "search_setup will retry later"
    exec gunicorn greaterwms.wsgi:application --bind 0.0.0.0:8008 --workers "${WEB_WORKERS:-3}" --threads 4 \
         --timeout 180 --access-logfile - --error-logfile -
    ;;
  scheduler) exec python manage.py scheduler ;;
  gateway)   exec python -m site_gateway.gateway ;;
  *)         exec python manage.py "$@" ;;
esac
