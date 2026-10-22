"""Pruebas del difuminado de rostros (YuNet) y del ciclo de aviso.

El difuminado es el mecanismo de anonimizacion de la evidencia (RF-06): si
falla, las fotos de evidencia quedan con las caras visibles.

El ciclo de aviso evita que se sature al prevencionista sin callar la
informacion: el inicio se avisa de inmediato, mientras la persona sigue sin
EPP se reavisa con un ping periodico, y el cumplimiento cierra el registro
para constar cuando termino.
"""

import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pytest

MOTOR = Path(__file__).parents[1] / "Yolo" / "modelamiento"
sys.path.insert(0, str(MOTOR))

import motor_cascovision as mc  # noqa: E402


# ---------- difuminado ----------

def test_banda_dentro_devuelve_tamano_positivo() -> None:
    """La banda nunca puede medir menos de cero.

    YuNet entrega las cajas como (x, y, w, h). Si se interpretan como
    (x1, y1, x2, y2), el ancho sale negativo y el rostro no se difumina.
    """
    caja = (100.0, 200.0, 140.0, 260.0)  # x, y, w, h
    x, y, w, h = caja
    bx, by, bw, bh = mc.banda_dentro(
        (x, y, x + w, y + h), x + w / 2, y + h / 2, w * 0.55, h * 0.34)

    assert bw > 0
    assert bh > 0
    assert bx >= x
    assert by >= y


def test_detectar_rostros_devuelve_cajas_con_esquinas() -> None:
    """Las cajas deben venir como (x1, y1, x2, y2), con x2 > x1."""
    class FalsoDetector:
        """Simula la salida de YuNet: (x, y, w, h) mas landmarks."""

        def getInputSize(self):
            return (320, 240)

        def setInputSize(self, tamano):
            pass

        def detect(self, imagen):
            return None, np.array([[100.0, 50.0, 40.0, 60.0,
                                     110.0, 70.0, 130.0, 70.0]])

    imagen = np.zeros((240, 320, 3), dtype=np.uint8)
    caras = mc.detectar_rostros(FalsoDetector(), imagen)

    assert len(caras) == 1
    caja, ojos = caras[0]
    assert caja[2] > caja[0]  # x2 > x1
    assert caja[3] > caja[1]  # y2 > y1
    assert caja[2] - caja[0] == pytest.approx(40.0)
    assert caja[3] - caja[1] == pytest.approx(60.0)
    assert ojos == (110.0, 70.0, 130.0, 70.0)


def test_difumar_roi_modifica_la_region() -> None:
    """La banda difuminada debe quedar borrosa, no intacta."""
    class FalsoDetector:
        def getInputSize(self):
            return (200, 200)

        def setInputSize(self, tamano):
            pass

        def detect(self, imagen):
            return None, np.array([[80.0, 80.0, 40.0, 40.0,
                                     90.0, 100.0, 110.0, 100.0]])

    # Ruido: sin difuminar, los pixeles varian mucho.
    rng = np.random.default_rng(0)
    roi = rng.integers(0, 255, (200, 200, 3), dtype=np.uint8)
    antes = roi[80:120, 80:120].copy()

    n = mc.MonitorEPP._difumar_roi(FalsoDetector(), roi)

    assert n == 1
    despues = roi[80:120, 80:120]
    # La region difuminada pierde el detalle: la varianza baja.
    assert despues.std() < antes.std()


def test_difumar_roi_no_toca_lo_que_esta_fuera() -> None:
    class FalsoDetector:
        def getInputSize(self):
            return (200, 200)

        def setInputSize(self, tamano):
            pass

        def detect(self, imagen):
            return None, np.array([[80.0, 80.0, 40.0, 40.0,
                                     90.0, 100.0, 110.0, 100.0]])

    roi = np.zeros((200, 200, 3), dtype=np.uint8)
    mc.MonitorEPP._difumar_roi(FalsoDetector(), roi)

    # Fuera de la banda queda intacto.
    assert roi[0:50, 0:50].sum() == 0


