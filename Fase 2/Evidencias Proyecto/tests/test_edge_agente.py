"""Pruebas del agente Edge (tarea 4.4): zona de riesgo, cliente de la baliza
según docs/PROTOCOLO_BALIZA.md y cola local sin pérdidas."""

import json
import sys
import threading
import time
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).parents[1] / "src" / "edge"))

import agente  # noqa: E402


# ---------- baliza simulada mínima para las pruebas ----------

@pytest.fixture
def baliza():
    estado = {"codigo": 200, "demora": 0.0, "llamadas": []}

    class Manejador(BaseHTTPRequestHandler):
        def _responder(self):
            largo = int(self.headers.get("Content-Length") or 0)
            cuerpo = json.loads(self.rfile.read(largo)) if largo else None
            estado["llamadas"].append({"ruta": self.path, "cuerpo": cuerpo,
                                       "token": self.headers.get("Authorization")})
            time.sleep(estado["demora"])
            self.send_response(estado["codigo"])
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"status": "alerting"}')

        do_GET = do_POST = _responder

        def log_message(self, *args):
            pass

    servidor = ThreadingHTTPServer(("127.0.0.1", 0), Manejador)
    threading.Thread(target=servidor.serve_forever, daemon=True).start()
    estado["url"] = f"http://127.0.0.1:{servidor.server_address[1]}"
    yield estado
    servidor.shutdown()


def _cliente(url):
    return agente.ClienteBaliza(url, "token-de-prueba", "zona-norte", "Zona Norte")


# ---------- zona de riesgo ----------

def test_zona_por_defecto_cubre_todo_el_cuadro() -> None:
    assert agente.Zona().contiene((10, 10, 50, 90), 100, 100)


def test_zona_cuenta_el_punto_de_los_pies() -> None:
    mitad_izquierda = agente.Zona([[0, 0], [0.5, 0], [0.5, 1], [0, 1]])
    assert mitad_izquierda.contiene((10, 0, 40, 100), 100, 100)
    assert not mitad_izquierda.contiene((60, 0, 90, 100), 100, 100)


# ---------- cliente de la baliza ----------

def test_alerta_aceptada_mide_la_latencia(baliza) -> None:
    resultado = _cliente(baliza["url"]).alertar(["missing_helmet"])

    assert resultado["status"] == "alerted"
    assert resultado["latency_ms"] >= 0
    orden = baliza["llamadas"][0]
    assert orden["ruta"] == "/alert"
    assert orden["token"] == "Bearer token-de-prueba"
    assert orden["cuerpo"]["zone_id"] == "zona-norte"
    assert 1 <= orden["cuerpo"]["duration_s"] <= 30


def test_sin_respuesta_reintenta_una_vez_con_el_mismo_alert_id(baliza, monkeypatch) -> None:
    monkeypatch.setattr(agente.ClienteBaliza, "ESPERA_S", 0.2)
    baliza["demora"] = 0.5

    resultado = _cliente(baliza["url"]).alertar(["missing_helmet"])

    assert resultado == {"status": "failed", "latency_ms": None}
    ids = [llamada["cuerpo"]["alert_id"] for llamada in baliza["llamadas"]]
    assert len(ids) == 2 and ids[0] == ids[1]


def test_zona_equivocada_no_se_reintenta(baliza) -> None:
    baliza["codigo"] = 409

    resultado = _cliente(baliza["url"]).alertar(["missing_reflective_vest"])

    assert resultado["status"] == "failed"
    assert len(baliza["llamadas"]) == 1


def test_tres_fallos_dejan_la_baliza_fuera_de_linea_y_vuelve(baliza, monkeypatch) -> None:
    monkeypatch.setattr(agente.ClienteBaliza, "ESPERA_S", 0.2)
    cliente = _cliente("http://127.0.0.1:9")  # puerto sin servicio

    cambios = [cliente.revisar() for _ in range(3)]
    assert cambios == [False, False, True] and not cliente.en_linea
    assert cliente.alertar(["missing_helmet"])["status"] == "skipped_offline"

    cliente.url = baliza["url"]
    assert cliente.revisar() and cliente.en_linea


