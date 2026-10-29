"""Pruebas de la descarga de configuración del agente desde la API (4.15).

El agente pregunta `GET /edge/config` una vez al arrancar y usa su
`config.json` como respaldo, porque un borde no puede depender de la API para
arrancar. Estas pruebas cubren esa decisión y el parte `PUT
/edge/beacons/{id}/status`.
"""

import json
import sys
import threading
from copy import deepcopy
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parents[1] / "src" / "edge"))

import agente  # noqa: E402

CONFIG_LOCAL = {
    "camera_id": "camara-01",
    "zone_id": "zona-norte",
    "zone_name": "Zona Norte",
    "fuente": "0",
    "poligono": [[0.0, 0.0], [1.0, 0.0], [1.0, 1.0], [0.0, 1.0]],
    "baliza": {"url": "http://127.0.0.1:8081", "duracion_s": 10},
    "api": "",
    "carpeta_datos": "edge-datos",
}

RESPUESTA_API = {
    "camera_id": "camara-01",
    "camera": {
        "id": "camara-01", "name": "Camara 01", "rtsp_url": "rtsp://10.0.0.5",
        "location": "Entrada norte", "active": True,
        "last_frame_at": None, "created_at": "2026-10-01T00:00:00+00:00",
    },
    "zone_id": "zona-norte",
    "zone": {
        "id": "zona-norte", "camera_id": "camara-01", "name": "Zona Norte API",
        "polygon": [[0.0, 0.0], [0.5, 0.0], [0.5, 1.0], [0.0, 1.0]],
        "suppression_s": 60, "active": True,
    },
    "beacon": {
        "id": "baliza-01", "zone_id": "zona-norte", "name": "Baliza Norte",
        "ip": "192.168.50.21", "duration_s": 12, "sound": "siren",
        "message": "CASCO", "online": False, "battery_pct": None,
        "last_seen_at": None,
    },
}


@pytest.fixture
def api():
    """API simulada que atiende /edge/config y /edge/beacons/{id}/status."""

    estado = {"codigo": 200, "respuestas": [], "llamadas": []}

    class Manejador(BaseHTTPRequestHandler):
        def _leer(self):
            largo = int(self.headers.get("Content-Length") or 0)
            cuerpo = json.loads(self.rfile.read(largo)) if largo else None
            estado["llamadas"].append({
                "ruta": self.path, "metodo": self.command, "cuerpo": cuerpo,
                "token": self.headers.get("Authorization"),
            })
            self.send_response(estado["codigo"])
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(estado["respuestas"]).encode("utf-8"))

        do_GET = do_PUT = _leer

        def log_message(self, *args):
            pass

    servidor = ThreadingHTTPServer(("127.0.0.1", 0), Manejador)
    threading.Thread(target=servidor.serve_forever, daemon=True).start()
    estado["config"] = dict(CONFIG_LOCAL, api=f"http://127.0.0.1:{servidor.server_address[1]}")
    yield estado
    servidor.shutdown()


def _config(api, **cambios) -> dict:
    cfg = deepcopy(api["config"])
    cfg.update(cambios)
    return cfg


def test_la_config_remota_manda_camara_zona_y_poligono(api) -> None:
    api["respuestas"] = RESPUESTA_API
    cfg = _config(api)

    agente.aplicar_configuracion_remota(cfg, agente._configuracion_remota(cfg, "token"))

    assert cfg["zone_id"] == "zona-norte"
    assert cfg["zone_name"] == "Zona Norte API"
    # El polígono que administra el dashboard reemplaza al del JSON local.
    assert cfg["poligono"] == [[0.0, 0.0], [0.5, 0.0], [0.5, 1.0], [0.0, 1.0]]


def test_pregunta_una_vez_con_el_token_del_agente(api) -> None:
    api["respuestas"] = RESPUESTA_API
    cfg = _config(api)

    agente._configuracion_remota(cfg, "token-secreto")

    assert len(api["llamadas"]) == 1
    llamada = api["llamadas"][0]
    assert llamada["metodo"] == "GET"
    assert llamada["ruta"] == "/edge/config?camera_id=camara-01"
    assert llamada["token"] == "Bearer token-secreto"