# ---------- rastreo de la cara bajo sombra ----------
#
# El anonimato no admite fallos, y en obra las sombras duras sobre el rostro
# hacen que YuNet devuelva landmarks creíbles pero desplazados. Estas pruebas
# fijan que la zona única de ojos y nariz caiga sobre la cara aun asi.

def _detector_con(caja, ojos):
    """Detector falso que devuelve una cara dada como (x, y, w, h) y sus ojos."""

    class FalsoDetector:
        def getInputSize(self):
            return (400, 400)

        def setInputSize(self, tamano):
            pass

        def detect(self, imagen):
            if caja is None:
                return None, None
            fila = [*caja, *ojos]
            return None, np.array([fila], dtype=np.float32)

    return FalsoDetector()


def _cambio(antes, despues, y1, y2, x1, x2) -> bool:
    """True si la región fue difuminada (los pixeles cambiaron)."""
    return not np.array_equal(antes[y1:y2, x1:x2], despues[y1:y2, x1:x2])


def _roiso():
    """ROI con ruido, para que el difuminado sea medible."""
    return np.random.default_rng(1).integers(0, 255, (400, 400, 3), dtype=np.uint8)


def test_dimensiones_convierte_esquinas_a_ancho_alto() -> None:
    """Las cajas vienen como esquinas; las medidas relativas van sobre el ancho.

    Confundir x2 con el ancho hace que la banda salga oversized y que la
    validación de los ojos use una escala equivocada.
    """
    assert mc.dimensiones((100.0, 100.0, 200.0, 260.0)) == (100.0, 100.0, 100.0, 160.0)


def test_landmarks_buenos_se_aceptan() -> None:
    cara = (100.0, 100.0, 200.0, 260.0)
    ojos = (130.0, 167.0, 170.0, 167.0)

    assert mc.ojos_plausibles(cara, ojos)


def test_landmark_huido_a_la_siente_se_rechaza() -> None:
    """Con sombra el ojo se va a la sien: la banda saldría fuera del rostro."""
    cara = (100.0, 100.0, 200.0, 260.0)
    ojos = (130.0, 167.0, 250.0, 160.0)

    assert not mc.ojos_plausibles(cara, ojos)


def test_landmarks_demasiado_juntos_se_rechazan() -> None:
    cara = (100.0, 100.0, 200.0, 260.0)
    ojos = (145.0, 167.0, 155.0, 167.0)

    assert not mc.ojos_plausibles(cara, ojos)


def test_landmarks_a_distinta_altura_se_rechazan() -> None:
    cara = (100.0, 100.0, 200.0, 260.0)
    ojos = (130.0, 167.0, 170.0, 230.0)

    assert not mc.ojos_plausibles(cara, ojos)


def test_landmarks_fuera_de_la_cara_se_rechazan() -> None:
    cara = (100.0, 100.0, 200.0, 260.0)
    ojos = (210.0, 167.0, 250.0, 167.0)

    assert not mc.ojos_plausibles(cara, ojos)


def test_landmarks_aceptados_dan_una_sola_zona() -> None:
    """Los ojos válidos anclan UN rectángulo que los cruza y baja a la nariz."""
    cara = (100.0, 100.0, 200.0, 260.0)
    zona = mc.zona_ojos_nariz(cara, (130.0, 167.0, 170.0, 167.0))

    x, y, w, h = zona
    # Un único rectángulo, contenido en la cara.
    assert cara[0] <= x and x + w <= cara[2]
    assert cara[1] <= y and y + h <= cara[3]
    # Cruza los dos ojos de lado a lado, sin dejar hueco entre ellos.
    assert x <= 130.0 and 170.0 <= x + w
    # Y baja hasta la nariz (~0.60 de la altura de la cara: y = 196).
    assert y <= 167.0 < y + h
    assert y + h >= 196
    # Y sube hasta las cejas (~0.35: y = 156).
    assert y <= 156


def test_landmarks_rechazados_caen_a_la_anatomia() -> None:
    """Con ojos implausibles se usa la posición anatómica, dentro de la cara."""
    cara = (100.0, 100.0, 200.0, 260.0)
    zona = mc.zona_ojos_nariz(cara, (130.0, 167.0, 250.0, 160.0))

    x, y, w, h = zona
    assert cara[0] <= x
    assert x + w <= cara[2]
    assert cara[1] <= y
    assert y + h <= cara[3]
    # Queda centrada en el eje de la cara, que es donde están los dos ojos.
    assert x <= (cara[0] + cara[2]) / 2.0 <= x + w


