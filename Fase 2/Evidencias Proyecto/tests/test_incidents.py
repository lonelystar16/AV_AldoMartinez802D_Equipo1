"""Pruebas de las rutas de incidentes de la API.

Por defecto corren contra el almacenamiento JSON en un archivo temporal. Con
CASCOVISION_TEST_POSTGRES=1 y las variables POSTGRES_* corren contra una base
PostgreSQL de pruebas. Cada caso crea un esquema aislado con las migraciones
y los catálogos; las tablas existentes de la base no se modifican.
"""

import asyncio
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

import httpx
import pytest

API_SOURCE = Path(__file__).parents[1] / "src" / "api"
sys.path.insert(0, str(API_SOURCE))

from app import almacen  # noqa: E402
from app.main import app  # noqa: E402

TOKEN = "token-de-prueba"
AUTH = {"Authorization": f"Bearer {TOKEN}"}
USAR_POSTGRES = os.getenv("CASCOVISION_TEST_POSTGRES") == "1"


@pytest.fixture(autouse=True)
def entorno(tmp_path, monkeypatch, request):
    """Token del agente Edge y almacenamiento aislado por prueba."""

    monkeypatch.setenv("EDGE_API_TOKEN", TOKEN)
    if USAR_POSTGRES:
        request.getfixturevalue("postgres_db")
        monkeypatch.setenv("CASCOVISION_STORAGE", "postgres")
    else:
        monkeypatch.setenv("CASCOVISION_STORAGE", "json")
        monkeypatch.setattr(almacen, "ARCHIVO", tmp_path / "incidents.json")


INCIDENTE = {
    "camera_id": "camara-01",
    "zone_id": "zona-norte",
    "detected_at": "2026-01-15T14:30:00Z",
    "violation_type": "missing_helmet",
    "confidence": 0.94,
    "evidence_path": "incidents/2026/01/15/incidente-001.jpg",
    "beacon_alert": {"status": "skipped_offline", "latency_ms": None},
}


def _peticion(metodo: str, ruta: str, **kwargs) -> httpx.Response:
    async def request() -> httpx.Response:
        transporte = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transporte,
                                     base_url="http://test") as cliente:
            return await cliente.request(metodo, ruta, **kwargs)

    return asyncio.run(request())


def _registrar(**cambios) -> httpx.Response:
    return _peticion("POST", "/incidents", json={**INCIDENTE, **cambios}, headers=AUTH)


# ---------- registro ----------

def test_registrar_incidente_devuelve_201() -> None:
    respuesta = _registrar()

    assert respuesta.status_code == 201
    cuerpo = respuesta.json()
    assert cuerpo["status"] == "open"
    assert cuerpo["id"]


def test_registrar_incidente_persiste() -> None:
    incident_id = _registrar().json()["id"]

    respuesta = _peticion("GET", f"/incidents/{incident_id}")

    assert respuesta.status_code == 200
    assert respuesta.json()["violation_type"] == "missing_helmet"
    assert respuesta.json()["violation_types"] == ["missing_helmet"]
    assert respuesta.json()["evidence_path"] == INCIDENTE["evidence_path"]


def test_registrar_conserva_violation_types_y_agrega_tipo_principal() -> None:
    incident_id = _registrar(violation_types=["missing_reflective_vest"]).json()["id"]

    respuesta = _peticion("GET", f"/incidents/{incident_id}")

    assert respuesta.status_code == 200
    assert respuesta.json()["violation_types"] == [
        "missing_reflective_vest", "missing_helmet",
    ]


def test_face_blurred_se_persiste_y_se_devuelve() -> None:
    incident_id = _registrar(face_blurred=True).json()["id"]

    respuesta = _peticion("GET", f"/incidents/{incident_id}")

    assert respuesta.status_code == 200
    assert respuesta.json()["face_blurred"] is True


def test_face_blurred_es_falso_por_defecto() -> None:
    incident_id = _registrar().json()["id"]

    respuesta = _peticion("GET", f"/incidents/{incident_id}")

    assert respuesta.status_code == 200
    assert respuesta.json()["face_blurred"] is False


def test_registrar_sin_token_responde_401() -> None:
    respuesta = _peticion("POST", "/incidents", json=INCIDENTE)

    assert respuesta.status_code == 401


def test_registrar_con_token_incorrecto_responde_401() -> None:
    respuesta = _peticion("POST", "/incidents", json=INCIDENTE,
                          headers={"Authorization": "Bearer otro"})

    assert respuesta.status_code == 401


def test_registrar_sin_token_configurado_responde_503(monkeypatch) -> None:
    monkeypatch.delenv("EDGE_API_TOKEN")

    respuesta = _registrar()

    assert respuesta.status_code == 503


def test_incidente_invalido_responde_422() -> None:
    assert _registrar(confidence=1.7).status_code == 422


def test_violacion_desconocida_responde_422() -> None:
    assert _registrar(violation_type="missing_gloves").status_code == 422


@pytest.mark.skipif(not USAR_POSTGRES, reason="Las FK se validan en PostgreSQL")
@pytest.mark.parametrize("campo", ["camera_id", "zone_id"])
def test_catalogo_desconocido_responde_422(campo: str) -> None:
    respuesta = _registrar(**{campo: "no-existe"})
    assert respuesta.status_code == 422
    assert respuesta.json()["detail"] == "Camera or zone is not configured"
    assert _peticion("GET", "/incidents").json() == []


def test_fecha_sin_zona_horaria_responde_422() -> None:
    assert _registrar(detected_at="2026-01-15T14:30:00").status_code == 422


