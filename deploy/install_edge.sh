#!/usr/bin/env bash
# One-time set-up on a fresh Ubuntu Server 24.04 LTS box (edge box, or cloud VM with "cloud").
#   sudo ./deploy/install_edge.sh            # edge box (everything on site)
#   sudo ./deploy/install_edge.sh cloud      # cloud VM (core only; factory runs deploy/site)
set -euo pipefail
MODE="${1:-edge}"
cd "$(dirname "$0")/.."
[[ $EUID -eq 0 ]] || { echo "Run with sudo."; exit 1; }

echo "1/4 Docker"
apt-get update -qq
apt-get install -y -qq docker.io docker-compose-v2 python3 openssl >/dev/null
systemctl enable --now docker

echo "2/4 Secrets -> deploy/.env"
if [[ ! -f deploy/.env ]]; then
  cp "deploy/${MODE}.env.example" deploy/.env
  rnd() { openssl rand -base64 36 | tr -d '/+=' | cut -c1-40; }
  fernet=$(python3 -c "import base64,os;print(base64.urlsafe_b64encode(os.urandom(32)).decode())")
  sed -i "s|^DJANGO_SECRET_KEY=.*|DJANGO_SECRET_KEY=$(rnd)$(rnd)|; s|^POSTGRES_PASSWORD=.*|POSTGRES_PASSWORD=$(rnd)|; \
          s|^GATEWAY_TOKEN=.*|GATEWAY_TOKEN=$(rnd)|; s|^INTEGRATION_KEY=.*|INTEGRATION_KEY=${fernet}|" deploy/.env
  chmod 600 deploy/.env
  echo "   Created deploy/.env. Edit SITE_ADDRESS / ALLOWED_HOSTS / CSRF_TRUSTED_ORIGINS now, then re-run."
  echo "   KEEP A COPY OF deploy/.env SOMEWHERE SAFE (INTEGRATION_KEY unlocks stored API keys)."
  exit 0
fi

echo "3/4 Build and start (${MODE})"
docker compose --env-file deploy/.env -f "deploy/docker-compose.${MODE}.yml" up -d --build

echo "4/4 Waiting for the app"
for i in $(seq 1 60); do
  docker compose --env-file deploy/.env -f "deploy/docker-compose.${MODE}.yml" exec -T app \
    python -c "import urllib.request;urllib.request.urlopen('http://127.0.0.1:8008/api/v1/health')" 2>/dev/null && break
  sleep 5
done
echo
echo "Running. Next: create the first PIC account:"
echo "  docker compose --env-file deploy/.env -f deploy/docker-compose.${MODE}.yml exec app \\"
echo "    python manage.py create_pic --company \"Client Ltd\" --username pic1 --staff-id P001 --name \"First PIC\""