def test_landmark_huido_no_deja_la_cara_sin_difuminar() -> None:
    """Regresión del caso reportado: sombra desplaza un ojo y YuNet sigue
    devolviendo la cara. Antes la banda salía fuera y el rostro quedaba
    identificable; ahora se cae a la anatomía y sale una zona única que deja
    también cubierto el puente entre los ojos, que era el hueco que quedaba."""
    roi = _roiso()
    antes = roi.copy()
    # Cara 100x100 en (100,100); ojo izquierdo huido a la sien (250,160).
    detector = _detector_con((100.0, 100.0, 100.0, 100.0),
                             (130.0, 167.0, 250.0, 160.0))

    assert mc.difumar_roi(detector, roi) == 1
    # Zona única x 111..189, y 130..168: cejillas, ojos y nariz de un tirón.
    assert _cambio(antes, roi, 130, 168, 111, 189)
    # El puente entre los dos ojos ya no queda al descubierto.
    assert _cambio(antes, roi, 140, 160, 145, 155)


def test_sombra_profunda_usa_la_caja_de_cabeza() -> None:
    """Sin cara detectada, la caja de cabeza de YOLO sostiene la zona."""
    roi = _roiso()
    antes = roi.copy()
    cabezas = [{"caja": (110, 100, 190, 200)}]

    assert mc.difuminar_cabeza(roi, cabezas, (0, 0)) == 1
    # Con casco o sin él, la cara empieza bajo el borde: zona única
    # x 121..178, y 130..180 dentro de la caja de cabeza.
    assert _cambio(antes, roi, 130, 180, 121, 178)
    # El centro, donde cae el puente entre los ojos, también queda difuminado.
    assert _cambio(antes, roi, 145, 165, 145, 155)


def test_sin_cara_ni_cabeza_usa_la_proporcion_de_la_persona() -> None:
    """Último respaldo: sin ninguna detección, la cabeza ocupa la parte alta."""
    roi = _roiso()
    antes = roi.copy()

    assert mc.difuminar_cabeza_persona(roi) == 1
    assert _cambio(antes, roi, 20, 55, 130, 170)


def test_difumar_rostros_no_se_queda_sin_cobertura() -> None:
    """La cadena completa siempre difumina algo, sea cual sea el fallo."""
    frame = _roiso()
    antes = frame.copy()
    detector = _detector_con(None, ())

    assert mc.difumar_rostros(detector, frame, (100, 100, 300, 380), []) == 1
    assert _cambio(antes, frame, 130, 175, 165, 235)


def test_iluminacion_normalizada_no_destruye_la_imagen() -> None:
    """CLAHE recupera contraste local sin arruinar el color ni el tamaño."""
    imagen = np.random.default_rng(2).integers(0, 255, (120, 160, 3), dtype=np.uint8)

    salida = mc.normalizar_iluminacion(imagen)

    assert salida.shape == imagen.shape
    assert salida.dtype == imagen.dtype
    assert not np.array_equal(salida, imagen)


def test_iluminacion_normalizada_no_modifica_el_original() -> None:
    """La evidencia se guarda con el frame original, no con el igualado."""
    imagen = np.random.default_rng(3).integers(0, 255, (120, 160, 3), dtype=np.uint8)
    copia = imagen.copy()

    mc.normalizar_iluminacion(imagen)

    assert np.array_equal(imagen, copia)


# ---------- ciclo de vida del aviso: inicio, ping y fin ----------

