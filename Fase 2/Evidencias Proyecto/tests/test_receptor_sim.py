import json
import http.client
import sys
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path
from uuid import uuid4

import pytest

SIM_PATH = Path(__file__).parents[1] / "src" / "firmware" / "receptor-sim"
sys.path.insert(0, str(SIM_PATH))
import server  # noqa: E402

TOKEN = "t" * 32


@pytest.fixture
def receptor(tmp_path):
    state = server.Receptor(TOKEN, "zona-norte", "Zona Norte", "baliza-01",
                            tmp_path / "alerts.jsonl")
    httpd = server.crear_servidor(port=0, receptor=state)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{httpd.server_address[1]}", state
    httpd.shutdown()
    httpd.server_close()


def request(base, method, path, body=None, token=TOKEN, raw=None):
    data = raw if raw is not None else (json.dumps(body).encode() if body is not None else None)
    headers = {"Content-Type": "application/json"}
    if token is not None:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(base + path, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=3) as response:
            return response.status, json.loads(response.read() or b"null")
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read() or b"null")


def valid_order(**changes):
    return {
        "alert_id": str(uuid4()),
        "zone_id": "zona-norte",
        "zone_name": "Zona Norte",
        "violations": ["missing_helmet"],
        "duration_s": 10,
        "sound": "siren",
        "sent_at": "2026-10-20T14:30:00Z",
        **changes,
    }


def test_health_publica_incluye_estado_de_bateria(receptor):
    status, body = request(receptor[0], "GET", "/health", token=None)
    assert status == 200
    assert body["status"] == "ok" and body["zone_id"] == "zona-norte"
    assert body["battery_pct"] == 87 and body["protocol"] == "1"


def test_orden_valida_y_registro_jsonl(receptor):
    base, state = receptor
    order = valid_order()
    status, body = request(base, "POST", "/alert", order)
    assert status == 200 and body == {
        "status": "alerting", "alert_id": order["alert_id"], "duplicate": False,
    }
    line = json.loads(state.log_path.read_text(encoding="utf-8"))
    assert line["order"] == order and line["received_at"]


@pytest.mark.parametrize("token", [None, "incorrecto"])
def test_token_ausente_o_incorrecto_responde_401(receptor, token):
    assert request(receptor[0], "POST", "/alert", valid_order(), token)[0] == 401


@pytest.mark.parametrize("duration", [0, 31])
def test_duracion_fuera_de_rango_responde_400(receptor, duration):
    status, body = request(receptor[0], "POST", "/alert", valid_order(duration_s=duration))
    assert status == 400 and body["field"] == "duration_s"


def test_zona_ajena_responde_409(receptor):
    status, body = request(receptor[0], "POST", "/alert", valid_order(zone_id="zona-sur"))
    assert status == 409 and body["zone_id"] == "zona-norte"


def test_reintento_con_mismo_id_no_reinicia_alerta(receptor):
    base, state = receptor
    order = valid_order(duration_s=10)
    assert request(base, "POST", "/alert", order)[1]["duplicate"] is False
    active_until = state.active_until
    time.sleep(0.01)
    assert request(base, "POST", "/alert", order)[1]["duplicate"] is True
    assert state.active_until == active_until


def test_cuerpo_mayor_a_un_kb_responde_413(receptor):
    assert request(receptor[0], "POST", "/alert", raw=b" " * 1025)[0] == 413


def test_demora_configurada(receptor):
    base, state = receptor
    state.delay_ms = 30
    start = time.perf_counter()
    assert request(base, "POST", "/alert", valid_order())[0] == 200
    assert time.perf_counter() - start >= 0.025


def test_fail_rate_cierra_sin_responder(receptor, monkeypatch):
    base, state = receptor
    state.fail_rate = 1
    monkeypatch.setattr(server.random, "random", lambda: 0)
    order = valid_order()
    with pytest.raises(http.client.RemoteDisconnected):
        request(base, "POST", "/alert", order)
    state.fail_rate = 0
    assert request(base, "POST", "/alert", order)[1]["duplicate"] is True


def test_fail_rate_tambien_afecta_health(receptor, monkeypatch):
    base, state = receptor
    state.fail_rate = 1
    monkeypatch.setattr(server.random, "random", lambda: 0)
    with pytest.raises(http.client.RemoteDisconnected):
        request(base, "GET", "/health", token=None)


def test_configuracion_requiere_token_seguro():
    with pytest.raises(ValueError, match="32 caracteres"):
        server.Receptor("corto", "zona-norte", "Zona Norte", "baliza-01", "alerts.jsonl")
