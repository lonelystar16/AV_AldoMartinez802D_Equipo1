"""Pruebas de los recursos (cámaras, zonas, balizas) y del reporte.

Cubre las rutas nuevas de `main.py`: el catálogo que consulta el dashboard,
la configuración que descarga el agente Edge, el heartbeat de la baliza y
`GET /reports`.

Como `tests/test_incidents.py`, corren contra el almacenamiento JSON en un
archivo temporal, así que no necesitan PostgreSQL.
"""

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import httpx
import pytest

API_SOURCE = Path(__file__).parents[1] / "src" / "api"
sys.path.insert(0, str(API_SOURCE))

from app import almacen  # noqa: E402
from app.main import app  # noqa: E402

TOKEN = "token-de-prueba"
AUTH = {"Authorization": f"Bearer {TOKEN}"}

# Dos cámaras y dos zonas, para que los filtros tengan algo que descartar.
RECURSOS = {
    "cameras": [
        {
            "id": "camara-01",
            "name": "Camara 01 - Entrada norte",
            "rtsp_url": "rtsp://192.168.50.10/stream",
            "location": "Entrada norte",
            "active": True,
            "last_frame_at": None,
            "created_at": "2026-10-01T00:00:00+00:00",
        },
        {
            "id": "camara-02",
            "name": "Camara 02 - Anden",
            "rtsp_url": "rtsp://192.168.50.11/stream",
            "location": "Anden",
            "active": False,
            "last_frame_at": None,
            "created_at": "2026-10-02T00:00:00+00:00",
        },
    ],
    "zones": [
        {
            "id": "zona-norte",
            "camera_id": "camara-01",
            "name": "Zona Norte",
            "polygon": [[0.0, 0.0], [1.0, 0.0], [1.0, 1.0]],
            "suppression_s": 60,
            "active": True,
        },
        {
            "id": "zona-sur",
            "camera_id": "camara-02",
            "name": "Zona Sur",
            "polygon": [[0.0, 0.0], [1.0, 0.0], [1.0, 1.0]],
            "suppression_s": 60,
            "active": True,
        },
    ],
    "beacons": [
        {
            "id": "baliza-01",
            "zone_id": "zona-norte",
            "name": "Baliza Norte",
            "ip": "127.0.0.1",
            "duration_s": 10,
            "sound": "siren",
            "message": "USO OBLIGATORIO DE CASCO",
            "online": False,
            "battery_pct": None,
            "last_seen_at": None,
        },
    ],
}


def peticion(metodo: str, ruta: str, **kwargs) -> httpx.Response:
    async def request() -> httpx.Response:
        transporte = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transporte,
                                     base_url="http://test") as cliente:
            return await cliente.request(metodo, ruta, **kwargs)

    return __import__("asyncio").run(request())


def _instante(valor: str) -> datetime:
    """Parsea una fecha de la API, que serializa UTC con la forma `Z`."""

    return datetime.fromisoformat(valor.replace("Z", "+00:00"))


def _utc(*args) -> datetime:
    return datetime(*args, tzinfo=timezone.utc)


@pytest.fixture(autouse=True)
def entorno(tmp_path, monkeypatch):
    """Token del agente y dos archivos temporales: incidentes y recursos."""

    monkeypatch.setenv("EDGE_API_TOKEN", TOKEN)
    monkeypatch.delenv("CASCOVISION_STORAGE", raising=False)
    monkeypatch.setattr(almacen, "ARCHIVO", tmp_path / "incidents.json")
    monkeypatch.setattr(almacen, "ARCHIVO_RECURSOS", tmp_path / "recursos.json")
    (tmp_path / "recursos.json").write_text(json.dumps(RECURSOS), encoding="utf-8")


def _incidente(**kwargs) -> dict:
    """Registra un aviso con `event="inicio"` y devuelve su respuesta."""

    cuerpo = {
        "camera_id": "camara-01",
        "zone_id": "zona-norte",
        "detected_at": "2026-10-28T08:00:00+00:00",
        "violation_type": "missing_helmet",
        "violation_types": ["missing_helmet"],
        "confidence": 0.91,
        "evidence_path": "evidencias/a.jpg",
        "beacon_alert": {"status": "skipped_offline", "latency_ms": None},
        # Sin esto cada aviso quedaría sin episodio y no habría nada que
        # cerrar; además una persona no EPP abriría dos registros.
        "episode_id": str(uuid4()),
    }
    cuerpo.update(kwargs)
    respuesta = peticion("POST", "/incidents", json=cuerpo, headers=AUTH)
    assert respuesta.status_code == 201, respuesta.text
    return respuesta.json()