class MonitorFalso:
    """Ejercita el ciclo de aviso sin cargar el modelo de deteccion."""

    def __init__(self, ping_segundos=60):
        self.ping_segundos = ping_segundos
        self.violacion_confirmada = {}
        self.estado_confirmado = {}
        self.episodio = {}
        self.en_espera = []
        self.historial = {}
        self.ultimo_estado = {}
        self.ultimo_visto = {}
        self.caja_vista = {}
        self.al_registrar = None
        self.n_frames = 0

    _registrar_cambio = mc.MonitorEPP._registrar_cambio
    _retomar_episodio = mc.MonitorEPP._retomar_episodio
    _controlar_ping = mc.MonitorEPP._controlar_ping
    _depurar_invisibles = mc.MonitorEPP._depurar_invisibles
    _cerrar_episodio = mc.MonitorEPP._cerrar_episodio
    _consola = staticmethod(lambda pid, estado, evento="inicio": None)


def _episodio_registrado():
    """Episodio cuyo INICIO llego a registrarse, como queda en produccion."""
    ahora = time.monotonic()
    return {"inicio": ahora, "ultimo_ping": ahora, "pings": 0,
            "incidente": {"episode_id": "ep-1", "event": "inicio",
                          "violation_types": ["sin_casco", "sin_chaleco"],
                          "ping_count": 0}}


def test_primera_infraccion_se_notifica_de_inmediato() -> None:
    """El inicio se avisa al instante, sin esperar el ping de nadie."""
    monitor = MonitorFalso()
    nuevos = {}

    evento = monitor._registrar_cambio(1, frozenset({"sin_casco"}), 0.9, nuevos)

    assert evento == "inicio"
    assert nuevos[1][2] == "inicio"


def test_misma_infraccion_no_genera_un_inicio_nuevo() -> None:
    """La persona sigue sin EPP: no se abre un registro nuevo."""
    monitor = MonitorFalso()
    monitor._registrar_cambio(1, frozenset({"sin_casco"}), 0.9, {})

    nuevos2 = {}
    evento = monitor._registrar_cambio(1, frozenset({"sin_casco"}), 0.9, nuevos2)

    assert evento is None
    assert nuevos2 == {}


def test_ping_se_emite_al_vencer_el_intervalo() -> None:
    """Con la misma infraccion mantenida, toca ping al cumplirse el intervalo."""
    monitor = MonitorFalso(ping_segundos=60)
    monitor._registrar_cambio(1, frozenset({"sin_casco"}), 0.9, {})

    # Se simula el paso del tiempo venciendo el intervalo del episodio.
    monitor.episodio[1]["ultimo_ping"] -= 60

    nuevos = {}
    evento = monitor._registrar_cambio(1, frozenset({"sin_casco"}), 0.9, nuevos)

    assert evento == "ping"
    assert nuevos[1][2] == "ping"


def test_ping_no_se_emite_antes_del_intervalo() -> None:
    monitor = MonitorFalso(ping_segundos=60)
    monitor._registrar_cambio(1, frozenset({"sin_casco"}), 0.9, {})

    nuevos = {}
    evento = monitor._registrar_cambio(1, frozenset({"sin_casco"}), 0.9, nuevos)

    assert evento is None
    assert nuevos == {}


def test_ping_desactivado_con_cero() -> None:
    """Con el ping desactivado solo se avisan el inicio y el fin."""
    monitor = MonitorFalso(ping_segundos=0)
    monitor._registrar_cambio(1, frozenset({"sin_casco"}), 0.9, {})

    monitor.episodio[1]["ultimo_ping"] -= 9999
    nuevos = {}
    evento = monitor._registrar_cambio(1, frozenset({"sin_casco"}), 0.9, nuevos)

    assert evento is None
    assert nuevos == {}


def test_otra_persona_sin_epp_se_avisa_inmediatamente() -> None:
    """Si aparece otra persona sin EPP, no espera el ping de la primera.

    El numero de personas en infraccion aumento: es información nueva para el
    prevencionista.
    """
    monitor = MonitorFalso(ping_segundos=60)
    monitor._registrar_cambio(1, frozenset({"sin_casco"}), 0.9, {})

    # La persona 1 esta a mitad de su ventana de ping.
    monitor.episodio[1]["ultimo_ping"] -= 30

    nuevos = {}
    monitor._registrar_cambio(2, frozenset({"sin_casco"}), 0.9, nuevos)

    assert nuevos[2][2] == "inicio"