def test_la_url_local_de_la_baliza_no_se_pisa(api) -> None:
    """El config.json trae la URL del simulador en el puerto 8081.

    La API dirige la baliza por IP y el puerto 80 del protocolo; si el sitio
    local ya fijó una URL, es un ajuste que la API no debe reemplazar.
    """
    api["respuestas"] = RESPUESTA_API
    cfg = _config(api)

    agente.aplicar_configuracion_remota(cfg, agente._configuracion_remota(cfg, "token"))

    assert cfg["baliza"]["url"] == "http://127.0.0.1:8081"
    assert cfg["baliza"]["duracion_s"] == 10


def test_sin_url_local_la_baliza_se_dirige_por_su_ip(api) -> None:
    api["respuestas"] = RESPUESTA_API
    # Local sin nada fijado: manda lo que diga la API.
    cfg = _config(api, baliza={})

    agente.aplicar_configuracion_remota(cfg, agente._configuracion_remota(cfg, "token"))

    # El protocolo fija el puerto 80, así que de la IP sale la URL completa.
    assert cfg["baliza"]["url"] == "http://192.168.50.21"
    assert cfg["baliza"]["duracion_s"] == 12


def test_sin_baliza_en_la_api_la_config_local_sigue_viva(api) -> None:
    api["respuestas"] = dict(RESPUESTA_API, beacon=None)
    cfg = _config(api)

    agente.aplicar_configuracion_remota(cfg, agente._configuracion_remota(cfg, "token"))

    assert cfg["baliza"]["url"] == "http://127.0.0.1:8081"


def test_api_caída_devuelve_none_en_lugar_de_lanzar(api) -> None:
    api["codigo"] = 503
    cfg = _config(api)

    assert agente._configuracion_remota(cfg, "token") is None


def test_api_que_no_conoce_la_camara_devuelve_none(api) -> None:
    api["respuestas"] = dict(RESPUESTA_API, camera_id="camara-99")
    cfg = _config(api)

    assert agente._configuracion_remota(cfg, "token") is None


def test_la_espera_de_la_api_es_corta(api, monkeypatch) -> None:
    """Un borde no puede colgarse del arranque por una API lenta."""
    api["codigo"] = 503

    llamado = {}

    def espera_larga(*args, **kwargs):
        llamado["timeout"] = kwargs.get("timeout")
        raise OSError("sin red")

    monkeypatch.setattr(agente.urllib.request, "urlopen", espera_larga)
    cfg = _config(api)

    assert agente._configuracion_remota(cfg, "token") is None
    assert llamado["timeout"] == agente.ESPERA_API_S
    assert llamado["timeout"] < 5


# ---------- parte de estado de la baliza ----------


def _baliza_en_linea(url: str) -> agente.ClienteBaliza:
    baliza = agente.ClienteBaliza(url, "token", "zona-norte", "Zona Norte")
    baliza.en_linea = True
    return baliza


def test_el_parte_informa_el_estado_de_la_baliza(api) -> None:
    api["respuestas"] = {"id": "baliza-01"}
    cfg = _config(api)

    agente.informar_baliza(cfg["api"], "baliza-01", "token-secreto",
                           _baliza_en_linea("http://127.0.0.1:1"))

    assert len(api["llamadas"]) == 1
    llamada = api["llamadas"][0]
    assert llamada["metodo"] == "PUT"
    assert llamada["ruta"] == "/edge/beacons/baliza-01/status"
    assert llamada["token"] == "Bearer token-secreto"
    assert llamada["cuerpo"]["online"] is True
    assert llamada["cuerpo"]["checked_at"] is not None


def test_el_parte_es_una_notificacion_no_una_orden(api) -> None:
    """Si la API no responde, el análisis no se frena ni se reporta el fallo."""
    cfg = _config(api)
    api["codigo"] = 503

    # No debe lanzar.
    agente.informar_baliza(cfg["api"], "baliza-01", "token",
                           _baliza_en_linea("http://127.0.0.1:1"))


def test_sin_baliza_no_se_envia_el_parte(api) -> None:
    cfg = _config(api)

    agente.informar_baliza(cfg["api"], None, "token",
                           _baliza_en_linea("http://127.0.0.1:1"))

    assert api["llamadas"] == []
