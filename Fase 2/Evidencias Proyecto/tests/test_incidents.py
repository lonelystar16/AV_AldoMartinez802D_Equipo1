"""Pruebas de las rutas de incidentes de la API."""

import asyncio
import sys
from pathlib import Path

import httpx
import pytest

API_SOURCE = Path(__file__).parents[1] / "src" / "api"
sys.path.insert(0, str(API_SOURCE))

from app import almacen  # noqa: E402
from app.main import app  # noqa: E402


@pytest.fixture(autouse=True)
def almacenamiento_temporal(tmp_path, monkeypatch):
    """Redirige la persistencia a un archivo aislado por prueba."""

    destino = tmp_path / "incidents.json"
    monkeypatch.setattr(almacen, "ARCHIVO", destino)
    return destino


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


def test_registrar_incidente_devuelve_201() -> None:
    respuesta = _peticion("POST", "/incidents", json=INCIDENTE)

    assert respuesta.status_code == 201
    cuerpo = respuesta.json()
    assert cuerpo["status"] == "open"
    assert cuerpo["id"]


def test_registrar_incidente_persiste_en_disco() -> None:
    _peticion("POST", "/incidents", json=INCIDENTE)

    guardados = almacen.cargar()
    assert len(guardados) == 1
    assert guardados[0]["violation_type"] == "missing_helmet"
    assert guardados[0]["evidence_path"] == INCIDENTE["evidence_path"]


def test_incidente_invalido_responde_422() -> None:
    cuerpo = {**INCIDENTE, "confidence": 1.7}

    respuesta = _peticion("POST", "/incidents", json=cuerpo)

    assert respuesta.status_code == 422


def test_violacion_desconocida_responde_422() -> None:
    cuerpo = {**INCIDENTE, "violation_type": "missing_gloves"}

    respuesta = _peticion("POST", "/incidents", json=cuerpo)

    assert respuesta.status_code == 422


def test_listar_incidentes_ordenado_por_fecha() -> None:
    _peticion("POST", "/incidents", json={**INCIDENTE,
                                          "detected_at": "2026-01-15T10:00:00Z"})
    _peticion("POST", "/incidents", json={**INCIDENTE,
                                          "detected_at": "2026-01-15T18:00:00Z"})

    respuesta = _peticion("GET", "/incidents")

    assert respuesta.status_code == 200
    fechas = [i["detected_at"] for i in respuesta.json()]
    assert fechas == ["2026-01-15T18:00:00Z", "2026-01-15T10:00:00Z"]


def test_listar_incidentes_filtra_por_zona() -> None:
    _peticion("POST", "/incidents", json=INCIDENTE)
    _peticion("POST", "/incidents", json={**INCIDENTE, "zone_id": "zona-sur"})

    respuesta = _peticion("GET", "/incidents", params={"zone_id": "zona-sur"})

    assert respuesta.status_code == 200
    assert len(respuesta.json()) == 1
    assert respuesta.json()[0]["zone_id"] == "zona-sur"


def test_obtener_incidente_inexistente_responde_404() -> None:
    respuesta = _peticion("GET", "/incidents/no-existe")

    assert respuesta.status_code == 404


def test_listar_incidentes_conserva_track_id() -> None:
    _peticion("POST", "/incidents", json={**INCIDENTE, "person_track_id": 7,
                                          "violation_types": ["missing_helmet",
                                                              "missing_reflective_vest"]})

    respuesta = _peticion("GET", "/incidents")

    cuerpo = respuesta.json()[0]
    assert cuerpo["person_track_id"] == 7
    assert cuerpo["violation_types"] == ["missing_helmet", "missing_reflective_vest"]


def test_health_sigue_disponible() -> None:
    respuesta = _peticion("GET", "/health")

    assert respuesta.status_code == 200
    assert respuesta.json() == {"status": "ok", "service": "cascovision-api"}