def test_cumplimiento_cierra_el_registro() -> None:
    """Cuando la persona cumple se avisa el fin del registro."""
    monitor = MonitorFalso()
    monitor._registrar_cambio(1, frozenset({"sin_casco"}), 0.9, {})

    nuevos = {}
    evento = monitor._registrar_cambio(1, frozenset(), 0.9, nuevos)

    assert evento == "fin"
    assert nuevos[1][2] == "fin"


def test_cumplimiento_sin_registro_previo_no_avisa() -> None:
    monitor = MonitorFalso()
    nuevos = {}

    evento = monitor._registrar_cambio(1, frozenset(), 0.9, nuevos)

    assert evento is None
    assert nuevos == {}


def test_reincidir_tras_cumplir_abre_un_registro_nuevo() -> None:
    """El fin cierra el episodio: volver a estar sin EPP es un hecho nuevo."""
    monitor = MonitorFalso()
    monitor._registrar_cambio(1, frozenset({"sin_casco"}), 0.9, {})
    monitor._registrar_cambio(1, frozenset(), 0.9, {})
    # El cierre lo despacha _registrar; aqui se simula ese cierre.
    monitor.episodio.pop(1, None)

    nuevos = {}
    monitor._registrar_cambio(1, frozenset({"sin_casco"}), 0.9, nuevos)

    assert nuevos[1][2] == "inicio"


def test_personas_distintas_tienen_su_propio_ping() -> None:
    """El ping es por persona: una no bloquea el aviso de la otra."""
    monitor = MonitorFalso(ping_segundos=60)
    monitor._registrar_cambio(1, frozenset({"sin_casco"}), 0.9, {})
    monitor._registrar_cambio(2, frozenset({"sin_casco"}), 0.9, {})

    monitor.episodio[1]["ultimo_ping"] -= 60
    monitor.episodio[2]["ultimo_ping"] -= 10

    nuevos = {}
    monitor._registrar_cambio(1, frozenset({"sin_casco"}), 0.9, nuevos)
    monitor._registrar_cambio(2, frozenset({"sin_casco"}), 0.9, nuevos)

    assert set(nuevos) == {1}
    assert nuevos[1][2] == "ping"


# ---------- ventanas de ping por script ----------

def test_monitoreo_v1_usa_30_segundos() -> None:
    """`monitoreo_v1` es la variante con el ping más frecuente."""
    import ast

    ruta = MOTOR / "monitoreo_v1.py"
    arbol = ast.parse(ruta.read_text(encoding="utf-8"))

    valor = None
    for n in ast.walk(arbol):
        if isinstance(n, ast.Assign):
            for t in n.targets:
                if getattr(t, "id", "") == "PING_SEGUNDOS":
                    valor = n.value.value

    assert valor == 30


def test_monitoreo_v1_tiene_la_gracia_de_cierre() -> None:
    """La variante de 30 s también retiene el episodio en vez de cerrarlo.

    Comparte con el motor la constante de gracia y el alcance de reaparición,
    y define su propio retome sobre la clave de la falta: si alguna de esas
    piezas desaparece, un parpadeo del detector vuelve a partir la infracción
    en dos registros.
    """
    import ast

    ruta = MOTOR / "monitoreo_v1.py"
    arbol = ast.parse(ruta.read_text(encoding="utf-8"))

    nombres = {n.id for n in ast.walk(arbol) if isinstance(n, ast.Name)}
    llamadas = {n.func.id for n in ast.walk(arbol)
                if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)}
    funciones = {n.name for n in ast.walk(arbol) if isinstance(n, ast.FunctionDef)}

    assert "GRACIA_CIERRE_SEGUNDOS" in nombres, "no comparte la gracia con el motor"
    assert "FRAME_PARA_DESCARTAR" in nombres, "no descarta a los que dejaron de verse"
    assert "retomar_episodio" in llamadas, "no retoma el episodio al volver"
    assert {"clave_falta", "retomar_episodio"} <= funciones


# ---------- la logica real de la variante de 30 s ----------
#
# `monitoreo_v1` abre la camara al importarse, asi que no se puede importar el
# script entero en un test. Se extraen por AST sus funciones puras y se corren
# contra estados en memoria, que es justo por donde se colaba el bug: la falta
# se identifica por su clave y no por el nombre crudo que le puso el detector.

