"""Aplica migraciones pendientes y registra sus SHA-256 en schema_migrations."""

import hashlib
from getpass import getpass
from pathlib import Path
import sys

import psycopg

MIGRATIONS = Path(__file__).resolve().parent / "migrations"
PROJECT = MIGRATIONS.parent.parent
sys.path.insert(0, str(PROJECT / "src" / "api"))
from app.almacen import postgres_config


def main() -> None:
    config = postgres_config()
    config["user"] = input("PostgreSQL schema owner: ").strip()
    config["password"] = getpass("Password: ")
    with psycopg.connect(**config) as db:
        db.execute("""
            CREATE TABLE IF NOT EXISTS schema_migrations (
                filename TEXT PRIMARY KEY,
                sha256 TEXT NOT NULL,
                applied_at TIMESTAMPTZ NOT NULL DEFAULT now()
            )
        """)
        for path in sorted(MIGRATIONS.glob("[0-9][0-9][0-9]_*.sql")):
            source = path.read_bytes()
            checksum = hashlib.sha256(source).hexdigest()
            applied = db.execute(
                "SELECT sha256 FROM schema_migrations WHERE filename = %s", (path.name,)
            ).fetchone()
            if applied:
                if applied[0] != checksum:
                    raise RuntimeError(f"Migracion aplicada modificada: {path.name}")
                continue
            db.execute(source.decode("utf-8"), prepare=False)
            db.execute(
                "INSERT INTO schema_migrations (filename, sha256) VALUES (%s, %s)",
                (path.name, checksum),
            )
            db.commit()
            print(f"Aplicada: {path.name}")


if __name__ == "__main__":
    main()
