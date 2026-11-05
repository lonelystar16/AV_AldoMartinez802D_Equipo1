"""PostgreSQL de pruebas: cada caso usa un esquema propio y lo elimina al salir."""

import os
import sys
from pathlib import Path
from uuid import uuid4

import pytest

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT / "src" / "api"))

# Administrador del seed (db/seed/001_catalogos.sql): existe en PostgreSQL, así
# que incident_events puede referenciarlo.
USUARIO_PRUEBA = {"id": "d2000000-0000-4000-8000-000000000101",
                  "email": "admin@example.invalid", "full_name": "Administrador demo",
                  "role": "admin"}


@pytest.fixture(autouse=True)
def sesion_iniciada(request):
    """Las pruebas de cada ruta entran como admin sin pasar por el login.

    El login, los roles y el rechazo sin token se prueban en test_auth.py, cuyos
    casos llevan la marca ``sin_sesion`` para usar la autenticación real.
    """
    main = sys.modules.get("app.main")
    if main is None or request.node.get_closest_marker("sin_sesion"):
        yield
        return
    from app.auth import usuario_actual

    main.app.dependency_overrides[usuario_actual] = lambda: dict(USUARIO_PRUEBA)
    yield
    main.app.dependency_overrides.pop(usuario_actual, None)


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
    for name in ("005_claves_incidentes.sql", "006_integridad_y_auditoria.sql"):
        path = PROJECT / "db/migrations" / name
        db_before_foreign_keys.execute(path.read_text(encoding="utf-8"))
    return db_before_foreign_keys
