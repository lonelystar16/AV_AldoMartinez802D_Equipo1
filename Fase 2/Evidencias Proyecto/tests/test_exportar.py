"""Reporte en PDF y Excel, `GET /reports/export` (RF-15, tarea 4.12).

Corren con el almacenamiento JSON en un directorio temporal, sin PostgreSQL.
"""

import asyncio
import json
import re
import zipfile
from io import BytesIO

import httpx
import pytest

from app import almacen
from app import main as api
from app.main import app

EDGE = {"Authorization": "Bearer token-edge"}
RECURSOS = {
    "cameras": [{"id": "camara-01", "name": "Cámara acceso", "rtsp_url": "rtsp://192.0.2.10/x",
                 "active": True, "created_at": "2026-10-01T00:00:00+00:00"}],
    "zones": [
        # Nombres que un administrador podría escribir: una fórmula y caracteres fuera de Latin-1.
        {"id": "zona-formula", "camera_id": "camara-01", "name": "=1+1",
         "polygon": [[0, 0], [1, 0], [1, 1]], "suppression_s": 60, "active": True},
        {"id": "zona-emoji", "camera_id": "camara-01", "name": "Patio → grúa 🚧",
         "polygon": [[0, 0], [1, 0], [1, 1]], "suppression_s": 60, "active": True},
    ],
    "beacons": [],
}


@pytest.fixture(autouse=True)
def entorno(tmp_path, monkeypatch):
    monkeypatch.setenv("EDGE_API_TOKEN", "token-edge")
    monkeypatch.setenv("CASCOVISION_STORAGE", "json")
    monkeypatch.setattr(almacen, "ARCHIVO", tmp_path / "incidents.json")
    monkeypatch.setattr(almacen, "ARCHIVO_RECURSOS", tmp_path / "recursos.json")
    (tmp_path / "recursos.json").write_text(json.dumps(RECURSOS), encoding="utf-8")
    for zona, hora in (("zona-formula", "10"), ("zona-emoji", "11")):
        respuesta = _peticion("POST", "/incidents", headers=EDGE, json={
            "camera_id": "camara-01", "zone_id": zona,
            "detected_at": f"2026-01-15T{hora}:00:00Z", "violation_type": "missing_helmet",
            "confidence": 0.91, "evidence_path": f"incidents/2026/01/15/{zona}.jpg",
            "beacon_alert": {"status": "alerted", "latency_ms": 4},
        })
        assert respuesta.status_code == 201


def _peticion(metodo: str, ruta: str, **kwargs) -> httpx.Response:
    async def request() -> httpx.Response:
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),
                                     base_url="http://test") as cliente:
            return await cliente.request(metodo, ruta, **kwargs)

    return asyncio.run(request())


def _hojas(contenido: bytes) -> dict[str, str]:
    with zipfile.ZipFile(BytesIO(contenido)) as libro:
        return {n: libro.read(n).decode("utf-8") for n in libro.namelist() if n.endswith(".xml")}


def test_excel_trae_resumen_e_incidentes() -> None:
    respuesta = _peticion("GET", "/reports/export?formato=xlsx")

    assert respuesta.status_code == 200
    assert respuesta.headers["content-type"].startswith("application/vnd.openxmlformats")
    assert re.search(r'attachment; filename="reporte_cascovision_\d{8}_\d{4}\.xlsx"',
                     respuesta.headers["content-disposition"])
    assert respuesta.content[:2] == b"PK"
    hojas = _hojas(respuesta.content)
    textos = hojas["xl/sharedStrings.xml"]
    assert "Cámara acceso" in textos and "Sin casco" in textos and "Por turno" in textos
    # Cabecera más dos incidentes en la hoja Incidentes.
    assert len(re.findall(r"<row ", hojas["xl/worksheets/sheet2.xml"])) == 3


def test_excel_no_convierte_un_nombre_en_formula() -> None:
    hojas = _hojas(_peticion("GET", "/reports/export?formato=xlsx").content)

    assert "=1+1" in hojas["xl/sharedStrings.xml"]
    assert all("<f>" not in xml for n, xml in hojas.items() if n.startswith("xl/worksheets/"))


def test_pdf_se_genera_aunque_un_nombre_no_sea_latin1() -> None:
    respuesta = _peticion("GET", "/reports/export?formato=pdf")

    assert respuesta.status_code == 200
    assert respuesta.headers["content-type"] == "application/pdf"
    assert respuesta.content.startswith(b"%PDF")


def test_la_exportacion_respeta_los_filtros() -> None:
    respuesta = _peticion("GET", "/reports/export?formato=xlsx&zone_id=zona-emoji")
    hojas = _hojas(respuesta.content)

    assert len(re.findall(r"<row ", hojas["xl/worksheets/sheet2.xml"])) == 2
    assert "Patio → grúa 🚧" in hojas["xl/sharedStrings.xml"]  # el filtro aplicado, en palabras


def test_avisa_si_el_archivo_no_trae_todo(monkeypatch) -> None:
    monkeypatch.setattr(api, "LIMITE_EXPORTACION", 1)
    hojas = _hojas(_peticion("GET", "/reports/export?formato=xlsx").content)

    assert "Se incluyen 1 de 2 incidentes" in hojas["xl/sharedStrings.xml"]


@pytest.mark.parametrize("consulta", [
    "formato=csv",
    "formato=pdf&desde=2026-01-16T00:00:00Z&hasta=2026-01-15T00:00:00Z",
    "formato=pdf&desde=2026-01-15T00:00:00",
])
def test_parametros_invalidos_responden_422(consulta) -> None:
    assert _peticion("GET", f"/reports/export?{consulta}").status_code == 422


@pytest.mark.sin_sesion
def test_sin_sesion_responde_401() -> None:
    assert _peticion("GET", "/reports/export?formato=pdf").status_code == 401
