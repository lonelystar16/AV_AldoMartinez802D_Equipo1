"""Pruebas de la separación entre lo que se difumina y lo que se vigila.

Un chaleco suelto en el piso puede salir cajado por YOLO como `Person`, con su
propio `vest` encima. Esa caja no describe a nadie y abriría un incidente por
cada chaleco abandonado de la obra. La regla que la descarta (`parece_cuerpo`)
mide qué fracción de la PERSONA cubre el EPP: en una persona de verdad el
chaleco ocupa el torso, un 40 %; en el fantasma ocupa la caja entera.

El orden de los argumentos es la trampa, y por eso está escrito en el motor:
medido al revés daría ~1.0 también en una persona real y la regla descartaría
a todo el mundo.

Decisión de producto y no de código: el EPP sin nadie detrás se evalúa, se
difumina, pero no se reporta. Un chaleco no es un trabajador. Lo que sí se
sigue haciendo con él es difuminar el frame entero, porque un EPP suelto
también puede estar tapando un rostro que el detector no acertó.
"""

import ast
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pytest

PROYECTO = Path(__file__).parents[1]
MOTOR = PROYECTO / "Yolo" / "modelamiento"
sys.path.insert(0, str(MOTOR))

import motor_cascovision as mc  # noqa: E402

ANCHO, ALTO = 300, 400


def _frame():
    return np.random.default_rng(11).integers(0, 255, (ALTO, ANCHO, 3),
                                              dtype=np.uint8)


class MotorPrueba(mc.MonitorEPP):
    """Motor entero con detecciones programadas, sin cargar YOLO ni YuNet."""

    def __init__(self, escenas):
        # Solo lo que el difuminado de frame completo llega a tocar.
        self.detector = None
        self.escenas = iter(escenas)
        self.ping_segundos = 60
        self.historial = {}
        self.ultimo_estado = {}
        self.estado_confirmado = {}
        self.violacion_confirmada = {}
        self.ultimo_visto = {}
        self.caja_vista = {}
        self.episodio = {}
        self.en_espera = []
        self.n_frames = 0
        self.t_prev = time.time()
        self.fps = 0.0
        self.camera_id = "camara-01"
        # Sin zonas: aquí solo importa la regla anti-fantasma.
        self.zonas = None
        self.difuminados = []
        self.avisos = []
        self.al_registrar = self.avisos.append

    def _detectar(self, frame):
        return next(self.escenas)

    def guardar_evidencia(self, frame):
        return "incidents/2026/01/01/prueba.jpg", datetime.now(timezone.utc)

    def difumar_rostros(self, frame, persona, cabezas):
        """Sustituye el difuminado: aquí solo se cuenta quién pasó por él."""
        self.difuminados.append(persona)
        return 1

    @staticmethod
    def _consola(pid, estado, evento="inicio"):
        pass


@pytest.fixture(autouse=True)
def completos(monkeypatch):
    """El difuminado de frame completo no corre de verdad: solo se cuenta."""
    llamadas = []
    monkeypatch.setattr(mc, "difumar_roi",
                        lambda detector, roi: llamadas.append(roi) or 1)
    return llamadas


def _persona(pid, caja):
    return {"id": pid, "caja": caja, "conf": 0.9, "nombre": "Person"}


def _epp(nombre, caja, eid=90):
    return {"id": eid, "caja": caja, "conf": 0.8, "nombre": nombre}


# La caja del fantasma es casi la del chaleco: 28000 de 31900 px² de la
# persona, un 88 %. El umbral es 0.7.
FANTASMA = (95, 95, 205, 385)
CHALECO = (100, 100, 200, 380)

# Persona de verdad: el chaleco cubre 11200 de 28000 px², un 40 %.
PERSONA = (100, 100, 200, 380)
TORSO = (110, 180, 190, 320)
CABEZA = (130, 105, 170, 140)


# ---------- la regla, por sí sola ----------

def test_un_chaleco_cajado_como_persona_no_parece_cuerpo() -> None:
    """Ocupa la caja entera: detrás de esa caja no hay nadie."""
    assert not mc.parece_cuerpo(_persona(1, FANTASMA), [_epp("vest", CHALECO)])


def test_en_una_persona_real_el_chaleco_ocupa_el_torso() -> None:
    """40 % de la caja: torso y no cuerpo entero, así que sí hay alguien."""
    assert mc.parece_cuerpo(_persona(1, PERSONA), [_epp("no_vest", TORSO)])


def test_sin_epp_no_se_puede_acusar_a_la_caja_de_ser_el_epp() -> None:
    """No detectar nada no prueba nada, y además es noticia por sí mismo.

    El fantasma va siempre acompañado de su propio EPP, así que este caso no
    lo deja pasar por accidente: deja intacto `POLITICA_SIN_DATOS`.
    """
    assert mc.parece_cuerpo(_persona(1, PERSONA), [])


# ---------- lo que se vigila ----------

def test_un_chaleco_cajado_como_persona_no_abre_registro(completos) -> None:
    """Sin la regla esto abriría un incidente por `falta_casco`, como cualquiera."""
    monitor = MotorPrueba([([_persona(1, FANTASMA)], [_epp("vest", CHALECO)], False)])

    assert monitor.procesar(_frame()) == []
    assert monitor.avisos == []
    assert monitor.episodio == {}
    # Sí se difumina: fantasma o no, lo que entra en el encuadre no se queda
    # con el rostro a la vista.
    assert monitor.difuminados == [FANTASMA]
    assert len(completos) == 1


