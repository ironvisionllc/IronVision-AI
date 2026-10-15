"""Idempotent one-shot: create the Keycloak role + database on the existing Postgres server if missing. Never drops anything.

python -m app.tools.keycloak_db_init
Env: KEYCLOAK_DB_NAME (keycloak), KEYCLOAK_DB_USER (keycloak), KEYCLOAK_DB_PASSWORD (required),
     KEYCLOAK_DB_INIT_URL or DATABASE_URL (a role allowed to CREATE ROLE / CREATE DATABASE, e.g. the Postgres owner).
"""
import os
import re
import sys

import psycopg
from psycopg import sql

NAME = re.compile(r"^[a-z_][a-z0-9_]{0,62}$")


def init(admin_url: str, db_name: str, db_user: str, password: str) -> list[str]:
    if not NAME.match(db_name) or not NAME.match(db_user):
        raise ValueError("KEYCLOAK_DB_NAME / KEYCLOAK_DB_USER must be lowercase identifiers")
    done: list[str] = []
    with psycopg.connect(admin_url.replace("postgresql+psycopg:", "postgresql:"), autocommit=True) as c:
        if c.execute("SELECT 1 FROM pg_roles WHERE rolname=%s", (db_user,)).fetchone():
            c.execute(sql.SQL("ALTER ROLE {} WITH LOGIN PASSWORD {}").format(sql.Identifier(db_user), sql.Literal(password)))
            done.append(f"role {db_user}: exists (password synced from env)")
        else:
            c.execute(sql.SQL("CREATE ROLE {} WITH LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE PASSWORD {}")
                      .format(sql.Identifier(db_user), sql.Literal(password)))
            done.append(f"role {db_user}: created")
        if c.execute("SELECT 1 FROM pg_database WHERE datname=%s", (db_name,)).fetchone():
            done.append(f"database {db_name}: exists (untouched)")
        else:
            if not c.execute("SELECT rolsuper FROM pg_roles WHERE rolname=current_user").fetchone()[0]:
                c.execute(sql.SQL("GRANT {} TO CURRENT_USER").format(sql.Identifier(db_user)))  # PG16: CREATEROLE needs SET ROLE for OWNER
            c.execute(sql.SQL("CREATE DATABASE {} OWNER {}").format(sql.Identifier(db_name), sql.Identifier(db_user)))
            done.append(f"database {db_name}: created")
        c.execute(sql.SQL("REVOKE ALL ON DATABASE {} FROM PUBLIC").format(sql.Identifier(db_name)))
        c.execute(sql.SQL("GRANT ALL ON DATABASE {} TO {}").format(sql.Identifier(db_name), sql.Identifier(db_user)))
    return done


def main() -> int:
    pw = os.environ.get("KEYCLOAK_DB_PASSWORD", "")
    url = os.environ.get("KEYCLOAK_DB_INIT_URL") or os.environ.get("DATABASE_URL", "")
    if len(pw) < 16 or not url:
        print("[keycloak-db-init] KEYCLOAK_DB_PASSWORD (>=16 chars) and DATABASE_URL are required", file=sys.stderr)
        return 2
    try:
        for line in init(url, os.environ.get("KEYCLOAK_DB_NAME", "keycloak"), os.environ.get("KEYCLOAK_DB_USER", "keycloak"), pw):
            print(f"[keycloak-db-init] {line}")
    except Exception as e:  # noqa: BLE001 - operator-facing message
        print(f"[keycloak-db-init] FAILED: {type(e).__name__}: {str(e).splitlines()[0][:200]}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