@pytest.mark.parametrize("ruta", [
    "C:/Users/equipo/incidents/x.jpg",
    "/var/incidents/x.jpg",
    "incidents/../secreto.jpg",
    "incidents\\2026\\x.jpg",
])
def test_evidencia_con_ruta_no_relativa_responde_422(ruta: str) -> None:
    assert _registrar(evidence_path=ruta).status_code == 422


# ---------- ciclo de vida del aviso ----------

EPISODIO = "0f9a1c2e-1111-4222-8333-444455556666"


def _aviso(evento: str, **cambios) -> httpx.Response:
    """Aviso del agente Edge, marcando el momento del ciclo."""

    return _registrar(event=evento, episode_id=EPISODIO, **cambios)


def test_el_ping_actualiza_el_mismo_registro() -> None:
    """El ping no abre un incidente nuevo: mantiene vivo el ya registrado."""
    incident_id = _registrar(event="inicio", episode_id=EPISODIO).json()["id"]

    respuesta = _aviso("ping", occurred_at="2026-01-15T14:31:00Z", ping_count=1)

    assert respuesta.json()["id"] == incident_id
    assert len(_peticion("GET", "/incidents").json()) == 1


def test_el_ping_conserva_los_datos_del_inicio() -> None:
    """El aviso periódico repite los datos ya registrados, no los reemplaza."""
    _registrar(event="inicio", episode_id=EPISODIO, confidence=0.91)

    _aviso("ping", confidence=0.42, occurred_at="2026-01-15T14:31:00Z", ping_count=1)

    cuerpo = _peticion("GET", "/incidents").json()[0]
    assert cuerpo["confidence"] == 0.91
    assert cuerpo["evidence_path"] == INCIDENTE["evidence_path"]


def test_el_fin_registra_cuando_termino() -> None:
    incident_id = _registrar(event="inicio", episode_id=EPISODIO,
                             detected_at="2026-01-15T14:30:00Z").json()["id"]

    _aviso("fin", occurred_at="2026-01-15T14:33:00Z", ping_count=2)

    cuerpo = _peticion("GET", f"/incidents/{incident_id}").json()
    assert cuerpo["event"] == "fin"
    assert cuerpo["ended_at"].startswith("2026-01-15T14:33:00")
    assert cuerpo["started_at"].startswith("2026-01-15T14:30:00")


def test_un_ping_sin_inicio_no_pierde_el_registro() -> None:
    """Si el inicio quedó en la cola local, el ping crea el registro igual."""
    respuesta = _aviso("ping", occurred_at="2026-01-15T14:31:00Z", ping_count=1)

    assert respuesta.status_code == 201
    assert len(_peticion("GET", "/incidents").json()) == 1


def test_ping_sin_episode_id_responde_422() -> None:
    """Un ping sin episodio no podría actualizarse sobre el registro correcto."""
    assert _registrar(event="ping").status_code == 422


def test_cada_persona_tiene_su_propio_registro() -> None:
    """Aparecer otra persona sin EPP abre un registro aparte, de inmediato."""
    _registrar(event="inicio", episode_id=EPISODIO)
    otro = "9a8b7c6d-7777-4888-9999-000011112222"

    _registrar(event="inicio", episode_id=otro, zone_id="zona-sur")

    assert len(_peticion("GET", "/incidents").json()) == 2


# ---------- consulta ----------

def test_listar_incidentes_ordenado_por_fecha() -> None:
    _registrar(detected_at="2026-01-15T10:00:00Z")
    _registrar(detected_at="2026-01-15T18:00:00Z")

    respuesta = _peticion("GET", "/incidents")

    assert respuesta.status_code == 200
    fechas = [i["detected_at"] for i in respuesta.json()]
    assert fechas == ["2026-01-15T18:00:00Z", "2026-01-15T10:00:00Z"]


def test_listar_incidentes_filtra_por_zona() -> None:
    _registrar()
    _registrar(zone_id="zona-sur")

    respuesta = _peticion("GET", "/incidents", params={"zone_id": "zona-sur"})

    assert respuesta.status_code == 200
    assert len(respuesta.json()) == 1
    assert respuesta.json()[0]["zone_id"] == "zona-sur"


def test_listar_incidentes_pagina() -> None:
    for hora in range(10, 15):
        _registrar(detected_at=f"2026-01-15T{hora}:00:00Z")

    respuesta = _peticion("GET", "/incidents", params={"page": 2, "limit": 2})

    fechas = [i["detected_at"] for i in respuesta.json()]
    assert fechas == ["2026-01-15T12:00:00Z", "2026-01-15T11:00:00Z"]


def test_obtener_incidente_inexistente_responde_404() -> None:
    assert _peticion("GET", "/incidents/no-existe").status_code == 404


def test_listar_incidentes_conserva_track_id() -> None:
    _registrar(person_track_id=7,
               violation_types=["missing_helmet", "missing_reflective_vest"])

    cuerpo = _peticion("GET", "/incidents").json()[0]

    assert cuerpo["person_track_id"] == 7
    assert cuerpo["violation_types"] == ["missing_helmet", "missing_reflective_vest"]


def test_health_sigue_disponible() -> None:
    respuesta = _peticion("GET", "/health")

    assert respuesta.status_code == 200
    assert respuesta.json() == {"status": "ok", "service": "cascovision-api"}


if __name__ == "__main__":
    timestamp = datetime.now().astimezone().strftime("%Y%m%d_%H%M%S")
    log_dir = Path(__file__).resolve().parent / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / f"test_incidents_{timestamp}.log"
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "-vv", "-s", str(Path(__file__).resolve())],
        cwd=Path(__file__).resolve().parents[1],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    log_path.write_text(result.stdout, encoding="utf-8")
    print(result.stdout, end="")
    print(f"\nLog completo guardado en: {log_path}")
    raise SystemExit(result.returncode)
