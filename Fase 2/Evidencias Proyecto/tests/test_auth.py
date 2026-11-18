"""Login con JWT, roles, revisión de incidentes y evidencia (tarea 4.16).

Usan el almacenamiento JSON con el administrador local del entorno. Las de
PostgreSQL (crypt de pgcrypto e incident_events) se saltan sin
CASCOVISION_TEST_POSTGRES=1.
"""

import asyncio
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx
import jwt
import pytest

from app import almacen, auth
from app import main as api
from app.main import app

SECRETO = "s" * 40
ADMIN = {"email": "admin@cascovision.test", "password": "clave-larga-de-prueba"}
EDGE = {"Authorization": "Bearer token-edge"}
INCIDENTE = {
    "camera_id": "camara-01", "zone_id": "zona-norte",
    "detected_at": "2026-01-15T14:30:00Z", "violation_type": "missing_helmet",
    "confidence": 0.9, "evidence_path": "incidents/2026/01/15/incidente-001.jpg",
    "beacon_alert": {"status": "alerted", "latency_ms": 120},
}

pytestmark = pytest.mark.sin_sesion


@pytest.fixture(autouse=True)
def entorno(tmp_path, monkeypatch):
    monkeypatch.setenv("JWT_SECRET", SECRETO)
    monkeypatch.setenv("EDGE_API_TOKEN", "token-edge")
    monkeypatch.setenv("CASCOVISION_STORAGE", "json")
    monkeypatch.setenv("CASCOVISION_ADMIN_EMAIL", ADMIN["email"])
    monkeypatch.setenv("CASCOVISION_ADMIN_PASSWORD", ADMIN["password"])
    monkeypatch.setattr(almacen, "ARCHIVO", tmp_path / "incidents.json")
    monkeypatch.setattr(api, "RAIZ_EVIDENCIA", tmp_path)


def _peticion(metodo: str, ruta: str, **kwargs) -> httpx.Response:
    async def request() -> httpx.Response:
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),
                                     base_url="http://test") as cliente:
            return await cliente.request(metodo, ruta, **kwargs)

    return asyncio.run(request())


def _token(rol: str = "admin", **cambios) -> dict:
    datos = {"sub": almacen.ADMIN_LOCAL_ID, "email": "x@y.cl", "name": "X", "role": rol,
             "exp": datetime.now(timezone.utc) + timedelta(hours=1), **cambios}
    return {"Authorization": f"Bearer {jwt.encode(datos, SECRETO, algorithm='HS256')}"}


def _login(**cambios) -> httpx.Response:
    return _peticion("POST", "/auth/login", json={**ADMIN, **cambios})


def _incidente() -> str:
    return _peticion("POST", "/incidents", json=INCIDENTE, headers=EDGE).json()["id"]


# ---------- rutas protegidas ----------

PROTEGIDAS = [
    ("GET", "/incidents"), ("GET", "/incidents/x"), ("GET", "/incidents/x/evidence"),
    ("PATCH", "/incidents/x"), ("GET", "/cameras"), ("GET", "/cameras/x"),
    ("GET", "/zones"), ("GET", "/beacons"), ("GET", "/reports"), ("GET", "/config"),
    ("GET", "/users"), ("POST", "/users"), ("GET", "/auth/me"),
]


@pytest.mark.parametrize(("metodo", "ruta"), PROTEGIDAS)
def test_sin_token_responde_401(metodo, ruta) -> None:
    assert _peticion(metodo, ruta).status_code == 401


@pytest.mark.parametrize(("metodo", "ruta"), [("GET", "/incidents"), ("GET", "/beacons")])
def test_el_token_del_agente_no_abre_el_dashboard(metodo, ruta) -> None:
    assert _peticion(metodo, ruta, headers=EDGE).status_code == 401


def test_health_sigue_publico() -> None:
    assert _peticion("GET", "/health").status_code == 200


# ---------- login ----------

