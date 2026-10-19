# 3Form WMS / MES / APS - one image for the web app, the scheduler and the site gateway.
#   docker build -f deploy/Dockerfile -t 3form-wms:3.5.0 .
FROM node:20-alpine AS web
WORKDIR /web
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

FROM python:3.11-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_DISABLE_PIP_VERSION_CHECK=1
# pg_dump must be >= the PostgreSQL server (16): use the PostgreSQL project's apt repository.
RUN apt-get update \
 && apt-get install -y --no-install-recommends postgresql-common ca-certificates \
 && /usr/share/postgresql-common/pgdg/apt.postgresql.org.sh -y \
 && apt-get install -y --no-install-recommends postgresql-client-16 \
 && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
COPY --from=web /web/dist /app/frontend/dist
RUN useradd --create-home --uid 1000 app \
 && mkdir -p logs media backups exports \
 && chown -R app:app /app \
 && chmod +x deploy/entrypoint.sh
USER app
EXPOSE 8008
ENTRYPOINT ["/app/deploy/entrypoint.sh"]
CMD ["web"]