def _cerrar(episode_id: str, momento: str) -> None:
    """Cierra el episodio en el instante dado, fijando así su `ended_at`."""

    respuesta = peticion(
        "POST",
        "/incidents",
        json={
            "camera_id": "camara-01",
            "zone_id": "zona-norte",
            "detected_at": "2026-10-28T08:00:00+00:00",
            "violation_type": "missing_helmet",
            "confidence": 0.91,
            "evidence_path": "evidencias/a.jpg",
            "beacon_alert": {"status": "skipped_offline", "latency_ms": None},
            "event": "fin",
            "episode_id": episode_id,
            # `occurred_at` es lo que la API guarda como `ended_at`.
            "occurred_at": momento,
        },
        headers=AUTH,
    )
    assert respuesta.status_code == 201, respuesta.text


# ==================== Cámaras ====================


def test_camaras_devuelve_el_catalogo() -> None:
    ids = [c["id"] for c in peticion("GET", "/cameras").json()]

    assert ids == ["camara-01", "camara-02"]


def test_camara_por_id() -> None:
    cuerpo = peticion("GET", "/cameras/camara-02").json()

    assert cuerpo["active"] is False
    assert cuerpo["location"] == "Anden"


def test_camara_inexistente_responde_404() -> None:
    assert peticion("GET", "/cameras/camara-99").status_code == 404