def _utilidades_v1():
    """`CLAVES_FALTA`, `clave_falta` y `retomar_episodio` de `monitoreo_v1`."""
    import ast
    import math

    ruta = MOTOR / "monitoreo_v1.py"
    arbol = ast.parse(ruta.read_text(encoding="utf-8"))

    nodos = []
    for n in arbol.body:
        if isinstance(n, ast.Assign) and any(
                getattr(t, "id", "") == "CLAVES_FALTA" for t in n.targets):
            nodos.append(n)
        elif isinstance(n, ast.FunctionDef) and n.name in ("clave_falta",
                                                           "retomar_episodio"):
            nodos.append(n)

    assert len(nodos) == 3, "falta alguna pieza de la gracia en monitoreo_v1"

    ns = {
        "math": math,
        "centro_caja": mc.centro_caja,
        "caja_vista": {},
        "en_espera": [],
        "episodios": {},
    }
    exec(compile(ast.Module(body=nodos, type_ignores=[]), str(ruta), "exec"), ns)
    return ns


def _en_espera(ns, clave, caja=(100, 50, 200, 300)):
    """Deja un episodio en espera, como hace la variante de 30 s al perderla."""
    episodio = {"inicio": 100.0, "ultimo_ping": 100.0}
    ns["en_espera"].append({"pid": 3, "clave": clave,
                            "centro": mc.centro_caja(caja),
                            "radio": mc.alcance_reaparicion(caja),
                            "episodio": episodio, "perdido": 0.0})
    return episodio


def test_v1_una_falta_con_otro_nombre_no_abre_otro_registro() -> None:
    """El detector alterna entre 'no_helmet' y 'falta_helmet': es la misma falta."""
    ns = _utilidades_v1()
    clave_falta = ns["clave_falta"]

    assert clave_falta(("no_helmet",)) == clave_falta(("falta_helmet",))
    assert clave_falta(("no_helmet", "no_vest")) == clave_falta(
        ("falta_helmet", "falta_vest"))
    assert clave_falta(()) == ()
    assert clave_falta(("no_helmet",)) != clave_falta(("no_vest",))


def test_v1_retoma_el_episodio_si_vuelve_al_mismo_sitio() -> None:
    """Vuelve con otro id de ByteTrack, pero sigue siendo el mismo registro."""
    ns = _utilidades_v1()
    episodio = _en_espera(ns, ("sin_casco",))
    ns["caja_vista"][21] = (110, 60, 210, 310)

    assert ns["retomar_episodio"](21, ("sin_casco",)) is True
    assert ns["episodios"][21] is episodio
    assert ns["en_espera"] == []


def test_v1_no_retoma_si_reaparece_en_otro_lado() -> None:
    """Entra alguien distinto por el otro extremo: no hereda el registro."""
    ns = _utilidades_v1()
    episodio = _en_espera(ns, ("sin_casco",))
    ns["caja_vista"][21] = (1600, 60, 1700, 310)

    assert ns["retomar_episodio"](21, ("sin_casco",)) is False
    assert ns["en_espera"][0]["episodio"] is episodio
    assert ns["episodios"] == {}


def test_v1_no_retoma_si_la_falta_es_otra() -> None:
    """Quien se fue sin casco no le regala su registro a quien va sin chaleco."""
    ns = _utilidades_v1()
    _en_espera(ns, ("sin_casco",))
    ns["caja_vista"][21] = (110, 60, 210, 310)

    assert ns["retomar_episodio"](21, ("sin_chaleco",)) is False
    assert len(ns["en_espera"]) == 1
    assert ns["episodios"] == {}


def test_los_tres_scripts_de_monitoreo_difuminan() -> None:
    """Los tres deben difuminar los rostros con YuNet."""
    import ast

    for nombre in ("monitoreo_v1", "monitoreo_v2", "monitoreo_api"):
        ruta = MOTOR / f"{nombre}.py"
        arbol = ast.parse(ruta.read_text(encoding="utf-8"))

        llamadas = {n.func.id for n in ast.walk(arbol)
                    if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)}
        # `monitoreo_v2` y `monitoreo_api` difuminan a traves del motor.
        assert ("difumar_rostros" in llamadas
                or "MonitorEPP" in llamadas), nombre