def test_una_persona_real_con_las_dos_faltas_sigue_reportando(completos) -> None:
    """Guardia contra el sobre-filtrado: filtrar de más también es un fallo."""
    epps = [_epp("no_helmet", CABEZA, 90), _epp("no_vest", TORSO, 80)]
    monitor = MotorPrueba([([_persona(1, PERSONA)], epps, False)])

    incidentes = monitor.procesar(_frame())

    assert len(incidentes) == 1
    assert incidentes[0]["event"] == "inicio"
    assert incidentes[0]["person_track_id"] == 1
    assert incidentes[0]["violation_types"] == ["missing_helmet",
                                                 "missing_reflective_vest"]
    assert monitor.difuminados == [PERSONA]
    # Con una caja de persona creíble no hace falta tirar del frame entero.
    assert completos == []


def test_un_torso_recortado_por_el_borde_pasa_por_fantasma() -> None:
    """CASO LÍMITE, conocido y aceptado.

    Si la persona queda cortada por el borde del encuadre, lo que se ve de su
    caja `Person` es sobre todo torso, y el chaleco puede cubrir más del 70 %
    de lo visible: la regla la descarta y esa persona no se reporta.

    Se acepta el coste. La alternativa es abrir un incidente por cada chaleco
    suelto, que es justo el fallo que esta regla viene a corregir.
    """
    torso_recortado = _persona(1, (0, 100, 60, 200))

    assert not mc.parece_cuerpo(torso_recortado, [_epp("vest", (2, 110, 58, 195))])


# ---------- lo que se difumina ----------

def test_el_epp_sueto_sin_persona_no_abre_registro(completos) -> None:
    """Solo el chaleco, sin caja `Person`: no hay nadie a quien avisar."""
    monitor = MotorPrueba([([], [_epp("no_vest", CHALECO)], False)])

    assert monitor.procesar(_frame()) == []
    assert monitor.avisos == []
    assert monitor.episodio == {}


def test_el_epp_sueto_si_difumina_el_frame_entero(completos) -> None:
    """Sin caja de persona donde recortar, el anonimato cae sobre el frame entero."""
    monitor = MotorPrueba([([], [_epp("no_vest", CHALECO)], False)])

    monitor.procesar(_frame())

    assert monitor.avisos == []
    assert len(completos) == 1


# ---------- el modelo que se usa ----------

def _asignacion(arbol, nombre):
    for nodo in ast.walk(arbol):
        if isinstance(nodo, ast.Assign) and any(
                isinstance(objetivo, ast.Name) and objetivo.id == nombre
                for objetivo in nodo.targets):
            return nodo.value
    return None


def _nombres(raiz):
    """Todos los nombres que el archivo menciona, incluidos los importados."""
    nombres = {n.id for n in ast.walk(raiz) if isinstance(n, ast.Name)}
    for n in ast.walk(raiz):
        if isinstance(n, (ast.Import, ast.ImportFrom)):
            nombres.update(a.name for a in n.names)
            nombres.update(a.asname for a in n.names if a.asname)
    return nombres


def test_el_motor_prefiere_el_onnx_exportado() -> None:
    """El ONNX va primero: con él el agente corre sin PyTorch en CPU."""
    arbol = ast.parse((MOTOR / "motor_cascovision.py").read_text(encoding="utf-8"))
    candidatos = _asignacion(arbol, "_NOMBRES_MODELO")

    assert isinstance(candidatos, ast.Tuple)
    orden = [elemento.value for elemento in candidatos.elts]
    assert orden[0].endswith(".onnx")
    assert orden[1].endswith(".pt")


def test_si_falta_el_onnx_el_respaldo_es_el_pt() -> None:
    """El respaldo es el `.pt`: un ONNX que no está no es un modelo."""
    arbol = ast.parse((MOTOR / "motor_cascovision.py").read_text(encoding="utf-8"))
    eleccion = _asignacion(arbol, "RUTA_MODELO_EPP")

    assert isinstance(eleccion, ast.Call) and eleccion.func.id == "next"
    por_defecto = eleccion.args[1]
    assert isinstance(por_defecto, ast.Name) and por_defecto.id == "RUTA_MODELO_PT"


def test_exportar_onnx_parte_del_pt_nunca_del_onnx() -> None:
    """Exportar desde el ONNX ya exportado no sería exportar nada."""
    arbol = ast.parse((MOTOR / "exportar_onnx.py").read_text(encoding="utf-8"))
    nombres = _nombres(arbol)

    assert "RUTA_MODELO_PT" in nombres
    assert "RUTA_MODELO_EPP" not in nombres


def test_monitoreo_v1_toma_la_ruta_del_motor() -> None:
    """v1 la tenía escrita a mano y relativa al CWD: se habría quedado en el .pt."""
    arbol = ast.parse((MOTOR / "monitoreo_v1.py").read_text(encoding="utf-8"))

    assert "RUTA_MODELO_EPP" in _nombres(arbol)
    assert _asignacion(arbol, "RUTA_MODELO_EPP") is None
