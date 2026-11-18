"""Database connection: DATABASE_URL if set (CI, Docker), else an embedded PostgreSQL in .pgdata."""
from __future__ import annotations

import os
from pathlib import Path

import psycopg

ROOT = Path(__file__).resolve().parents[2]
SCHEMA_SQL = ROOT / "sql" / "schema.sql"


def database_url() -> str:
    url = os.environ.get("DATABASE_URL")
    if url:
        return url
    import pgserver  # local development only

    srv = pgserver.get_server(str(ROOT / ".pgdata"), cleanup_mode=None)
    return srv.get_uri()


def connect(autocommit: bool = False) -> psycopg.Connection:
    return psycopg.connect(database_url(), autocommit=autocommit, options="-c TimeZone=UTC")


def init_schema(conn: psycopg.Connection) -> None:
    conn.execute(SCHEMA_SQL.read_text())
    conn.execute((ROOT / "sql" / "indexes.sql").read_text())
    conn.commit()


def dbt_env() -> dict[str, str]:
    """Connection settings for dbt's profiles.yml (env_var based)."""
    from urllib.parse import parse_qs, urlparse

    u = urlparse(database_url())
    q = parse_qs(u.query)
    host = q.get("host", [u.hostname or "localhost"])[0]
    return {"PGHOST": host, "PGPORT": str(u.port or 5432), "PGUSER": u.username or "postgres",
            "PGPASSWORD": u.password or "", "PGDATABASE": (u.path or "/postgres").lstrip("/") or "postgres"}
