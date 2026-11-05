"""Alta y edición de cámaras, zonas y balizas desde el dashboard (tarea 4.19).

Los roles y las validaciones corren con el almacenamiento JSON. Guardar, los
conflictos y el rol restringido de db/roles.sql necesitan PostgreSQL y se
saltan sin CASCOVISION_TEST_POSTGRES=1.
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
sys.path.insert(0, str(PROYECTO / "src" / "edge"))

from app import almacen  # noqa: E402
from app.main import app  # noqa: E402

SECRETO = "s" * 40
EDGE = {"Authorization": "Bearer token-edge"}
CAMARA = {"name": "Cámara patio", "rtsp_url": "rtsp://192.0.2.30/stream", "location": "Patio"}
ZONA = {"camera_id": "camara-01", "name": "Zona patio",
        "polygon": [[0.1, 0.1], [0.9, 0.1], [0.9, 0.9]], "suppression_s": 60}
BALIZA = {"name": "Baliza patio", "ip": "192.0.2.40", "duration_s": 10, "sound": "siren"}
RUTAS = [("/cameras/camara-09", CAMARA), ("/zones/zona-09", ZONA), ("/beacons/baliza-09", BALIZA)]

pytestmark = pytest.mark.sin_sesion


@pytest.fixture(autouse=True)
def entorno(tmp_path, monkeypatch):
    monkeypatch.setenv("JWT_SECRET", SECRETO)
    monkeypatch.setenv("EDGE_API_TOKEN", "token-edge")
    monkeypatch.setenv("CASCOVISION_STORAGE", "json")
    monkeypatch.setattr(almacen, "ARCHIVO", tmp_path / "incidents.json")


def _peticion(metodo: str, ruta: str, **kwargs) -> httpx.Response:
    async def request() -> httpx.Response:
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),
                                     base_url="http://test") as cliente:
            return await cliente.request(metodo, ruta, **kwargs)

    return asyncio.run(request())


def _token(rol: str = "admin") -> dict:
    datos = {"sub": almacen.ADMIN_LOCAL_ID, "email": "x@y.cl", "name": "X", "role": rol,
             "exp": datetime.now(timezone.utc) + timedelta(hours=1)}
    return {"Authorization": f"Bearer {jwt.encode(datos, SECRETO, algorithm='HS256')}"}


# ---------- roles y validación ----------

@pytest.mark.parametrize(("ruta", "cuerpo"), RUTAS)
def test_sin_token_responde_401(ruta, cuerpo) -> None:
    assert _peticion("PUT", ruta, json=cuerpo).status_code == 401


@pytest.mark.parametrize("rol", ["prevencionista", "supervisor"])
@pytest.mark.parametrize(("ruta", "cuerpo"), RUTAS)
def test_solo_el_admin_edita(rol, ruta, cuerpo) -> None:
    assert _peticion("PUT", ruta, json=cuerpo, headers=_token(rol)).status_code == 403


INVALIDOS = [
    ("/cameras/camara-09", {**CAMARA, "rtsp_url": "rtsp://usuario:clave@192.0.2.30/stream"}),
    ("/cameras/camara-09", {**CAMARA, "rtsp_url": "http://192.0.2.30/stream"}),
    ("/cameras/camara-09", {**CAMARA, "name": "   "}),
    ("/cameras/Camara 09", CAMARA),
    ("/zones/zona-09", {**ZONA, "polygon": [[0.1, 0.1], [0.9, 0.9]]}),
    ("/zones/zona-09", {**ZONA, "polygon": [[0.1, 0.1], [1.5, 0.1], [0.9, 0.9]]}),
    ("/zones/zona-09", {**ZONA, "suppression_s": 5}),
    ("/zones/zona-09", {**ZONA, "camera_id": "Cámara Uno"}),
    ("/beacons/baliza-09", {**BALIZA, "ip": "999.0.2.40"}),
    ("/beacons/baliza-09", {**BALIZA, "duration_s": 31}),
    ("/beacons/baliza-09", {**BALIZA, "sound": "bocina"}),
    ("/beacons/baliza-09", {**BALIZA, "message": "x" * 41}),
]


@pytest.mark.parametrize(("ruta", "cuerpo"), INVALIDOS)
def test_datos_invalidos_responden_422(ruta, cuerpo) -> None:
    assert _peticion("PUT", ruta, json=cuerpo, headers=_token()).status_code == 422


@pytest.mark.parametrize(("ruta", "cuerpo"), RUTAS)
def test_sin_postgres_responde_503(ruta, cuerpo) -> None:
    respuesta = _peticion("PUT", ruta, json=cuerpo, headers=_token())
    assert respuesta.status_code == 503
    assert respuesta.json()["detail"] == almacen.SOLO_POSTGRES_RECURSOS


# ---------- el agente toma la zona editada ----------

def test_el_agente_cambia_la_zona_sin_reiniciarse() -> None:
    import agente

    cfg = {"camera_id": "camara-01", "zone_id": "zona-norte", "zone_name": "Norte",
           "poligono": [[0, 0], [1, 0], [1, 1]], "baliza": {"url": "http://sim"}}

    class Monitor:
        zonas = None
        poligono = None

    monitor = Monitor()
    baliza = agente.ClienteBaliza("", "", "zona-norte", "Norte")
    nueva = {"camera_id": "camara-01", "zone_id": "zona-norte",
             "zone": {"name": "Norte nueva", "polygon": [[0, 0], [0.5, 0], [0.5, 1]]},
             "beacon": None}

    assert agente.recargar_zona(monitor, baliza, cfg, None) is False
    assert agente.recargar_zona(monitor, baliza, cfg, nueva) is True
    assert monitor.zonas == [{"id": "zona-norte",
                              "poligono": [(0.0, 0.0), (0.5, 0.0), (0.5, 1.0)]}]
    assert baliza.zona_nombre == "Norte nueva"
    assert cfg["baliza"]["url"] == "http://sim"  # la URL local no se pisa
    assert agente.recargar_zona(monitor, baliza, cfg, nueva) is False


# ---------- PostgreSQL ----------

@pytest.fixture
def pg(postgres_db, monkeypatch):
    monkeypatch.setenv("CASCOVISION_STORAGE", "postgres")
    return postgres_db


def test_postgres_crea_y_edita_camara_zona_y_baliza(pg) -> None:
    admin = _token()
    camara = _peticion("PUT", "/cameras/camara-09", json=CAMARA, headers=admin)
    assert camara.status_code == 200 and camara.json()["name"] == "Cámara patio"

    zona = {**ZONA, "camera_id": "camara-09"}
    assert _peticion("PUT", "/zones/zona-09", json=zona, headers=admin).status_code == 200
    baliza = _peticion("PUT", "/beacons/baliza-09", headers=admin,
                       json={**BALIZA, "zone_id": "zona-09", "message": "Use casco"})
    assert baliza.status_code == 200 and baliza.json()["online"] is False

    nuevo = [[0.2, 0.2], [0.8, 0.2], [0.8, 0.8], [0.2, 0.8]]
    editada = _peticion("PUT", "/zones/zona-09", json={**zona, "polygon": nuevo}, headers=admin)
    assert editada.json()["polygon"] == nuevo
    assert pg.execute("SELECT count(*) FROM zones WHERE id = 'zona-09'").fetchone()[0] == 1

    config = _peticion("GET", "/edge/config?camera_id=camara-09", headers=EDGE).json()
    assert config["zone"]["polygon"] == nuevo
    assert config["beacon"]["id"] == "baliza-09"
    assert config["beacon"]["ip"] == "192.0.2.40"


def test_postgres_conflictos_y_referencias(pg) -> None:
    admin = _token()
    # baliza-01 del seed ya usa 192.0.2.20 y la zona-norte.
    ip_tomada = _peticion("PUT", "/beacons/baliza-09", headers=admin,
                          json={**BALIZA, "ip": "192.0.2.20"})
    assert ip_tomada.status_code == 409
    assert ip_tomada.json()["detail"] == "Beacon IP is already in use"

    zona_tomada = _peticion("PUT", "/beacons/baliza-09", headers=admin,
                            json={**BALIZA, "zone_id": "zona-norte"})
    assert zona_tomada.status_code == 409
    assert zona_tomada.json()["detail"] == "Zone already has a beacon"

    sin_camara = _peticion("PUT", "/zones/zona-09", headers=admin,
                           json={**ZONA, "camera_id": "camara-inexistente"})
    assert sin_camara.status_code == 422


def test_postgres_el_rol_de_la_api_puede_editar(pg, monkeypatch) -> None:
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
        import os
        # Cada conexión de la API entra con el rol restringido.
        monkeypatch.setenv("PGOPTIONS", f"{os.getenv('PGOPTIONS', '')} -c role={nombres['cascovision']}")
        admin = _token()
        assert _peticion("PUT", "/cameras/camara-09", json=CAMARA, headers=admin).status_code == 200
        assert _peticion("PUT", "/zones/zona-09", headers=admin,
                         json={**ZONA, "camera_id": "camara-09"}).status_code == 200
        assert _peticion("PUT", "/beacons/baliza-09", headers=admin,
                         json={**BALIZA, "zone_id": "zona-09"}).status_code == 200
        latido = _peticion("PUT", "/edge/beacons/baliza-09/status", headers=EDGE,
                           json={"online": True})
        assert latido.status_code == 200 and latido.json()["online"] is True
    finally:
        pg.execute(sql.SQL("DROP OWNED BY {}, {}, {}").format(*map(sql.Identifier, nombres.values())))
        pg.execute(sql.SQL("DROP ROLE {}, {}, {}").format(*map(sql.Identifier, nombres.values())))
