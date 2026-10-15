# Recovery tool image: app code + PostgreSQL 16 client (pg_dump/pg_restore must match the server major version).
FROM postgres:16-bookworm
RUN apt-get update && apt-get install -y --no-install-recommends python3 python3-venv ca-certificates && rm -rf /var/lib/apt/lists/*
RUN python3 -m venv /venv
ENV PATH=/venv/bin:$PATH PYTHONUNBUFFERED=1
COPY backend/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt
COPY backend /app/backend
COPY scripts/e2e_sso.py /app/scripts/e2e_sso.py
WORKDIR /app/backend
ENTRYPOINT []
CMD ["python", "-m", "app.tools.recovery", "status"]