# ---------- motor limitado a la zona ----------

class ZonalPrueba(agente.MonitorZonal):
    """Motor con detecciones programadas, sin cargar YOLO ni YuNet."""

    def __init__(self, zona, escenas):
        self.poligono = zona
        # Este stub no pasa por `MonitorEPP.__init__`, así que reparte a mano
        # lo que el motor esperaría encontrar: las zonas en su formato y la
        # cámara que se reporta. Con eso el motor limita el aviso por su cuenta.
        self.zonas = zona.como_zonas("zona-prueba")
        self.camera_id = "camara-prueba"
        self.escenas = iter(escenas)
        self.ping_segundos = 60
        self.historial, self.ultimo_estado, self.estado_confirmado = {}, {}, {}
        self.violacion_confirmada, self.ultimo_visto, self.caja_vista = {}, {}, {}
        self.episodio, self.en_espera = {}, []
        self.n_frames, self.t_prev, self.fps = 0, time.time(), 0.0
        self.avisos = []
        self.al_registrar = self.avisos.append

    def _detectar(self, frame):
        return next(self.escenas)

    def guardar_evidencia(self, frame):
        return "incidents/2026/01/01/prueba.jpg", datetime.now(timezone.utc)

    def difumar_rostros(self, frame, persona, cabezas):
        return 1

    @staticmethod
    def _consola(pid, estado, evento="inicio"):
        pass


def _persona_sin_epp(pid, x1, x2):
    persona = {"nombre": "Person", "caja": (x1, 50, x2, 390), "conf": 0.9, "id": pid}
    epps = [{"nombre": "no_helmet", "caja": (x1 + 20, 55, x2 - 20, 110), "conf": 0.8, "id": 90 + pid},
            {"nombre": "no_vest", "caja": (x1 + 10, 150, x2 - 10, 280), "conf": 0.8, "id": 80 + pid}]
    return persona, epps


def test_solo_avisa_de_quien_esta_dentro_de_la_zona() -> None:
    dentro, epp_dentro = _persona_sin_epp(1, 10, 140)      # pies en x = 0,25
    fuera, epp_fuera = _persona_sin_epp(2, 170, 290)       # pies en x = 0,77
    escena = ([dentro, fuera], epp_dentro + epp_fuera, True)
    monitor = ZonalPrueba(agente.Zona([[0, 0], [0.5, 0], [0.5, 1], [0, 1]]), [escena, escena])
    frame = np.zeros((400, 300, 3), dtype=np.uint8)

    monitor.procesar(frame)
    monitor.procesar(frame)  # el motor confirma la infracción en el segundo cuadro

    assert [(a["event"], a["person_track_id"]) for a in monitor.avisos] == [("inicio", 1)]


# ---------- cola local ----------

def test_vaciar_la_cola_no_pierde_lo_que_falta_si_la_api_vuelve_a_caer(tmp_path, monkeypatch) -> None:
    reporte = agente.ReporteAPI("http://127.0.0.1:9", archivo_cola=tmp_path / "cola.jsonl", token="x")
    for n in (1, 2, 3):
        reporte._encolar({"n": n})

    def enviar(incidente):
        if incidente["n"] == 2:  # la API se cae a mitad del vaciado
            reporte._encolar(incidente)
            return False
        return True

    monkeypatch.setattr(reporte, "enviar", enviar)

    assert reporte.vaciar_cola() == 1
    assert [i["n"] for i in reporte.pendientes] == [2, 3]
    lineas = (tmp_path / "cola.jsonl").read_text(encoding="utf-8").splitlines()
    assert [json.loads(linea)["n"] for linea in lineas] == [2, 3]