def test_login_entrega_token_que_abre_las_rutas() -> None:
    respuesta = _login()

    assert respuesta.status_code == 200
    cuerpo = respuesta.json()
    assert cuerpo["user"]["role"] == "admin"
    cabecera = {"Authorization": f"Bearer {cuerpo['access_token']}"}
    assert _peticion("GET", "/auth/me", headers=cabecera).json()["email"] == ADMIN["email"]
    assert _peticion("GET", "/incidents", headers=cabecera).status_code == 200


def test_login_ignora_mayusculas_del_correo() -> None:
    assert _login(email=ADMIN["email"].upper()).status_code == 200


@pytest.mark.parametrize("cambio", [{"password": "otra-clave-cualquiera"},
                                    {"email": "nadie@cascovision.test"}])
def test_login_con_datos_malos_responde_401(cambio) -> None:
    respuesta = _login(**cambio)

    assert respuesta.status_code == 401
    # Mismo mensaje en los dos casos: no revela qué correos existen.
    assert respuesta.json()["detail"] == "Invalid email or password"


def test_sin_jwt_secret_responde_503(monkeypatch) -> None:
    monkeypatch.setenv("JWT_SECRET", "corto")

    assert _login().status_code == 503


@pytest.mark.parametrize("cabecera", [
    _token(exp=datetime.now(timezone.utc) - timedelta(seconds=1)),
    {"Authorization": "Bearer " + jwt.encode({"sub": "x", "role": "admin",
                                              "exp": 9999999999}, "otro" * 10)},
    _token(rol="root"),
], ids=["vencido", "firma_ajena", "rol_desconocido"])
def test_token_invalido_responde_401(cabecera) -> None:
    assert _peticion("GET", "/incidents", headers=cabecera).status_code == 401


# ---------- roles ----------

def test_supervisor_consulta_pero_no_revisa() -> None:
    incident_id = _incidente()
    supervisor = _token("supervisor")

    assert _peticion("GET", f"/incidents/{incident_id}", headers=supervisor).status_code == 200
    respuesta = _peticion("PATCH", f"/incidents/{incident_id}", headers=supervisor,
                          json={"status": "reviewed"})
    assert respuesta.status_code == 403


@pytest.mark.parametrize("rol", ["prevencionista", "supervisor"])
def test_solo_el_admin_ve_usuarios_y_config(rol) -> None:
    assert _peticion("GET", "/users", headers=_token(rol)).status_code == 403
    assert _peticion("GET", "/config", headers=_token(rol)).status_code == 403


def test_admin_lista_usuarios_y_en_json_no_crea() -> None:
    admin = _token("admin")

    assert [u["email"] for u in _peticion("GET", "/users", headers=admin).json()] == [ADMIN["email"]]
    nuevo = {"email": "p@cascovision.test", "full_name": "P", "role": "prevencionista",
             "password": "x" * 12}
    assert _peticion("POST", "/users", headers=admin, json=nuevo).status_code == 503


# ---------- revisión de incidentes (RF-14) ----------

def test_prevencionista_revisa_el_incidente() -> None:
    incident_id = _incidente()
    respuesta = _peticion("PATCH", f"/incidents/{incident_id}", headers=_token("prevencionista"),
                          json={"status": "reviewed"})

    assert respuesta.status_code == 200
    assert respuesta.json()["status"] == "reviewed"


@pytest.mark.parametrize("estado", ["closed", "false_positive"])
def test_cerrar_exige_comentario(estado) -> None:
    incident_id = _incidente()
    ruta = f"/incidents/{incident_id}"

    assert _peticion("PATCH", ruta, headers=_token(), json={"status": estado}).status_code == 422
    con_comentario = {"status": estado, "comment": "Revisado en terreno"}
    assert _peticion("PATCH", ruta, headers=_token(), json=con_comentario).status_code == 200


def test_mismo_estado_responde_409() -> None:
    incident_id = _incidente()

    respuesta = _peticion("PATCH", f"/incidents/{incident_id}", headers=_token(),
                          json={"status": "open"})
    assert respuesta.status_code == 409


def test_revisar_incidente_inexistente_responde_404() -> None:
    respuesta = _peticion("PATCH", "/incidents/no-existe", headers=_token(),
                          json={"status": "reviewed"})
    assert respuesta.status_code == 404


# ---------- evidencia (RF-19) ----------

