"""Edición y desactivación de usuarios por el administrador (CU-11, tarea 4.19).

Roles y validación corren con JSON. Guardar, desactivar y el rol restringido
de db/roles.sql necesitan PostgreSQL y se saltan sin CASCOVISION_TEST_POSTGRES=1.
"""

import asyncio
import re
import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx
import jwt
import pytest

PROYECTO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROYECTO / "src" / "api"))

from app import almacen  # noqa: E402
from app.main import app  # noqa: E402

SECRETO = "s" * 40
ADMIN_ID = "d2000000-0000-4000-8000-000000000101"  # admin del seed
OTRO = "d2000000-0000-4000-8000-000000000102"  # prevencionista del seed

pytestmark = pytest.mark.sin_sesion


@pytest.fixture(autouse=True)
def entorno(tmp_path, monkeypatch):
    monkeypatch.setenv("JWT_SECRET", SECRETO)
    monkeypatch.setenv("CASCOVISION_STORAGE", "json")
    monkeypatch.setattr(almacen, "ARCHIVO", tmp_path / "incidents.json")


def _peticion(metodo: str, ruta: str, **kwargs) -> httpx.Response:
    async def request() -> httpx.Response:
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),
                                     base_url="http://test") as cliente:
            return await cliente.request(metodo, ruta, **kwargs)

    return asyncio.run(request())


def _token(rol: str = "admin", sub: str = ADMIN_ID) -> dict:
    datos = {"sub": sub, "email": "x@y.cl", "name": "X", "role": rol,
             "exp": datetime.now(timezone.utc) + timedelta(hours=1)}
    return {"Authorization": f"Bearer {jwt.encode(datos, SECRETO, algorithm='HS256')}"}


# ---------- roles y validación ----------

def test_sin_token_401_y_otros_roles_403() -> None:
    assert _peticion("PATCH", f"/users/{OTRO}", json={"active": False}).status_code == 401
    for rol in ("prevencionista", "supervisor"):
        respuesta = _peticion("PATCH", f"/users/{OTRO}", json={"active": False}, headers=_token(rol))
        assert respuesta.status_code == 403


@pytest.mark.parametrize("cuerpo", [
    {"role": None}, {"active": None}, {"full_name": None}, {"full_name": "   "},
    {"role": "jefe"}, {"phone": "569123"}, {"active": "quizás"},
])
def test_datos_invalidos_422(cuerpo) -> None:
    assert _peticion("PATCH", f"/users/{OTRO}", json=cuerpo, headers=_token()).status_code == 422


def test_id_invalido_422() -> None:
    assert _peticion("PATCH", "/users/no-es-uuid", json={}, headers=_token()).status_code == 422


@pytest.mark.parametrize("cuerpo", [{"active": False}, {"role": "supervisor"}])
def test_el_admin_no_se_desactiva_ni_se_degrada(cuerpo) -> None:
    respuesta = _peticion("PATCH", f"/users/{ADMIN_ID}", json=cuerpo, headers=_token())
    assert respuesta.status_code == 409
    assert respuesta.json()["detail"] == "You cannot deactivate or demote yourself"


def test_sin_postgres_503() -> None:
    respuesta = _peticion("PATCH", f"/users/{OTRO}", json={"active": False}, headers=_token())
    assert respuesta.status_code == 503


# ---------- PostgreSQL ----------

@pytest.fixture
def pg(postgres_db, monkeypatch):
    monkeypatch.setenv("CASCOVISION_STORAGE", "postgres")
    return postgres_db


def test_postgres_edita_y_desactiva(pg) -> None:
    clave = uuid.uuid4().hex
    creado = _peticion("POST", "/users", headers=_token(), json={
        "email": "edicion@example.test", "full_name": "Ana", "role": "supervisor",
        "password": clave, "phone": "+56911111111"}).json()
    ruta = f"/users/{creado['id']}"

    editado = _peticion("PATCH", ruta, headers=_token(),
                        json={"full_name": " Ana Pérez ", "role": "prevencionista", "phone": None})
    assert editado.status_code == 200
    cuerpo = editado.json()
    assert (cuerpo["full_name"], cuerpo["role"], cuerpo["phone"], cuerpo["active"]) == \
        ("Ana Pérez", "prevencionista", None, True)
    assert _peticion("PATCH", ruta, headers=_token(), json={}).json() == cuerpo  # sin cambios

    login = {"email": "edicion@example.test", "password": clave}
    assert _peticion("POST", "/auth/login", json=login).status_code == 200
    assert _peticion("PATCH", ruta, headers=_token(), json={"active": False}).json()["active"] is False
    assert _peticion("POST", "/auth/login", json=login).status_code == 401  # ya no entra
    assert almacen.AlmacenPostgres().destinatarios_avisos() == []  # ni recibe avisos

    desconocido = _peticion("PATCH", f"/users/{uuid.uuid4()}", headers=_token(), json={"active": True})
    assert desconocido.status_code == 404


def test_postgres_el_rol_de_la_api_puede_editar(pg, monkeypatch) -> None:
    import os

    from psycopg import sql

    if not pg.execute("SELECT rolsuper FROM pg_roles WHERE rolname = current_user").fetchone()[0]:
        pytest.skip("Requiere un usuario PostgreSQL superusuario para cambiar de rol")
    sufijo = uuid.uuid4().hex[:10]
    nombres = {"cascovision": f"cv_api_{sufijo}", "auditoria_admin": f"cv_audit_{sufijo}",
               "prevencion_mantencion": f"cv_prev_{sufijo}"}
    fuente = (PROYECTO / "db" / "roles.sql").read_text(encoding="utf-8")
    for original, temporal in nombres.items():
        fuente = re.sub(rf"\b{original}\b", temporal, fuente)
    pg.execute(fuente, prepare=False)
    try:
        monkeypatch.setenv("PGOPTIONS", f"{os.getenv('PGOPTIONS', '')} -c role={nombres['cascovision']}")
        respuesta = _peticion("PATCH", f"/users/{OTRO}", headers=_token(),
                              json={"active": True, "phone": "+56922222222"})
        assert respuesta.status_code == 200 and respuesta.json()["active"] is True
        # El rol de la API no puede cambiar el correo ni la clave.
        assert pg.execute("SELECT has_column_privilege(%s, 'users', 'password_hash', 'UPDATE')",
                          (nombres["cascovision"],)).fetchone()[0] is False
        assert pg.execute("SELECT has_column_privilege(%s, 'users', 'email', 'UPDATE')",
                          (nombres["cascovision"],)).fetchone()[0] is False
    finally:
        pg.execute(sql.SQL("DROP OWNED BY {}, {}, {}").format(*map(sql.Identifier, nombres.values())))
        pg.execute(sql.SQL("DROP ROLE {}, {}, {}").format(*map(sql.Identifier, nombres.values())))
