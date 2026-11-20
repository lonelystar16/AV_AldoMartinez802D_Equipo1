"""El agente aplica lo que se edita en el dashboard sin reiniciarse (4.19).

La URL RTSP y los estados activos de la cámara y de la zona salen de
`GET /edge/config`. Se cubre la decisión (qué fuente manda, cuándo se pausa)
y el ciclo principal con una cámara y una API simuladas.
"""

import json
import sys
from collections import deque
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parents[1] / "src" / "edge"))

import agente  # noqa: E402
from motor_cascovision import MonitorEPP  # noqa: E402

CFG = {"camera_id": "camara-01", "zone_id": "zona-norte", "zone_name": "Zona Norte",
       "fuente": "rtsp://local/json", "poligono": [[0, 0], [1, 0], [1, 1], [0, 1]],
       "baliza": {"url": "", "duracion_s": 10}, "api": "http://api", "carpeta_datos": "edge-datos"}


def remota(url="rtsp://api/camara", camara=True, zona=True, zone_id="zona-norte") -> dict:
    return {"camera_id": "camara-01",
            "camera": {"id": "camara-01", "rtsp_url": url, "active": camara},
            "zone_id": zone_id,
            "zone": {"id": zone_id, "name": "Zona Norte",
                     "polygon": CFG["poligono"], "active": zona},
            "beacon": None}


# ---------- qué cámara se abre ----------

def test_la_fuente_fija_del_sitio_gana_a_la_api() -> None:
    assert agente.elegir_fuente("rtsp://u:clave@cam/1", CFG, remota()) == "rtsp://u:clave@cam/1"


def test_sin_fuente_fija_manda_la_url_del_dashboard() -> None:
    assert agente.elegir_fuente(None, CFG, remota()) == "rtsp://api/camara"
    assert agente.elegir_fuente("", CFG, remota()) == "rtsp://api/camara"


def test_sin_api_manda_el_json_local() -> None:
    assert agente.elegir_fuente(None, CFG, None) == "rtsp://local/json"


# ---------- cuándo se vigila ----------

@pytest.mark.parametrize("respuesta, esperado", [
    (None, True),                                  # API caída: se sigue vigilando
    (remota(), True),
    (remota(camara=False), False),
    (remota(zona=False), False),
    (remota(zona=False, zone_id="zona-a"), True),  # otra zona no apaga la propia
])
def test_vigilancia_activa(respuesta, esperado) -> None:
    assert agente.vigilancia_activa(CFG, respuesta) is esperado


# ---------- al pausar se cierran los incidentes ----------

def test_cerrar_episodios_envia_fin_y_olvida_a_las_personas() -> None:
    enviados = []
    monitor = MonitorEPP.__new__(MonitorEPP)  # sin cargar el modelo
    monitor.al_registrar = enviados.append
    monitor.episodio = {1: {"incidente": {"episode_id": "e1", "event": "inicio"}},
                        2: {"incidente": None}}  # nunca llegó a registrarse
    monitor.en_espera = [{"episodio": {"incidente": {"episode_id": "e3", "event": "ping"}}}]
    for estado in ("historial", "ultimo_estado", "estado_confirmado",
                   "violacion_confirmada", "ultimo_visto", "caja_vista"):
        setattr(monitor, estado, {1: deque()})

    cierres = monitor.cerrar_episodios()

    assert [c["episode_id"] for c in cierres] == ["e1", "e3"]
    assert [e["event"] for e in enviados] == ["fin", "fin"]
    assert monitor.episodio == {} and monitor.en_espera == []
    assert monitor.ultimo_visto == {} and monitor.violacion_confirmada == {}
    # Cerrar de nuevo no repite el FIN.
    assert monitor.cerrar_episodios() == []


# ---------- el ciclo principal ----------

class Parar(Exception):
    """Termina el ciclo de prueba."""


class Camara:
    """Captura simulada: entrega cuadros o, si la URL es mala, nunca abre."""

    def __init__(self, url: str, eventos: list):
        self.url, self.eventos = url, eventos
        self.buena = "mala" not in url

    def isOpened(self):
        return self.buena

    def grab(self):
        return self.buena

    def retrieve(self):
        return True, object()

    def release(self):
        self.eventos.append(f"suelta {self.url}")


