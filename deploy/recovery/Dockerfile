# Recovery tool image: recovery code + PostgreSQL 16 client (pg_dump/pg_restore must match the server major version).
# Python deps: deploy/recovery/requirements.recovery.txt = minimal subset of backend/requirements.prod.txt (same pins),
# public PyPI only (never backend/requirements.txt: it holds Emergent preview packages from a private index).
FROM postgres:16-bookworm
# hadolint ignore=DL3008
RUN apt-get update && apt-get install -y --no-install-recommends python3 python3-venv ca-certificates && rm -rf /var/lib/apt/lists/*
RUN python3 -m venv /venv
ENV PATH=/venv/bin:$PATH PYTHONUNBUFFERED=1 PIP_DISABLE_PIP_VERSION_CHECK=1
COPY deploy/recovery/requirements.recovery.txt /app/requirements.recovery.txt
RUN pip install --no-cache-dir --index-url https://pypi.org/simple -r /app/requirements.recovery.txt
COPY backend /app/backend
COPY scripts/e2e_sso.py /app/scripts/e2e_sso.py
WORKDIR /app/backend
RUN python -m app.tools.selfcheck --recovery
ENTRYPOINT []
CMD ["python", "-m", "app.tools.recovery", "status"]