# ---------- el detector de 'Person' parpadea ----------
#
# En camara real la clase 'Person' no se detecta siempre: gafas, sombra o un
# perfil raro la hacen desaparecer del frame aunque la persona no se haya
# movido, y ByteTrack le reparte otro id al volver. Ese parpadeo partia una
# sola infraccion en dos registros (FIN y, segundos despues, INICIO con otro
# numero) y dejaba la cara sin difuminar en los frames sin persona.

def _persona(pid, caja=(100, 50, 200, 300)):
    return {"id": pid, "caja": caja, "conf": 0.9, "nombre": "Person"}


def _sin_epp():
    """Las dos faltas, con sus cajas dentro de la persona de arriba."""
    return [{"id": 90, "caja": (110, 55, 190, 110), "conf": 0.8,
             "nombre": "no_helmet"},
            {"id": 91, "caja": (105, 130, 195, 280), "conf": 0.8,
             "nombre": "no_vest"}]


class RostroFalso:
    """YuNet de mentira: encuentra siempre una cara que ocupa el frame."""

    def getInputSize(self):
        return (0, 0)

    def setInputSize(self, tamano):
        pass

    def detect(self, imagen):
        alto, ancho = imagen.shape[:2]
        return None, np.array([[0.0, 0.0, float(ancho), float(alto),
                                ancho * 0.3, alto * 0.42,
                                ancho * 0.7, alto * 0.42]], dtype=np.float32)


class MotorPrueba(mc.MonitorEPP):
    """Motor entero con detecciones programadas, sin cargar YOLO ni YuNet."""

    def __init__(self, escenas):
        self.detector = RostroFalso()
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
        self.avisos = []
        self.al_registrar = self.avisos.append

    def _detectar(self, frame):
        return next(self.escenas)

    def guardar_evidencia(self, frame):
        return "incidents/2026/01/01/prueba.jpg", datetime.now(timezone.utc)

    def difumar_rostros(self, frame, persona, cabezas):
        """Sustituye el difuminado por persona: aqui solo se cuentan llamadas."""
        return 1

    @staticmethod
    def _consola(pid, estado, evento="inicio"):
        pass


def _frames_motor():
    return np.random.default_rng(5).integers(0, 255, (400, 300, 3),
                                              dtype=np.uint8)


def _episodio_en_espera(monitor, pid, estados, caja):
    """Pierde a la persona de vista y devuelve los cierres de ese frame."""
    monitor.ultimo_visto[pid] = 0
    monitor.caja_vista[pid] = caja
    monitor.violacion_confirmada[pid] = mc.clave_violacion(estados)
    monitor.episodio[pid] = _episodio_registrado()
    monitor.n_frames = mc.FRAME_PARA_DESCARTAR + 1
    return monitor._depurar_invisibles()


def test_perder_a_la_persona_no_cierra_el_registro() -> None:
    """Un parpadeo del detector no emite FIN: el episodio se aparta a espera."""
    monitor = MonitorFalso()

    cierres = _episodio_en_espera(monitor, 7,
                                  frozenset({"sin_casco", "sin_chaleco"}),
                                  (100, 50, 200, 300))

    assert cierres == []
    assert monitor.episodio == {}
    assert len(monitor.en_espera) == 1
    assert monitor.en_espera[0]["clave"] == (
        "missing_helmet", "missing_reflective_vest")


def test_reaparicion_con_otro_id_retoma_el_mismo_registro() -> None:
    """ByteTrack da otro id al volver: sigue siendo el mismo episodio."""
    monitor = MonitorFalso()
    _episodio_en_espera(monitor, 3, frozenset({"sin_casco", "sin_chaleco"}),
                        (100, 50, 200, 300))

    nuevos = {}
    evento = monitor._registrar_cambio(21, frozenset({"sin_casco", "sin_chaleco"}),
                                       0.9, nuevos, (110, 60, 210, 310))

    assert monitor.en_espera == []
    assert 21 in monitor.episodio
    # No se abrio un registro nuevo, asi que no hay nada que avisar aun.
    assert evento != "inicio"
    assert nuevos == {}
    assert monitor.episodio[21]["incidente"]["episode_id"] == "ep-1"


