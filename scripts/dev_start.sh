#!/usr/bin/env bash
# Start everything for local development / demo on this Mac.
#   ./scripts/dev_start.sh            start
#   ./scripts/dev_start.sh stop       stop server + gateway (databases keep running)
set -euo pipefail
cd "$(dirname "$0")/.."
PY="${CONDA_PREFIX_3FORM:-$(conda info --base)/envs/3form_WMS}/bin/python"
mkdir -p logs

if [[ "${1:-}" == "stop" ]]; then
  [[ -f logs/server.pid ]] && kill "$(cat logs/server.pid)" 2>/dev/null && echo "Server stopped"
  [[ -f logs/gateway.pid ]] && kill "$(cat logs/gateway.pid)" 2>/dev/null && echo "Gateway stopped"
  rm -f logs/server.pid logs/gateway.pid
  exit 0
fi

echo "1/5 Databases (Docker)…"
docker compose --env-file .env -f deploy/docker-compose.dev.yml up -d
echo "2/5 Database tables…"
"$PY" manage.py migrate --noinput >/dev/null
"$PY" manage.py init_mongo
echo "3/5 Screens…"
[[ -f frontend/dist/index.html ]] || (cd frontend && npm install --no-fund --no-audit && npm run build)
echo "4/5 Server on http://127.0.0.1:8008 …"
nohup "$PY" manage.py runserver 127.0.0.1:8008 --noreload > logs/server.out 2>&1 &
echo $! > logs/server.pid
echo "5/5 Site gateway (scanners)…"
nohup "$PY" -m site_gateway.gateway > logs/gateway.out 2>&1 &
echo $! > logs/gateway.pid
sleep 3
echo
echo "Ready:  http://127.0.0.1:8008/login   (PIC / Eng. Manager)"
echo "        http://127.0.0.1:8008/worker  (workstation tablet)"
echo "Stop:   ./scripts/dev_start.sh stop"