@pytest.fixture
def ciclo(tmp_path, monkeypatch):
    """Corre `main()` con reloj, cámara, motor y API simulados.

    `respuestas` es lo que contesta la API en cada consulta, una tras otra
    (la primera es la del arranque). `cuadros_al_final` cuadros después de la
    última respuesta, el ciclo se detiene.
    """

    def correr(respuestas: list, cuadros_al_final: int = 2) -> list:
        eventos: list = []
        reloj = [0.0]
        pendientes = deque(respuestas)
        ultima = [None]

        def configuracion(cfg, token):
            if pendientes:
                ultima[0] = pendientes.popleft()
                r = ultima[0]
                eventos.append("config " + ("caida" if r is None else
                               f"{r['camera']['rtsp_url']} activa={agente.vigilancia_activa(cfg, r)}"))
                return r
            eventos.append("config igual")
            return ultima[0]

        class Monitor:
            def __init__(self, *args, **kwargs):
                self.cuadros_finales = 0

            def procesar(self, frame):
                eventos.append("procesa")
                if not pendientes:
                    self.cuadros_finales += 1
                    if self.cuadros_finales >= cuadros_al_final:
                        raise Parar

            def cerrar_episodios(self):
                eventos.append("cierra episodios")
                return []

        class Reporte:
            def __init__(self, reporte):
                self.reporte = reporte

            def enviar(self, incidente):
                pass

            def esperar(self):
                pass

        def abrir(fuente):
            eventos.append(f"abre {fuente}")
            return Camara(fuente, eventos)

        def dormir(segundos):
            reloj[0] += segundos

        def ahora():
            reloj[0] += 0.5
            return reloj[0]

        config = tmp_path / "edge.json"
        config.write_text(json.dumps(dict(CFG, carpeta_datos=str(tmp_path / "datos"))),
                          encoding="utf-8")
        monkeypatch.setattr(sys, "argv", ["agente.py", "--config", str(config), "--sin-ventana"])
        monkeypatch.delenv("CAMARA_FUENTE", raising=False)
        monkeypatch.setattr(agente, "_configuracion_remota", configuracion)
        monkeypatch.setattr(agente, "MonitorZonal", Monitor)
        monkeypatch.setattr(agente, "ReporteAsincrono", Reporte)
        monkeypatch.setattr(agente, "abrir", abrir)
        monkeypatch.setattr(agente, "guardar_cuadro", lambda frame, carpeta: None)
        monkeypatch.setattr(agente, "informar_baliza", lambda *a: None)
        monkeypatch.setattr(agente.cv2, "destroyAllWindows", lambda: None)
        monkeypatch.setattr(agente.time, "sleep", dormir)
        monkeypatch.setattr(agente.time, "monotonic", ahora)

        with pytest.raises(Parar):
            agente.main()
        return eventos

    return correr


def _entre(eventos: list, desde: str, hasta: str) -> list:
    inicio = eventos.index(desde)
    return eventos[inicio + 1:eventos.index(hasta, inicio + 1)]


def test_abre_la_url_del_dashboard_y_no_la_del_json(ciclo) -> None:
    eventos = ciclo([remota("rtsp://api/1")])

    assert "abre rtsp://api/1" in eventos
    assert not any("local/json" in e for e in eventos)


def test_una_url_mala_se_corrige_desde_el_dashboard_sin_reiniciar(ciclo) -> None:
    # La cámara nunca abre con la URL mala: aun así el agente sigue
    # preguntando a la API, toma la URL nueva y vuelve a vigilar.
    eventos = ciclo([remota("rtsp://api/mala"), remota("rtsp://api/mala"),
                     remota("rtsp://api/buena")])

    assert eventos.count("abre rtsp://api/mala") > 1  # reintentó la mala
    assert "abre rtsp://api/buena" in eventos
    assert eventos.index("abre rtsp://api/buena") > eventos.index("config rtsp://api/buena activa=True")
    assert "procesa" in eventos[eventos.index("abre rtsp://api/buena"):]


def test_cambiar_la_url_reabre_la_camara(ciclo) -> None:
    eventos = ciclo([remota("rtsp://api/1"), remota("rtsp://api/1"), remota("rtsp://api/2")])

    tras_cambio = eventos[eventos.index("config rtsp://api/2 activa=True"):]
    assert tras_cambio[1:3] == ["suelta rtsp://api/1", "abre rtsp://api/2"]


@pytest.mark.parametrize("apagada", [remota(camara=False), remota(zona=False)],
                         ids=["camara", "zona"])
def test_desactivar_pausa_y_reactivar_reanuda(ciclo, apagada) -> None:
    eventos = ciclo([remota(), remota(), apagada, apagada, remota()])

    pausa = _entre(eventos, "config rtsp://api/camara activa=False",
                   "config rtsp://api/camara activa=True")
    # Al pausar cierra los incidentes abiertos y suelta la cámara, y mientras
    # dure la pausa no analiza ningún cuadro.
    assert pausa[:2] == ["cierra episodios", "suelta rtsp://api/camara"]
    assert "procesa" not in pausa and not any(e.startswith("abre") for e in pausa)
    # Antes de la pausa vigilaba, y al reactivar vuelve a abrir y a vigilar.
    assert "procesa" in eventos[:eventos.index("cierra episodios")]
    despues = eventos[eventos.index("config rtsp://api/camara activa=True", eventos.index("cierra episodios")):]
    assert despues[1] == "abre rtsp://api/camara" and "procesa" in despues


def test_arranca_en_pausa_si_la_camara_esta_desactivada(ciclo) -> None:
    eventos = ciclo([remota(camara=False), remota(camara=False), remota()])

    assert eventos.index("abre rtsp://api/camara") > eventos.index("config rtsp://api/camara activa=True")


def test_con_la_api_caida_sigue_con_lo_ultimo_que_supo(ciclo) -> None:
    eventos = ciclo([remota(), None, None])

    assert "cierra episodios" not in eventos
    assert eventos.count("abre rtsp://api/camara") == 1