def test_reaparicion_en_otra_parte_del_encuadre_abre_un_registro_nuevo() -> None:
    """Si aparece alguien distinto, no se apropia del episodio del anterior."""
    monitor = MonitorFalso()
    # Caja pequena: la espera solo admite reaparecer a 300 px de donde se fue.
    _episodio_en_espera(monitor, 3, frozenset({"sin_casco"}), (100, 50, 160, 200))

    nuevos = {}
    evento = monitor._registrar_cambio(21, frozenset({"sin_casco"}), 0.9,
                                       nuevos, (700, 50, 760, 200))

    assert evento == "inicio"
    assert nuevos[21][2] == "inicio"
    # El episodio del anterior sigue apartado, a la espera de su cierre.
    assert len(monitor.en_espera) == 1


def test_el_episodio_en_espera_se_cierra_al_vencer_la_gracia() -> None:
    """Si la persona no vuelve, el registro se cierra: ya no se le ve."""
    monitor = MonitorFalso()
    _episodio_en_espera(monitor, 3, frozenset({"sin_casco", "sin_chaleco"}),
                        (100, 50, 200, 300))
    monitor.en_espera[0]["perdido"] -= mc.GRACIA_CIERRE_SEGUNDOS + 1

    cierres = monitor._depurar_invisibles()

    assert len(cierres) == 1
    assert cierres[0]["event"] == "fin"
    assert cierres[0]["episode_id"] == "ep-1"
    assert monitor.en_espera == []


def test_sin_deteccion_de_persona_se_sigue_difuminando(monkeypatch) -> None:
    """'Personas: 0' con EPP a la vista no puede dejar la cara al descubierto.

    Este es el fallo reportado: YOLO no acierta 'Person' detras de los lentes,
    la lista de personas queda vacia y el difuminado, que se apoyaba en ella,
    no se ejecutaba.
    """
    llamadas = []
    original = mc.difumar_roi

    def contando(detector, frame):
        llamadas.append(1)
        return original(detector, frame)

    monkeypatch.setattr(mc, "difumar_roi", contando)
    motor = MotorPrueba([([], _sin_epp(), True)])
    frame = _frames_motor()
    antes = frame.copy()

    motor.procesar(frame)

    assert llamadas == [1]
    # La zona única cubre la línea de los ojos...
    assert not np.array_equal(frame[130:210, 40:100], antes[130:210, 40:100])
    # ...y también la nariz, que antes quedaba por debajo de las bandas.
    assert not np.array_equal(frame[240:290, 40:100], antes[240:290, 40:100])
    # Lo que queda fuera de la zona sigue intacto.
    assert np.array_equal(frame[330:380, 30:90], antes[330:380, 30:90])


def test_con_persona_detectada_no_se_difumina_el_frame_entero(monkeypatch) -> None:
    """El respaldo es solo para cuando falta la caja de la persona."""
    llamadas = []
    monkeypatch.setattr(mc, "difumar_roi",
                        lambda detector, frame: llamadas.append(1) or 0)
    motor = MotorPrueba([([_persona(3)], _sin_epp(), True)])

    motor.procesar(_frames_motor())

    assert llamadas == []


def test_un_parpadeo_no_parte_la_infraccion_en_dos_registros() -> None:
    """Caso reportado: sin EPP, sin salir de la camara, detectado dos veces.

    Sin la gracia, al perderse a 'Person' se emitia FIN y al volver, con un id
    nuevo, se abria otro INICIO: dos infracciones para una sola persona.
    """
    con_persona = ([_persona(3)], _sin_epp(), True)
    sin_persona = ([], _sin_epp(), True)
    vuelve = ([_persona(21)], _sin_epp(), True)
    escenas = [con_persona] * 3 + [sin_persona] * 50 + [vuelve] * 3
    motor = MotorPrueba(escenas)

    for _ in escenas:
        motor.procesar(_frames_motor())

    assert [a["event"] for a in motor.avisos] == ["inicio"]
    assert motor.en_espera == []
    assert 21 in motor.episodio
