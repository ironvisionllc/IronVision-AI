FROM python:3.11-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /srv/backend
# hadolint ignore=DL3008
RUN apt-get update && apt-get install -y --no-install-recommends curl && rm -rf /var/lib/apt/lists/*
COPY requirements.prod.txt .
RUN pip install -r requirements.prod.txt
COPY . .
# build-time gate: every module imports (incl. uvicorn) + uvicorn loads app.main:app and /api/v1/health/live answers 200 – scrubbed
# env, network blocked, no DB (python -m app.tools.selfcheck). Also the rehearsal-backend image (deploy/compose/recovery.yml).
RUN python -m app.tools.selfcheck --startup
RUN useradd -r -u 10001 aegis && mkdir -p /data/storage && chown -R aegis /srv/backend /data
USER aegis
EXPOSE 8001
HEALTHCHECK --interval=15s --timeout=5s --retries=10 CMD curl -fsS http://localhost:8001/api/v1/health || exit 1
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8001", "--proxy-headers"]