def test_evidencia_se_entrega_con_sesion(tmp_path) -> None:
    archivo = tmp_path / INCIDENTE["evidence_path"]
    archivo.parent.mkdir(parents=True)
    archivo.write_bytes(b"\xff\xd8jpeg")
    incident_id = _incidente()

    respuesta = _peticion("GET", f"/incidents/{incident_id}/evidence", headers=_token("supervisor"))

    assert respuesta.status_code == 200
    assert respuesta.headers["content-type"] == "image/jpeg"
    assert respuesta.content == b"\xff\xd8jpeg"


def test_evidencia_faltante_responde_404() -> None:
    incident_id = _incidente()

    assert _peticion("GET", f"/incidents/{incident_id}/evidence",
                     headers=_token()).status_code == 404


def test_evidencia_fuera_de_incidents_no_se_entrega(tmp_path) -> None:
    secreto = tmp_path / "secreto.jpg"
    secreto.write_bytes(b"no")
    almacen.ARCHIVO.write_text(
        '[{"id": "11111111-1111-4111-8111-111111111111", "evidence_path": "secreto.jpg"}]',
        encoding="utf-8",
    )

    respuesta = _peticion("GET", "/incidents/11111111-1111-4111-8111-111111111111/evidence",
                          headers=_token())
    assert respuesta.status_code == 404


# ---------- PostgreSQL ----------

MIGRACION_008 = Path(__file__).resolve().parents[1] / "db/migrations/008_autenticacion.sql"


@pytest.fixture
def pg(postgres_db, monkeypatch):
    postgres_db.execute(MIGRACION_008.read_text(encoding="utf-8"))
    monkeypatch.setenv("CASCOVISION_STORAGE", "postgres")
    return postgres_db


def test_postgres_crea_usuario_y_lo_autentica(pg) -> None:
    admin = _token("admin")
    nuevo = {"email": "Prev@CascoVision.test", "full_name": "Prevencionista", "role": "prevencionista",
             "password": "clave-del-prevencionista"}

    creado = _peticion("POST", "/users", headers=admin, json=nuevo)
    assert creado.status_code == 201
    assert creado.json()["email"] == "prev@cascovision.test"
    assert _peticion("POST", "/users", headers=admin, json=nuevo).status_code == 409

    hash_guardado = pg.execute(
        "SELECT password_hash FROM users WHERE email = 'prev@cascovision.test'"
    ).fetchone()[0]
    assert hash_guardado.startswith("$2") and nuevo["password"] not in hash_guardado

    login = _peticion("POST", "/auth/login",
                      json={"email": nuevo["email"], "password": nuevo["password"]})
    assert login.status_code == 200
    assert login.json()["user"]["role"] == "prevencionista"
    assert _peticion("POST", "/auth/login", json={"email": nuevo["email"],
                                                  "password": "mala"}).status_code == 401


def test_postgres_usuario_inactivo_no_entra(pg) -> None:
    # Los usuarios del seed están desactivados.
    pg.execute("UPDATE users SET password_hash = public.crypt('clave-del-seed', "
               "public.gen_salt('bf', 4)) WHERE email = 'admin@example.invalid'")

    respuesta = _peticion("POST", "/auth/login",
                          json={"email": "admin@example.invalid", "password": "clave-del-seed"})
    assert respuesta.status_code == 401


def test_postgres_revision_queda_en_incident_events(pg) -> None:
    incident_id = _incidente()
    revisor = _token("prevencionista", sub="d2000000-0000-4000-8000-000000000102")

    respuesta = _peticion("PATCH", f"/incidents/{incident_id}", headers=revisor,
                          json={"status": "closed", "comment": "Se entregó casco"})

    assert respuesta.status_code == 200
    evento = pg.execute(
        "SELECT user_id::text, from_status, to_status, comment FROM incident_events "
        "WHERE incident_id = %s", (incident_id,)
    ).fetchall()
    assert evento == [("d2000000-0000-4000-8000-000000000102", "open", "closed",
                       "Se entregó casco")]
    assert _peticion("PATCH", f"/incidents/{incident_id}", headers=revisor,
                     json={"status": "closed", "comment": "otra"}).status_code == 409