def test_catalogo_vacio_devuelve_lista_vacia(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(almacen, "ARCHIVO_RECURSOS", tmp_path / "no-existe.json")

    # Un catálogo vacío es un estado válido, no una falla: la API responde 200
    # con lista vacía y el dashboard muestra que aún no hay nada cargado.
    assert peticion("GET", "/cameras").json() == []


# ==================== Zonas ====================


def test_zonas_sin_filtro_devuelve_todas() -> None:
    ids = [z["id"] for z in peticion("GET", "/zones").json()]

    assert ids == ["zona-norte", "zona-sur"]


def test_zonas_por_camara() -> None:
    cuerpo = peticion("GET", "/zones?camera_id=camara-02").json()

    assert [z["id"] for z in cuerpo] == ["zona-sur"]
    assert cuerpo[0]["camera_id"] == "camara-02"


def test_zonas_trae_el_poligono() -> None:
    zonas = peticion("GET", "/zones?camera_id=camara-01").json()

    assert zonas[0]["polygon"] == [[0.0, 0.0], [1.0, 0.0], [1.0, 1.0]]


def test_zonas_sin_camara_responde_lista_vacia() -> None:
    assert peticion("GET", "/zones?camera_id=camara-99").json() == []


# ==================== Balizas ====================


def test_balizas_arrancan_en_linea_en_falso() -> None:
    cuerpo = peticion("GET", "/beacons").json()

    assert [b["id"] for b in cuerpo] == ["baliza-01"]
    # Mientras no exista el firmware, `online` es false: es el estado real.
    assert cuerpo[0]["online"] is False


# ==================== Configuración del agente ====================


def test_edge_config_requiere_token() -> None:
    assert peticion("GET", "/edge/config?camera_id=camara-01").status_code == 401


def test_edge_config_entrega_camara_zona_y_baliza() -> None:
    cuerpo = peticion(
        "GET", "/edge/config?camera_id=camara-01", headers=AUTH
    ).json()

    assert cuerpo["camera_id"] == "camara-01"
    assert cuerpo["zone_id"] == "zona-norte"
    assert cuerpo["zone"]["polygon"] == [[0.0, 0.0], [1.0, 0.0], [1.0, 1.0]]
    assert cuerpo["beacon"]["id"] == "baliza-01"
    assert cuerpo["beacon"]["ip"] == "127.0.0.1"


def test_edge_config_sin_baliza_devuelve_null() -> None:
    almacen.ARCHIVO_RECURSOS.write_text(
        json.dumps(dict(RECURSOS, beacons=[])), encoding="utf-8"
    )

    cuerpo = peticion(
        "GET", "/edge/config?camera_id=camara-01", headers=AUTH
    ).json()

    assert cuerpo["zone_id"] == "zona-norte"
    assert cuerpo["beacon"] is None


def test_edge_config_camara_inexistente_responde_404() -> None:
    respuesta = peticion(
        "GET", "/edge/config?camera_id=camara-99", headers=AUTH
    )

    assert respuesta.status_code == 404


def test_edge_config_camara_sin_zona_responde_404() -> None:
    almacen.ARCHIVO_RECURSOS.write_text(
        json.dumps(dict(RECURSOS, zones=[])), encoding="utf-8"
    )

    respuesta = peticion(
        "GET", "/edge/config?camera_id=camara-01", headers=AUTH
    )

    assert respuesta.status_code == 404


# ==================== Heartbeat de la baliza ====================


def test_heartbeat_requiere_token() -> None:
    respuesta = peticion(
        "PUT", "/edge/beacons/baliza-01/status", json={"online": True}
    )

    assert respuesta.status_code == 401


def test_heartbeat_marca_la_baliza_en_linea() -> None:
    cuerpo = peticion(
        "PUT",
        "/edge/beacons/baliza-01/status",
        json={"online": True, "battery_pct": 87},
        headers=AUTH,
    ).json()

    assert cuerpo["online"] is True
    assert cuerpo["battery_pct"] == 87
    assert cuerpo["last_seen_at"] is not None

    # El cambio sobrevive a la consulta posterior.
    assert peticion("GET", "/beacons").json()[0]["online"] is True


def test_heartbeat_bateria_fuera_de_rango_responde_422() -> None:
    respuesta = peticion(
        "PUT",
        "/edge/beacons/baliza-01/status",
        json={"online": True, "battery_pct": 150},
        headers=AUTH,
    )

    assert respuesta.status_code == 422


def test_heartbeat_baliza_inexistente_responde_404() -> None:
    respuesta = peticion(
        "PUT", "/edge/beacons/baliza-99/status", json={"online": True},
        headers=AUTH,
    )

    assert respuesta.status_code == 404


# ==================== Reporte ====================


def test_reporte_vacio_devuelve_totales_en_cero() -> None:
    cuerpo = peticion("GET", "/reports").json()

    assert cuerpo["total"] == 0
    assert cuerpo["incidentes"] == []
    assert cuerpo["resumen"]["en_curso"] == 0
    assert cuerpo["resumen"]["terminados"] == 0
    assert cuerpo["resumen"]["duracion_media_s"] is None
    assert cuerpo["resumen"]["por_estado"] == {
        "open": 0, "reviewed": 0, "closed": 0, "false_positive": 0,
    }
    assert cuerpo["resumen"]["balizas"] == {
        "alerted": 0, "failed": 0, "skipped_offline": 0,
    }


def test_reporte_trae_inicio_fin_camara_y_zona() -> None:
    _incidente()

    fila = peticion("GET", "/reports").json()["incidentes"][0]

    assert _instante(fila["started_at"]) == _utc(2026, 10, 28, 8, 0, 0)
    assert fila["ended_at"] is None
    assert fila["camera_id"] == "camara-01"
    assert fila["zone_id"] == "zona-norte"


def test_reporte_calcula_la_duracion_al_cerrar() -> None:
    incidente = _incidente()
    _cerrar(incidente["episode_id"], "2026-10-28T08:04:30+00:00")

    fila = peticion("GET", "/reports").json()["incidentes"][0]

    assert _instante(fila["ended_at"]) == _utc(2026, 10, 28, 8, 4, 30)
    assert fila["duration_s"] == 270.0


def test_reporte_suma_los_totales_del_periodo() -> None:
    _incidente()
    otro = _incidente(zone_id="zona-sur", camera_id="camara-02")
    _cerrar(otro["episode_id"], "2026-10-28T09:00:00+00:00")

    cuerpo = peticion("GET", "/reports").json()

    assert cuerpo["total"] == 2
    assert cuerpo["resumen"]["total"] == 2
    assert cuerpo["resumen"]["en_curso"] == 1
    assert cuerpo["resumen"]["terminados"] == 1
    # El aviso terminó, pero la revisión la hace una persona: hasta que alguien
    # clasifique el caso, los dos siguen como `open`.
    assert cuerpo["resumen"]["por_estado"] == {
        "open": 2, "reviewed": 0, "closed": 0, "false_positive": 0,
    }
    assert cuerpo["resumen"]["balizas"]["skipped_offline"] == 2
    # Solo el terminado tiene duración: 1 h = 3600 s.
    assert cuerpo["resumen"]["duracion_media_s"] == 3600.0


def test_reporte_el_total_no_se_limita_a_la_pagina() -> None:
    for _ in range(5):
        _incidente()

    cuerpo = peticion("GET", "/reports?limit=2").json()

    assert len(cuerpo["incidentes"]) == 2
    assert cuerpo["total"] == 5
    assert cuerpo["resumen"]["total"] == 5


def test_reporte_filtra_por_camara_y_zona() -> None:
    _incidente()
    _incidente(zone_id="zona-sur", camera_id="camara-02")

    por_camara = peticion("GET", "/reports?camera_id=camara-02").json()
    por_zona = peticion("GET", "/reports?zone_id=zona-norte").json()

    assert [f["zone_id"] for f in por_camara["incidentes"]] == ["zona-sur"]
    assert [f["camera_id"] for f in por_zona["incidentes"]] == ["camara-01"]


def test_reporte_filtra_por_estado_de_revision_y_por_baliza() -> None:
    _incidente()
    fallida = _incidente(beacon_alert={"status": "failed", "latency_ms": 120})
    _cerrar(fallida["episode_id"], "2026-10-28T09:00:00+00:00")

    por_baliza = {
        estado: peticion("GET", f"/reports?beacon_status={estado}").json()["total"]
        for estado in ("skipped_offline", "failed", "alerted")
    }
    por_estado = {
        estado: peticion("GET", f"/reports?status={estado}").json()["total"]
        for estado in ("open", "closed")
    }

    assert por_baliza == {"skipped_offline": 1, "failed": 1, "alerted": 0}
    # `status` es el de la revisión, que decide una persona: cerrar el aviso no
    # lo cambia, así que los dos siguen abiertos hasta que alguien los vea.
    assert por_estado == {"open": 2, "closed": 0}


def test_reporte_el_rango_solapa_no_filtra_por_deteccion() -> None:
    """Una infracción abierta antes del `desde` sigue contando.

    Para saber qué pasó en un turno, lo que estaba ocurriendo mientras tanto
    importa tanto como lo que empezó ahí.
    """
    incidente = _incidente()
    _cerrar(incidente["episode_id"], "2026-10-28T09:00:00+00:00")

    cuerpo = peticion("GET", "/reports?desde=2026-10-28T08:30:00Z").json()

    assert cuerpo["total"] == 1
    assert _instante(cuerpo["incidentes"][0]["started_at"]) == _utc(
        2026, 10, 28, 8, 0, 0
    )


def test_reporte_excluye_los_terminados_antes_del_desde() -> None:
    incidente = _incidente()
    _cerrar(incidente["episode_id"], "2026-10-28T08:10:00+00:00")

    cuerpo = peticion("GET", "/reports?desde=2026-10-28T08:20:00Z").json()

    assert cuerpo["total"] == 0


def test_reporte_excluye_los_detectados_despues_del_hasta() -> None:
    _incidente(detected_at="2026-10-28T10:00:00+00:00")

    cuerpo = peticion("GET", "/reports?hasta=2026-10-28T09:00:00Z").json()

    assert cuerpo["total"] == 0


def test_reporte_un_abierto_entre_medias_entra_por_solape() -> None:
    """Un aviso sin `ended_at` no se puede descartar por el rango."""
    _incidente(detected_at="2026-10-28T07:00:00+00:00")

    cuerpo = peticion(
        "GET", "/reports?desde=2026-10-28T08:00:00Z&hasta=2026-10-28T09:00:00Z"
    ).json()

    assert cuerpo["total"] == 1


def test_reporte_filtrar_por_tipo_de_infraccion() -> None:
    _incidente(violation_types=["missing_helmet", "missing_reflective_vest"])

    por_chaleco = peticion(
        "GET", "/reports?violation_type=missing_reflective_vest"
    ).json()
    por_casco = peticion(
        "GET", "/reports?violation_type=missing_helmet"
    ).json()

    # El filtro sirve con cualquiera de los tipos del incidente, no solo con
    # el principal.
    assert por_chaleco["total"] == 1
    assert por_casco["total"] == 1


def test_reporte_sin_zona_horaria_responde_422() -> None:
    assert peticion("GET", "/reports?desde=2026-10-28T08:00:00").status_code == 422


def test_reporte_desde_posterior_a_hasta_responde_422() -> None:
    respuesta = peticion(
        "GET",
        "/reports?desde=2026-10-28T10:00:00Z&hasta=2026-10-28T09:00:00Z",
    )

    assert respuesta.status_code == 422
