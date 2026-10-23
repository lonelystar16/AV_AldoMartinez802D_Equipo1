"""PostgreSQL de pruebas: cada caso usa un esquema propio y lo elimina al salir."""

import os
import sys
from pathlib import Path
from uuid import uuid4

import pytest

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT / "src" / "api"))


@pytest.fixture
def db_before_foreign_keys(monkeypatch):
    if os.getenv("CASCOVISION_TEST_POSTGRES") != "1":
        pytest.skip("Requiere CASCOVISION_TEST_POSTGRES=1 y una base PostgreSQL de pruebas")

    import psycopg
    from psycopg import sql
    from app.almacen import postgres_config

    schema = f"test_cascovision_{uuid4().hex}"
    with psycopg.connect(**postgres_config(), autocommit=True) as connection:
        connection.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(schema)))
        try:
            connection.execute(sql.SQL("SET search_path TO {}").format(sql.Identifier(schema)))
            options = os.getenv("PGOPTIONS", "")
            monkeypatch.setenv("PGOPTIONS", f"{options} -c search_path={schema}".strip())
            for path in sorted((PROJECT / "db" / "migrations").glob("00[1-4]_*.sql")):
                connection.execute(path.read_text(encoding="utf-8"))
            connection.execute((PROJECT / "db/seed/001_catalogos.sql").read_text(encoding="utf-8"))
            yield connection
        finally:
            connection.rollback()
            connection.execute(sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(schema)))


@pytest.fixture
def postgres_db(db_before_foreign_keys):
    path = PROJECT / "db/migrations/005_claves_incidentes.sql"
    db_before_foreign_keys.execute(path.read_text(encoding="utf-8"))
    return db_before_foreign_keys
