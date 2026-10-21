#!/bin/sh
# web | demo | scheduler | gateway | any manage.py command
set -e
cd /app
# Some hosts (e.g. Render) pass the full command, including this script's own path, as arguments.
[ "$1" = "/app/deploy/entrypoint.sh" ] && shift
case "$1" in
  web)
    python manage.py migrate --noinput
    python manage.py init_mongo
    python manage.py load_holidays
    python manage.py search_setup || echo "search_setup will retry later"
    exec gunicorn greaterwms.wsgi:application --bind 0.0.0.0:8008 --workers "${WEB_WORKERS:-3}" --threads 4 \
         --timeout 180 --access-logfile - --error-logfile -
    ;;
  demo)
    # Public website demo on one small free instance (PUBLIC_DEMO=1): the web app and the scheduler
    # share the container; the demo data is (re)built in the background so the page opens quickly.
    python manage.py migrate --noinput
    python manage.py init_mongo
    ( python manage.py public_demo_reset --if-stale; exec python manage.py scheduler ) &
    exec gunicorn greaterwms.wsgi:application --bind "0.0.0.0:${PORT:-8008}" --workers "${WEB_WORKERS:-2}" \
         --threads 4 --timeout 180 --access-logfile - --error-logfile -
    ;;
  scheduler) exec python manage.py scheduler ;;
  gateway)   exec python -m site_gateway.gateway ;;
  *)         exec python manage.py "$@" ;;
esac
