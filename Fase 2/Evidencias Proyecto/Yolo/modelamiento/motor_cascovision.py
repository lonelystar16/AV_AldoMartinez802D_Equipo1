"""Motor de análisis de EPP de CascoVision.

Reune la lógica de detección de casco y chaleco, el difuminado de rostros y el
registro de incidentes. `monitoreo_v2.py` lo ejecuta contra la cámara local y
`monitoreo_api.py` lo reutiliza para reportar los incidentes a la API REST.

El detector works con 5 clases: `helmet`, `no_helmet`, `no_vest`, `Person` y
`vest`. Las clases negativas (`no_helmet`, `no_vest`) son detecciones positivas
de una infracción: ya no hay que inferirla por la ausencia de un casco.
"""

import math
import time
import urllib.request
import uuid
from collections import deque
from datetime import datetime, timezone
from pathlib import Path

import cv2
from ultralytics import YOLO

from zonas import zona_de

# ==================== CONFIGURACIÓN ====================


def buscar_raiz_proyecto(inicio: Path) -> Path:
    """Sube desde el script hasta encontrar la carpeta que contiene 'Fase 2'."""
    for carpeta in (inicio, *inicio.parents):
        if (carpeta / "Fase 2").is_dir():
            return carpeta
    return inicio.parents[3]


RAIZ = buscar_raiz_proyecto(Path(__file__).resolve().parent)

# El .onnx va primero: ya está exportado (tarea 4.3) y con él el agente corre
# sin PyTorch en CPU, que es lo que permite aligerar la imagen de Docker. El
# .pt sigue siendo el origen, así que es el respaldo si el ONNX no está.
_RUTA_CARPETA_MODELO = Path("Fase 2") / "Evidencias Proyecto" / "models"
_NOMBRES_MODELO = ("cascovision_yolo26s.onnx", "cascovision_yolo26s.pt")
# Exportar y evaluar parten siempre del .pt, nunca del ONNX ya exportado.
RUTA_MODELO_PT = RAIZ / _RUTA_CARPETA_MODELO / "cascovision_yolo26s.pt"
_CANDIDATOS = [raiz / _RUTA_CARPETA_MODELO / nombre
               for raiz in (RAIZ, Path.cwd())
               for nombre in _NOMBRES_MODELO]
RUTA_MODELO_EPP = next((p for p in _CANDIDATOS if p.is_file()), RUTA_MODELO_PT)

# Detector de rostros YuNet. Es una red neuronal, no una cascada Haar: detecta
# frontales y de perfil, y entrega las coordenadas de ambos ojos como landmarks.
RUTA_YUNET = RAIZ / "Fase 2" / "Evidencias Proyecto" / "models" / "face_detection_yunet_2023mar.onnx"
URL_YUNET = ("https://github.com/opencv/opencv_zoo/raw/main/models/"
             "face_detection_yunet/face_detection_yunet_2023mar.onnx")
YUNET_UMBRAL = 0.6
YUNET_NMS = 0.3

CONF_MIN = 0.20

# Confianza mínima por clase: un positivo flojo no debe "limpiar" una infracción.
# Umbrales calibrados sobre el detector de 5 clases; ver
# `Yolo/README.md` para el protocolo de calibración.
CONF_MIN_POR_CLASE = {
    "Person": 0.40,
    "helmet": 0.30,
    "no_helmet": 0.30,
    "no_vest": 0.30,
    "vest": 0.35,
}

CLASE_PERSONA = "Person"

# Tracker de seguimiento. Se fija explicitamente porque el checkpoint trained
# arrastra 'tracktrack.yaml' en sus args y ese devuelve boxes.id nulo.
TRACKER = "bytetrack.yaml"

# El detector tiene 5 clases y todas son del producto: no hay clases que
# descartar (a diferencia del modelo de 11 clases anterior, que ignoraba guantes,
# botas, gafas y otros implementos).
CLASES_PERMITIDAS = {"Person", "helmet", "no_helmet", "no_vest", "vest"}

# Clases que anclan la cabeza, usadas como respaldo si YuNet no encuentra un rostro.
CLASES_CABEZA = {"helmet", "no_helmet"}

SOLAPAMIENTO_MIN = 0.35

# Fracción de la caja 'Person' que puede estar cubierta por el propio EPP
# antes de sospechar que esa caja no describe a una persona. Ver `parece_cuerpo`.
UMBRAL_EPP_CUBRE_PERSONA = 0.7

VENTANA_SUAVIZADO = 5
MIN_FRAMES_PARA_ALERTAR = 2
FRAME_PARA_DESCARTAR = 45

# La deteccion de 'Person' parpadea (gafas, sombra, perfil) y ByteTrack reparte
# un id nuevo al volver. Cerrando el episodio en ese hueco, una persona que
# nunca salio de la camara acabaria partida en varias infracciones: FIN, y unos
# segundos despues un INICIO con otro numero. El episodio se pone en espera en
# vez de cerrarse, y se retoma si la persona reaparece con la misma infraccion.
# Solo se cierra de verdad cuando la espera supera este tiempo.
GRACIA_CIERRE_SEGUNDOS = 15

# Distancia maxima a la que se admite que reaparezca la misma persona, medida
# en cajas de la propia persona. Evita enganchar el episodio de alguien que se
# fue a una persona distinta que entra por otro lado del encuadre.
GRACIA_CIERRE_CAJAS = 2.0

# --- Ciclo de vida del aviso de una persona sin EPP ---
#
# El objetivo no es callar al repetidor, sino mantener el aviso vivo. Una
# persona que sigue sin EPP genera un "ping" periodico que confirma que la
# situacion no cambia, sin abrir un registro nuevo cada vez.
#
# Los tres momentos del ciclo:
#
#   INICIO: la persona aparece sin EPP. Se avisa de inmediato y queda
#           registrado el momento en que empieza.
#   PING:   la persona sigue sin EPP. Cada PING_SEGUNDOS se reenvia el aviso
#           con los datos ya registrados, para que conste que la situacion
#           persiste. No crea un incidente nuevo.
#   FIN:    la persona se pone el EPP (o se pierde de vista). Se avisa del
#           cierre para que conste cuando termino el registro.
#
# Si aparece OTRA persona sin EPP, su INICIO se avisa de inmediato aunque haya
# un ping pendiente de la anterior: el numero de personas en infraccion aumento
# y eso es informacion nueva para el prevencionista.
#
# PING_SEGUNDOS = 0 desactiva el ping (solo se avisa el inicio y el fin).
PING_SEGUNDOS = 60

# Un ping no crea un incidente nuevo, sino que reenvia el ya registrado con
# este marcador. La API lo usa para actualizar el incidente en vez de crear otro.
TIPO_EVENTO = "ping"

# --- Zonas de riesgo ---
#
# Sin zonas configuradas el motor sigue siendo el de siempre: mira a todo el
# mundo y reporta a todo el mundo. Con zonas, solo se abre registro de quien
# está dentro de alguna; ver `zonas.py` y `monitoreo_sector.py`.
#
# Valores por defecto para los agentes que no configuran nada: hoy están
# escritos a mano en el incidente, y quedan aquí para no cambiar el
# comportamiento al introducir el parámetro.
CAMARA_POR_DEFECTO = "camara-01"
ZONA_POR_DEFECTO = "zona-norte"

# --- Difuminado a escala ---
#
# El anonimato no admite fallos, pero en obra las sombras duras sobre el rostro
# hacen que YuNet deje de encontrar la cara, o que la encuentre y devuelva
# landmarks creíbles pero desplazados. Por eso la zona no se localiza por una
# sola señal, sino por una cadena de respaldos, de más a menos precisa:
#
#   0. iluminación igualada (CLAHE) antes de mirar: recupera lo que la sombra
#      esconde, y es lo que hace que YuNet encuentre la cara;
#   1. landmarks de YuNet, solo si son coherentes con la geometría de la cara;
#   2. envolvente anatómica de ojos y nariz sobre la caja de la cara;
#   3. caja de cabeza detectada por YOLO (helmet / no_helmet);
#   4. proporción de la cabeza sobre la caja de la persona.
#
# Cada rostro se difumina con UN solo rectángulo que cruza los dos ojos y baja
# hasta la nariz. No es una banda por ojo: lo que deja identificable a una
# persona es el conjunto ojos-nariz pegado, y dejar un hueco entre bandas
# deja a la vista la mitad del rasgo.
#
# La envolvente anatómica (ZONA_ARIBA..ZONA_ABAJO) es el suelo: siempre cubre
# cejillas y punta de la nariz. Los landmarks de YuNet solo pueden ensancharla
# hacia arriba o hacia abajo, nunca estrecharla, porque suelen salir altos en
# las cajas que incluyen pelo o casco.
ZONA_REL_CENTRO_X = 0.50           # centro horizontal sin landmarks / ancho cara
ZONA_REL_ANCHO = 0.78              # ancho de la zona / ancho de la cara
ZONA_ARIBA = 0.30                  # borde superior / alto de la cara (cejillas)
ZONA_ABAJO = 0.68                  # borde inferior / alto de la cara (nariz)
ZONA_OJO_MARGEN = 0.12             # margen sobre la línea de ojos / alto cara
ZONA_OJO_BAJA = 0.20               # descenso bajo la línea de ojos / alto cara
ZONA_SEP_REL = 1.9                 # ancho mínimo: separación entre ojos * esto

# Validación de los landmarks de YuNet. Con sombras sigue devolviendo puntos,
# pero movidos a la sien, la mejilla o la ceja; confiar en ellos deja el
# rostro identificable. Solo se aceptan si son coherentes con la cara.
OJO_SEP_MIN = 0.30                 # separación mínima entre ojos / ancho de cara
OJO_SEP_MAX = 0.80                 # separación máxima entre ojos / ancho de cara
OJO_DESVIO_MAX_Y = 0.15            # desnivel permitido entre ojos / alto de cara
OJO_X_MIN, OJO_X_MAX = 0.08, 0.92  # rango horizontal admitido dentro de la cara
OJO_Y_MAX = 0.80                   # rango vertical admitido dentro de la cara

# Caja de cabeza (helmet / no_helmet) cuando YuNet no encuentra la cara. Esa
# caja puede llevar el casco puesto, así que la zona se ancla por debajo del
# borde y cubre la mitad inferior de la caja, que es donde está la cara.
CABEZA_ZONA_REL_Y = 0.55
CABEZA_ZONA_REL_ANCHO = 0.72
CABEZA_ZONA_REL_ALTO = 0.50

# Último respaldo, sobre la caja de la persona: sin rostro ni cabeza detectados
# (de espaldas, capucha, sombra profunda) la cabeza ocupa la parte alta del
# cuerpo y la cara cae cerca del borde superior.
PERSONA_ZONA_REL_Y = 0.115
PERSONA_ZONA_REL_ANCHO = 0.26
PERSONA_ZONA_REL_ALTO = 0.13

COLORES = {
    "helmet": (0, 255, 0),       # Verde para casco
    "vest": (255, 255, 0),       # Celeste/Cian para chaleco
    "Person": (255, 0, 0),       # Azul para persona
    "no_helmet": (0, 255, 255),  # Amarillo: cabeza sin casco
    "no_vest": (255, 0, 255),    # Magenta: torso sin chaleco
}
COLOR_TEXTO = (255, 255, 255)
COLOR_CONTORNO = (0, 0, 0)
FONT = cv2.FONT_HERSHEY_SIMPLEX

# Estados de una persona y su equivalencia en la API.
#   "falta_casco"   -> no se detecto 'no_helmet' ni 'helmet' (indeterminado)
#   "sin_casco"     -> se detecto 'no_helmet' (infraccion confirmada)
#   "falta_chaleco" -> no se detecto 'no_vest' ni 'vest' (indeterminado)
#   "sin_chaleco"   -> se detecto 'no_vest' (infraccion confirmada)
#
# La diferencia con el modelo anterior es que la infraccion ya no se infiere
# por la ausencia de un casco: el detector la declara de forma positiva.
TIPOS_INFRACCION = {
    "falta_casco": "missing_helmet",
    "sin_casco": "missing_helmet",
    "falta_chaleco": "missing_reflective_vest",
    "sin_chaleco": "missing_reflective_vest",
}

# Estados que representan una infraccion confirmada por el detector.
ESTADOS_INFRACCION = {"sin_casco", "sin_chaleco"}

# Política ante un estado indeterminado ("falta_casco" / "falta_chaleco"): el
# detector vio a la persona pero no declaro nada sobre esa zona (cabeza oculta,
# cuerpo fuera de cuadro, distancia). Hay dos lecturas defendibles:
#
#   "infraccion" -> se alerta tambien. Es la politica conservadora: en un
#                    sitio de obra no avisar puede costar un accidente.
#   "cumple"     -> solo se alerta con infraccion confirmada. Reduce falsos
#                    positivos, a costa de no avisar en los casos indeterminados.
#
# El valor por defecto es "infraccion" (conservador). El protocolo de
# evaluacion de `Yolo/README.md` mide ambas para reportar el coste de cada una.
POLITICA_SIN_DATOS = "infraccion"


# ==================== UTILIDADES ====================
def solapamiento(caja, contenedor):
    """Fracción del área de 'caja' contenida en 'contenedor' (0.0 - 1.0)."""
    ax1, ay1, ax2, ay2 = caja
    bx1, by1, bx2, by2 = contenedor
    ix = max(0.0, min(ax2, bx2) - max(ax1, bx1))
    iy = max(0.0, min(ay2, by2) - max(ay1, by1))
    area = max(1.0, float(ax2 - ax1) * float(ay2 - ay1))
    return (ix * iy) / area


def mejor_de_par(candidatos):
    """Resuelve el conflicto helmet/no_helmet (o vest/no_vest) por confianza."""
    if not candidatos:
        return None
    return max(candidatos, key=lambda e: e["conf"])["nombre"]


def evaluar_persona(parte):
    """Devuelve el frozenset de estados de una persona.

    Cada elemento del EPP aporta una de dos señales por zona:

    - `helmet` / `vest`: la persona lleva el implemento -> estado conforme.
    - `no_helmet` / `no_vest`: el detector afirma que NO lo lleva -> infraccion
      confirmada ("sin_casco" / "sin_chaleco").

    Si no hay ninguna deteccion en esa zona, el estado queda indeterminado
    ("falta_casco" / "falta_chaleco"): el motor no puede afirmar la infraccion,
    y la API recibe el mismo tipo de incidente, pero el incidente solo se
    registra cuando el estado es una infraccion confirmada.

    Esto difiere del modelo de 11 clases, donde la infraccion se inferia de la
    ausencia de un casco: ahora la declara el detector de forma positiva.
    """
    pares = {"casco": [], "chaleco": []}
    for e in parte:
        if e["nombre"] in ("helmet", "no_helmet"):
            pares["casco"].append(e)
        elif e["nombre"] in ("vest", "no_vest"):
            pares["chaleco"].append(e)

    casco = mejor_de_par(pares["casco"])
    chaleco = mejor_de_par(pares["chaleco"])

    estados = []
    if casco is None:
        estados.append("falta_casco")
    elif casco == "no_helmet":
        estados.append("sin_casco")
    if chaleco is None:
        estados.append("falta_chaleco")
    elif chaleco == "no_vest":
        estados.append("sin_chaleco")
    return frozenset(estados)


def parece_cuerpo(persona, partes):
    """¿La caja 'Person' contiene a un cuerpo, o es solo el EPP cajado dos veces?

    El detector no tiene clases de cabeza ni de torso, así que un chaleco
    suelto en el piso o colgado de la pared puede salir cajado como 'Person'
    y con su propio 'vest' o 'no_vest' encima. Esa caja no describe a nadie,
    y abriría un incidente por cada chaleco abandonado de la obra.

    Se mide qué fracción de la PERSONA cubre el EPP, y no al revés. El orden
    importa y es fácil equivocarse: un chaleco siempre está entero dentro de
    su caja 'Person', así que medido del otro sentido daría ~1.0 también en
    una persona real y la regla descartaría a todo el mundo. En una persona
    de verdad el chaleco ocupa el torso, alrededor de un 40 %; en el fantasma
    ocupa la caja entera.
    """
    if not partes:
        # Sin EPP no hay con qué acusar a la caja de ser el propio EPP, y el
        # hecho de no detectar nada es en sí mismo noticia
        # (ver POLITICA_SIN_DATOS). El fantasma va siempre acompañado de su
        # EPP, así que este caso no lo deja pasar por accidente.
        return True
    return max(solapamiento(persona["caja"], e["caja"]) for e in partes) < UMBRAL_EPP_CUBRE_PERSONA


def confirmar_infracciones(estado):
    """Convierte los estados de una persona en infracciones a notificar.

    Aplica `POLITICA_SIN_DATOS` a los estados indeterminados:
    - "infraccion": "falta_casco"/"falta_chaleco" también se notifican.
    - "cumple":     solo se notifican las infracciones confirmadas.

    Devuelve un frozenset con los estados a notificar.
    """
    if POLITICA_SIN_DATOS == "cumple":
        return frozenset(e for e in estado if e in ESTADOS_INFRACCION)
    return estado


def banda_dentro(caja, cx, cy, ancho, alto):
    """Rectángulo de tamaño dado, centrado en (cx, cy) y contenido en 'caja'."""
    x1, y1, x2, y2 = caja
    ancho = min(ancho, x2 - x1)
    alto = min(alto, y2 - y1)
    ix = min(max(cx - ancho / 2.0, x1), x2 - ancho)
    iy = min(max(cy - alto / 2.0, y1), y2 - alto)
    return (int(ix), int(iy), int(ancho), int(alto))


def cargar_yunet(ruta: Path, umbral: float = YUNET_UMBRAL):
    """Carga YuNet, descargándolo si no está en el repositorio."""
    if not ruta.is_file():
        ruta.parent.mkdir(parents=True, exist_ok=True)
        print(f"Descargando {ruta.name} desde el repositorio de OpenCV...")
        urllib.request.urlretrieve(URL_YUNET, str(ruta))
    return cv2.FaceDetectorYN.create(str(ruta), "", (320, 240), umbral, YUNET_NMS, 5000)


# CLAHE se crea una sola vez: el detector se ejecuta por frame y por persona.
_CLAHE = cv2.createCLAHE(clipLimit=2.5, tileGridSize=(8, 8))


def normalizar_iluminacion(imagen):
    """Iguala la iluminación con CLAHE antes de buscar el rostro.

    Es la defensa contra las sombras: YuNet encuentra bien el rostro con luz
    pareja, pero con una sombra dura sobre la cara deja de detectarlo o devuelve
    landmarks desplazados. Igualar el canal de luz en el espacio LAB recupera el
    contraste local sin arruinar el color, y devuelve una imagen nueva para no
    tocar el frame que se guarda como evidencia.
    """
    lab = cv2.cvtColor(imagen, cv2.COLOR_BGR2LAB)
    luz, a, b = cv2.split(lab)
    return cv2.cvtColor(cv2.merge((_CLAHE.apply(luz), a, b)), cv2.COLOR_LAB2BGR)


def detectar_rostros(detector, imagen):
    """[(caja_cara, ojos), ...] donde 'caja_cara' es (x1, y1, x2, y2).

    YuNet devuelve cada rostro como (x, y, w, h) mas los landmarks. Se
    convierte a (x1, y1, x2, y2) porque el resto del motor trabaja con
    esquinas: mixing los dos formatos hace que la zona difuminada salga con
    ancho negativo y el rostro no se difumine.

    Se le entrega la imagen con la iluminación igualada, no el frame original:
    es lo que permite encontrar el rostro cuando hay sombra sobre la cara.
    """
    alto, ancho = imagen.shape[:2]
    if detector.getInputSize() != (ancho, alto):
        detector.setInputSize((ancho, alto))
    _, caras = detector.detect(normalizar_iluminacion(imagen))
    if caras is None:
        return []
    salida = []
    for c in caras:
        x, y, w, h = float(c[0]), float(c[1]), float(c[2]), float(c[3])
        caja = (x, y, x + w, y + h)
        # indices 4-7: ojo derecho (x,y) e izquierdo (x,y)
        ojos = (float(c[4]), float(c[5]), float(c[6]), float(c[7]))
        salida.append((caja, ojos))
    return salida


# ==================== DIFUMINADO DE ROSTROS ====================
# Funciones de modulo para que los scripts de monitoreo que no usan el motor
# (monitoreo_v1) puedan difuminar sin duplicar la logica.

def dimensiones(cara):
    """(x1, y1, ancho, alto) de una caja dada como esquinas (x1, y1, x2, y2).

    El resto del motor pasa las cajas como esquinas, pero las medidas relativas
    (ancho de la zona, separación de ojos) se expresan sobre el ancho y el alto
    reales. Mezclar los dos formatos hace que la zona salga oversized y que la
    validación de los landmarks use una escala equivocada.
    """
    x1, y1, x2, y2 = cara
    return x1, y1, max(0.0, x2 - x1), max(0.0, y2 - y1)


def ojos_plausibles(cara, ojos) -> bool:
    """True si los ojos de YuNet son coherentes con la geometría de la cara.

    Con sombras duras YuNet devuelve puntos creíbles pero desplazados: el ojo
    cae en la sien o en la mejilla, y la zona sale fuera, dejando el rostro
    identificable. Se valida la separación entre ojos, el desnivel entre ellos
    y que ambos caigan dentro de la cara.
    """
    fx, fy, fw, fh = dimensiones(cara)
    if fw <= 0 or fh <= 0:
        return False
    (rx, ry), (lx, ly) = (ojos[0], ojos[1]), (ojos[2], ojos[3])
    if not (OJO_SEP_MIN * fw <= math.hypot(lx - rx, ly - ry) <= OJO_SEP_MAX * fw):
        return False
    if abs(ly - ry) > OJO_DESVIO_MAX_Y * fh:
        return False
    return all(
        fx + OJO_X_MIN * fw <= x <= fx + OJO_X_MAX * fw
        and fy <= y <= fy + OJO_Y_MAX * fh
        for x, y in ((rx, ry), (lx, ly))
    )


def zona_ojos_nariz(cara, ojos=None):
    """Única zona difuminada de un rostro: los dos ojos y la nariz juntos.

    Un solo rectángulo, de un tirón. La envolvente anatómica fija siempre el
    suelo de la zona (cejillas y punta de la nariz); si los landmarks de YuNet
    son coherentes, su línea de ojos ensancha esa envolvente hacia arriba y
    hacia abajo y su separación ensancha el ancho. Nunca la estrechan: si
    salieran mal (sombra, perfil, gafas) se ignoran y manda la anatomía.
    El anonimato no admite fallos ni huecos en medio.
    """
    fx, fy, fw, fh = dimensiones(cara)
    arriba = fy + fh * ZONA_ARIBA
    abajo = fy + fh * ZONA_ABAJO
    ancho = fw * ZONA_REL_ANCHO
    cx = fx + fw * ZONA_REL_CENTRO_X
    if ojos is not None and ojos_plausibles(cara, ojos):
        cx = (ojos[0] + ojos[2]) / 2.0
        linea = (ojos[1] + ojos[3]) / 2.0
        separacion = math.hypot(ojos[2] - ojos[0], ojos[3] - ojos[1])
        arriba = min(arriba, linea - fh * ZONA_OJO_MARGEN)
        abajo = max(abajo, linea + fh * ZONA_OJO_BAJA)
        ancho = max(ancho, separacion * ZONA_SEP_REL)
    return banda_dentro(cara, cx, (arriba + abajo) / 2.0,
                        ancho, abajo - arriba)


def difuminar_zona(roi, zona) -> int:
    """Desenfoque gaussiano sobre una única zona, recortada al ROI.

    Devuelve 1 si llegó a difuminarse y 0 si la zona caía vacía o fuera del
    recorte: si se dibujara fuera de la imagen, en vez de anonimizar se
    estaria tocando otro trozo del frame.
    """
    bx, by, bw, bh = (int(v) for v in zona)
    if bx < 0 or by < 0 or bw <= 0 or bh <= 0:
        return 0
    region = roi[by:by + bh, bx:bx + bw]
    if region.size == 0:
        return 0
    k = int(min(max(bw, bh) * 2, 99)) | 1
    roi[by:by + bh, bx:bx + bw] = cv2.GaussianBlur(region, (k, k), 0)
    return 1


def difumar_roi(detector, roi) -> int:
    """Difumina la zona de ojos y nariz de cada rostro dentro del ROI.

    Una sola zona continua por rostro, no una banda por ojo: lo que deja
    identificable a la persona es el conjunto ojos-nariz pegado, y un hueco
    entre bandas lo deja a medio tapar. Devuelve el numero de rostros
    difuminados.
    """
    if roi.size == 0:
        return 0
    n = 0
    for cara, ojos in detectar_rostros(detector, roi):
        # La caja viene como esquinas; el filtro de tamaño va sobre el ancho y
        # el alto reales, no sobre x2 e y2.
        _, _, fw, fh = dimensiones(cara)
        if fw < 8 or fh < 8:
            continue
        difuminar_zona(roi, zona_ojos_nariz(cara, ojos))
        n += 1
    return n


def difuminar_cabeza(roi, cabezas, origen) -> int:
    """Zona de ojos y nariz sobre la caja de cabeza, cuando YuNet no detecta.

    'cabezas' trae las cajas de cabeza en coordenadas de la imagen completa,
    pero 'roi' es un recorte de la persona. Hay que trasladar la caja al
    sistema de coordenadas de la ROI, si no la zona cae fuera.
    """
    if not cabezas:
        return 0
    mejor = max(cabezas, key=lambda c: c["caja"][2] * c["caja"][3])
    hx1, hy1, hx2, hy2 = mejor["caja"]
    ox, oy = origen
    cx1, cy1 = hx1 - ox, hy1 - oy
    cx2, cy2 = hx2 - ox, hy2 - oy
    alto_roi, ancho_roi = roi.shape[:2]
    if cx2 <= cx1 or cy2 <= cy1:
        return 0
    cx1, cy1 = max(0.0, cx1), max(0.0, cy1)
    cx2, cy2 = min(float(ancho_roi), cx2), min(float(alto_roi), cy2)
    if cx2 <= cx1 or cy2 <= cy1:
        return 0
    ancho_cabeza, alto_cabeza = cx2 - cx1, cy2 - cy1
    # La caja de cabeza puede llevar el casco puesto: la cara empieza por
    # debajo del borde, así que la zona se ancla en la mitad de la caja y
    # baja hasta la nariz.
    caja = (0.0, 0.0, ancho_cabeza, alto_cabeza)
    bx, by, bw, bh = banda_dentro(
        caja, ancho_cabeza * ZONA_REL_CENTRO_X,
        alto_cabeza * CABEZA_ZONA_REL_Y,
        ancho_cabeza * CABEZA_ZONA_REL_ANCHO,
        alto_cabeza * CABEZA_ZONA_REL_ALTO)
    return difuminar_zona(roi, (bx + cx1, by + cy1, bw, bh))


def difuminar_cabeza_persona(roi) -> int:
    """Zona de ojos y nariz estimada desde la caja de la persona.

    Es el último respaldo: si YuNet no ve el rostro y tampoco hay caja de
    cabeza (persona de espaldas, capucha, sombra profunda), la cabeza ocupa la
    parte alta del cuerpo y la cara cae cerca del borde superior. Mejor una
    zona aproximada que dejar el rostro sin anonimizar.
    """
    alto_roi, ancho_roi = roi.shape[:2]
    if alto_roi <= 0 or ancho_roi <= 0:
        return 0
    zona = banda_dentro(
        (0, 0, ancho_roi, alto_roi),
        ancho_roi * ZONA_REL_CENTRO_X, alto_roi * PERSONA_ZONA_REL_Y,
        ancho_roi * PERSONA_ZONA_REL_ANCHO, alto_roi * PERSONA_ZONA_REL_ALTO)
    return difuminar_zona(roi, zona)


def difumar_rostros(detector, frame, persona, cabezas) -> int:
    """Anonimiza el rostro de una persona. YuNet cubre frontal y perfil.

    Devuelve el numero de rostros difuminados.
    """
    x1, y1, x2, y2 = persona
    alto_f, ancho_f = frame.shape[:2]
    x1, y1 = max(0, x1), max(0, y1)
    x2, y2 = min(ancho_f, x2), min(alto_f, y2)
    if x2 <= x1 or y2 <= y1:
        return 0
    # La caja de 'Person' a veces empieza en los hombros y deja la cara fuera:
    # el rostro y la caja de cabeza se buscan también en un margen sobre ella.
    ya = max(0, y1 - (y2 - y1) // 3)
    ampliado = frame[ya:y2, x1:x2]
    n = difumar_roi(detector, ampliado)
    if n:
        return n
    # Sin rostro detectado: la caja de cabeza que vio YOLO, y si tampoco hay,
    # la proporción de la cabeza sobre la caja de la persona.
    n = difuminar_cabeza(ampliado, cabezas, (x1, ya))
    if n:
        return n
    return difuminar_cabeza_persona(frame[y1:y2, x1:x2])


def clave_violacion(estado):
    """Clave semántica de un estado: falta_casco y sin_casco son la misma falta.

    Sin esto, el parpadeo de la detección hace que una persona genere un
    incidente nuevo cada vez que alterna entre 'falta_chaleco' y 'sin_chaleco'.
    """
    return tuple(sorted({TIPOS_INFRACCION[i] for i in estado if i in TIPOS_INFRACCION}))


def centro_caja(caja):
    """Centro de una caja dada como esquinas, o None si no hay caja.

    Compartido con `monitoreo_v1.py`, que hace el mismo seguimiento de la
    persona entre frames.
    """
    if caja is None:
        return None
    x1, y1, x2, y2 = caja
    return (x1 + x2) / 2.0, (y1 + y2) / 2.0


def alcance_reaparicion(caja):
    """Distancia maxima a la que se admite que reaparezca la misma persona.

    Se mide en cajas de la propia persona: un par de cuerpos es margen
    suficiente para que la deteccion se corte mientras la persona sigue en el
    sitio, y poco como para enganchar a alguien que entra por otro lado del
    encuadre. Con caja desconocida no se restringe.
    """
    if caja is None:
        return float("inf")
    _, _, ancho, alto = dimensiones(caja)
    return max(ancho, alto, 1.0) * GRACIA_CIERRE_CAJAS


def texto(frame, cadena, org, escala, color, grosor=2):
    """Texto con contorno para que se lea sobre cualquier fondo."""
    cv2.putText(frame, cadena, org, FONT, escala, COLOR_CONTORNO, grosor + 2, cv2.LINE_AA)
    cv2.putText(frame, cadena, org, FONT, escala, color, grosor, cv2.LINE_AA)


# ==================== MOTOR ====================
class MonitorEPP:
    """Detecta infracciones de EPP, difumina rostros y registra incidentes."""

    def __init__(self, ruta_modelo=None, ruta_yunet=None, carpeta_evidencia="incidents",
                 al_registrar=None, ping_segundos=PING_SEGUNDOS,
                 camera_id=CAMARA_POR_DEFECTO, zonas=None):
        ruta_modelo = ruta_modelo or RUTA_MODELO_EPP
        if not Path(ruta_modelo).is_file():
            raise IOError(f"No se encontró el modelo YOLO: {ruta_modelo}")
        self.model = YOLO(str(ruta_modelo))
        self.detector = cargar_yunet(ruta_yunet or RUTA_YUNET)
        self.carpeta_evidencia = Path(carpeta_evidencia)
        self.al_registrar = al_registrar
        # Intervalo del ping de mantenimiento. 0 lo desactiva.
        self.ping_segundos = max(0, int(ping_segundos))
        # Cómo se reporta esta cámara a la API, y las zonas de riesgo que
        # vigila: `None` significa que se vigila todo el encuadre, que es el
        # comportamiento de siempre. Cada episodio queda anclado a la zona en
        # la que nació, que es lo que se reporta como `zone_id`.
        self.camera_id = camera_id
        self.zonas = zonas
        self.historial: dict[int, deque] = {}
        self.ultimo_estado: dict[int, frozenset] = {}
        self.estado_confirmado: dict[int, frozenset] = {}
        self.violacion_confirmada: dict[int, tuple] = {}
        self.ultimo_visto: dict[int, int] = {}
        # Ultima caja vista de cada persona: sirve para reconocer que la misma
        # persona reaparece tras un parpadeo del detector.
        self.caja_vista: dict[int, tuple] = {}
        # Episodio en curso por persona: inicio, ultimo ping, la zona donde
        # nació y el incidente ya registrado que se reenvia en cada ping.
        self.episodio: dict[int, dict] = {}
        # Episodios en espera de reaparicion: la persona se perdio de vista
        # (el detector de 'Person' parpadeo) pero no por eso se cierra el
        # registro. Se retoman si vuelve, o se cierran al vencer la gracia.
        self.en_espera: list[dict] = []
        self.n_frames = 0
        self.t_prev = time.time()
        self.fps = 0.0

    # ---------- detección ----------
    def _detectar(self, frame):
        # El checkpoint arrastra 'tracker: tracktrack.yaml' en sus args, y ese
        # tracker devuelve boxes.id nulo en Ultralytics 8.4. Se fija ByteTrack
        # de forma explicita porque sin IDs no hay seguimiento ni suavizado.
        results = self.model.track(frame, persist=True, conf=CONF_MIN,
                                   tracker=TRACKER, verbose=False)
        boxes = results[0].boxes
        hay_seguimiento = boxes.id is not None
        ids = boxes.id.int().tolist() if hay_seguimiento else list(range(len(boxes)))

        personas, epps = [], []
        for i, box in enumerate(boxes):
            nombre = self.model.names[int(box.cls[0])]
            if nombre not in CLASES_PERMITIDAS:
                continue
            conf = float(box.conf[0])
            if conf < CONF_MIN_POR_CLASE.get(nombre, CONF_MIN):
                continue
            item = {
                "nombre": nombre,
                "caja": tuple(map(int, box.xyxy[0])),
                "conf": conf,
                "id": ids[i],
            }
            (personas if nombre == CLASE_PERSONA else epps).append(item)
        return personas, epps, hay_seguimiento

    @staticmethod
    def _partes_de(epps, persona):
        """EPP asociados a la persona.

        Con el detector de 5 clases no hace falta reinterpretar nada: cada
        clase negativa ya declara su zona (cabeza o torso).
        """
        partes = []
        for e in epps:
            if solapamiento(e["caja"], persona["caja"]) < SOLAPAMIENTO_MIN:
                continue
            partes.append(e)
        return partes

    def _registrar_cambio(self, pid, estado, confianza, nuevos, caja=None, zona=None):
        """Gestiona el ciclo de vida del aviso de una persona.

        Decide que hacer con el estado confirmado de la persona, aplicando la
        politica vigente (`confirmar_infracciones`):

        - Sin infraccion notificable: si habia un episodio en curso, se cierra
          (FIN) para que conste cuando termino.
        - Con infraccion y sin episodio: se abre (INICIO) y se notifica de
          inmediato, sin esperar el ping de nadie.
        - Con infraccion y episodio en curso: si vencio el intervalo de ping,
          se reenvia el aviso ya registrado (PING) para confirmar que la
          situacion persiste.

        'caja' es la caja de la persona en el frame actual: permite reconocer
        que es la misma persona que se perdio de vista y retomar su episodio.
        'zona' es el id de la zona de riesgo en la que esta parado, o None si
        no hay zonas configuradas: con el que nace el episodio es el que se
        reporta como zone_id.

        Devuelve el tipo de evento generado: "inicio", "ping", "fin" o None.
        """
        notificables = confirmar_infracciones(estado)
        clave = clave_violacion(notificables)
        ahora = time.monotonic()

        if not clave:
            # Cumplimiento (o estado que la politica no notifica): el episodio
            # en curso se cierra despues, en _registrar, para conservar el
            # incidente ya registrado y poder reenviarlo.
            self.violacion_confirmada[pid] = clave
            self.estado_confirmado[pid] = estado
            if pid in self.episodio:
                nuevos[pid] = (notificables, confianza, "fin")
                return "fin"
            return None

        desconocida = self.violacion_confirmada.get(pid) is None
        if self.violacion_confirmada.get(pid) != clave:
            # Cambio semantico de la infraccion, o primera vez que se ve a
            # esta persona. El episodio anterior, si lo hay, se retira aqui.
            self.episodio.pop(pid, None)
            self.violacion_confirmada[pid] = clave
            self.estado_confirmado[pid] = estado
            if desconocida and self._retomar_episodio(pid, clave, caja, zona):
                # No es nadie nuevo: es a quien el detector dejo de ver y que
                # ahora vuelve, a veces con otro id de ByteTrack. Sigue siendo
                # el mismo registro, asi que no se abre un INICIO; pasa
                # directamente al control del ping.
                return self._controlar_ping(pid, nuevos, confianza, ahora)
            self.episodio[pid] = {"inicio": ahora, "ultimo_ping": ahora,
                                  "incidente": None, "zona": zona}
            nuevos[pid] = (notificables, confianza, "inicio")
            return "inicio"

        # Misma infraccion sostenida: toca ping si ya vencio el intervalo.
        self.estado_confirmado[pid] = estado
        episodio = self.episodio.get(pid)
        if episodio is None:
            # Se confirmo la infraccion sin haber pasado por un inicio (por
            # ejemplo, tras descartar a la persona por quedar fuera de cuadro).
            self.episodio[pid] = {"inicio": ahora, "ultimo_ping": ahora,
                                  "incidente": None, "zona": zona}
            nuevos[pid] = (notificables, confianza, "inicio")
            return "inicio"

        return self._controlar_ping(pid, nuevos, confianza, ahora)

    def _retomar_episodio(self, pid, clave, caja=None, zona=None):
        """Retoma un episodio en espera que tenga la misma infraccion y zona.

        Cuando la deteccion de 'Person' parpadea (gafas, sombra, perfil), la
        persona se pierde de vista y ByteTrack le asigna otro id al volver.
        Sin esto, cada parpadeo cerraria el registro con un FIN y abria otro
        con el mismo contenido: una persona que nunca salio de la camara
        quedaria partida en varias infracciones seguidas.

        Solo se retoma si ademas reaparece mas o menos donde se fue, para que
        una persona distinta que entra por otro lado del encuadre no se
        apropie del episodio de la anterior. Devuelve True si lo retomo.
        """
        if not clave:
            return False
        centro = centro_caja(caja)
        for i in range(len(self.en_espera) - 1, -1, -1):
            item = self.en_espera[i]
            if item["clave"] != clave:
                continue
            if item.get("zona") != zona:
                # El episodio quedo anclado a otra zona: retomarlo aqui
                # reportaria un incidente bajo un zone_id que ya no le toca.
                continue
            if centro is not None and item["centro"] is not None:
                if math.hypot(centro[0] - item["centro"][0],
                              centro[1] - item["centro"][1]) > item["radio"]:
                    continue
            self.en_espera.pop(i)
            self.episodio[pid] = item["episodio"]
            return True
        return False

    def _controlar_ping(self, pid, nuevos, confianza, ahora):
        """Emite el ping si ya vencio el intervalo; si no, no notifica nada."""
        episodio = self.episodio.get(pid)
        if episodio is None or self.ping_segundos <= 0:
            return None
        if ahora - episodio["ultimo_ping"] < self.ping_segundos:
            return None

        episodio["ultimo_ping"] = ahora
        notificables = confirmar_infracciones(self.estado_confirmado.get(pid, frozenset()))
        nuevos[pid] = (notificables, confianza, "ping")
        return "ping"

    def _cerrar_episodio(self, episodio):
        """Cierra un episodio ya retirado del mapa y devuelve el cierre.

        Tanto el episodio en curso como uno que aguarda en espera se cierran
        igual: se reenvia el incidente ya registrado con el evento 'fin'.
        Devuelve None si nunca llego a registrarse el inicio.
        """
        if episodio is None or episodio.get("incidente") is None:
            return None
        incidente = dict(episodio["incidente"])
        incidente["event"] = "fin"
        if self.al_registrar:
            self.al_registrar(incidente)
        return incidente

    # ---------- difuminado ----------
    @staticmethod
    def _difumar_roi(detector, roi):
        """Difumina la zona de ojos y nariz de cada rostro dentro del ROI.

        Devuelve el número de rostros difuminados.
        """
        return difumar_roi(detector, roi)

    def difumar_rostros(self, frame, persona, cabezas):
        """Anonimiza el rostro de una persona. YuNet cubre frontal y perfil."""
        return difumar_rostros(self.detector, frame, persona, cabezas)

    @staticmethod
    def _difuminar_cabeza(roi, cabezas, origen):
        """Banda de ojos sobre la caja de cabeza, cuando YuNet no detecta."""
        return difuminar_cabeza(roi, cabezas, origen)

    # ---------- evidencia ----------
    def guardar_evidencia(self, frame):
        """Guarda el frame ya difuminado en incidents/AAAA/MM/DD/.

        Devuelve la ruta relativa a la carpeta padre de la evidencia
        (``incidents/AAAA/MM/DD/archivo.jpg``): la API rechaza rutas absolutas.
        """
        ahora = datetime.now(timezone.utc)
        relativa = Path(self.carpeta_evidencia.name) / ahora.strftime("%Y/%m/%d")
        carpeta = self.carpeta_evidencia.parent / relativa
        carpeta.mkdir(parents=True, exist_ok=True)
        nombre = f"incidente-{ahora.strftime('%H%M%S-%f')}.jpg"
        cv2.imwrite(str(carpeta / nombre), frame)
        return (relativa / nombre).as_posix(), ahora

    def _registrar(self, frame, pid, estado, confianza, evento="inicio"):
        """Crea el incidente y lo entrega al callback si hay uno.

        Para el evento "inicio" se guarda la evidencia del frame y se crea un
        incidente nuevo. Para "ping" y "fin" se reenvia el incidente ya
        registrado, con los mismos datos: el ping confirma que la situacion
        persiste y el fin cierra el registro, pero ninguno de los dos crea un
        registro nuevo.
        """
        tipos = sorted({TIPOS_INFRACCION[i] for i in estado if i in TIPOS_INFRACCION})
        episodio = self.episodio.get(pid)

        if evento == "inicio":
            evidencia, momento = self.guardar_evidencia(frame)
            if not tipos:
                raise ValueError("No se puede registrar un incidente sin infraccion")
            incidente = {
                "camera_id": self.camera_id,
                # La zona en la que nacio el episodio; sin zonas configuradas
                # queda la de siempre, para no romper el contrato de la API.
                "zone_id": (episodio.get("zona") if episodio else None) or ZONA_POR_DEFECTO,
                "detected_at": momento.isoformat().replace("+00:00", "Z"),
                "violation_type": tipos[0],
                "violation_types": tipos,
                "confidence": round(min(1.0, max(0.0, confianza)), 4),
                "evidence_path": evidencia,
                "person_track_id": int(pid),
                "beacon_alert": {"status": "skipped_offline", "latency_ms": None},
                "event": "inicio",
                # Identifica al registro para que la API pueda actualizarlo con
                # cada ping en vez de crear un incidente nuevo.
                "episode_id": str(uuid.uuid4()),
                "occurred_at": momento.isoformat().replace("+00:00", "Z"),
                "ping_count": 0,
            }
            if episodio is not None:
                episodio["incidente"] = incidente
                episodio["inicio"] = time.monotonic()
            if self.al_registrar:
                self.al_registrar(incidente)
            return incidente

        # Ping o fin: se reenvia el incidente ya registrado, con los datos
        # originales, para mantener el aviso vivo sin duplicar registros.
        if episodio is None or episodio.get("incidente") is None:
            return None
        incidente = dict(episodio["incidente"])
        incidente["event"] = evento
        # Marca de cuando ocurrio este ping o este cierre; el episode_id
        # permite que la API actualice el mismo registro en vez de crear otro.
        incidente["occurred_at"] = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        if evento == "ping":
            episodio["pings"] = episodio.get("pings", 0) + 1
        incidente["ping_count"] = episodio.get("pings", 0)
        if self.al_registrar:
            self.al_registrar(incidente)
        if evento == "fin":
            # El registro se cierra: ya no hay episodio en curso para esta persona.
            self.episodio.pop(pid, None)
        return incidente

    def _depurar_invisibles(self):
        """Aparta los episodios de quienes ya no se ven, y cierra los vencidos.

        Devuelve los cierres (FIN) generados en este frame.

        El detector de 'Person' parpadea: gafas, sombra o un perfil raro hacen
        que desaparezca del frame aunque la persona no se haya movido, y al
        volver ByteTrack le reparte otro id. Si se cerrara el episodio en ese
        hueco, alguien que nunca salio de la camara acabaria partida en varias
        infracciones seguidas (FIN y, segundos despues, un INICIO con otro
        numero). En vez de cerrar, el episodio pasa a espera: se retoma si la
        persona reaparece con la misma falta y cerca de donde se fue, y solo
        se cierra de verdad cuando la espera supera GRACIA_CIERRE_SEGUNDOS.
        """
        cierres = []
        instante = time.monotonic()

        for pid in [p for p, v in self.ultimo_visto.items()
                    if self.n_frames - v > FRAME_PARA_DESCARTAR]:
            self.ultimo_visto.pop(pid, None)
            self.historial.pop(pid, None)
            self.ultimo_estado.pop(pid, None)
            self.estado_confirmado.pop(pid, None)
            clave = self.violacion_confirmada.pop(pid, None)
            caja = self.caja_vista.pop(pid, None)
            episodio = self.episodio.pop(pid, None)
            if episodio is not None and episodio.get("incidente") is not None:
                self._guardar_en_espera(pid, clave, caja, episodio, instante)

        # Ya no puede afirmarse que sigan sin EPP: se cierran.
        vencidos = [e for e in self.en_espera
                    if instante - e["perdido"] > GRACIA_CIERRE_SEGUNDOS]
        if vencidos:
            self.en_espera = [e for e in self.en_espera if e not in vencidos]
            for item in vencidos:
                cierre = self._cerrar_episodio(item["episodio"])
                if cierre is not None:
                    cierres.append(cierre)
                    self._consola(item["pid"], (), "fin")

        return cierres

    def _guardar_en_espera(self, pid, clave, caja, episodio, instante):
        """Aparta un episodio en curso sin cerrarlo.

        Comparten este camino dos motivos que significan lo mismo: dejar de ver
        a la persona, y verla fuera de su zona de riesgo. En los dos el
        episodio se guarda con la zona en la que nació, y se retoma si vuelve
        a tiempo o se cierra con FIN cuando vence la gracia.
        """
        self.en_espera.append({"pid": pid,
                               "clave": clave,
                               "zona": episodio.get("zona"),
                               "centro": centro_caja(caja),
                               "radio": alcance_reaparicion(caja),
                               "episodio": episodio,
                               "perdido": instante})

    def _apartar_por_zona(self, pid, caja):
        """Guarda el episodio de alguien que acaba de dejar su zona de riesgo.

        No se cierra en el acto: alguien que cruza el borde y vuelve no debe
        arrastrar un FIN y un INICIO. Pasa a espera con la misma gracia que la
        pérdida de detección, y si la persona regresa a esa misma zona con la
        misma falta y cerca, se retoma con el mismo episode_id.

        Se deshace tambien de la confirmación de la infracción: si no, al
        volver se la tomaría por una infracción sostenida y no por alguien
        que se fue y volvió, que es lo que es.
        """
        clave = self.violacion_confirmada.pop(pid, None)
        self.estado_confirmado.pop(pid, None)
        episodio = self.episodio.pop(pid, None)
        if episodio is None or episodio.get("incidente") is None:
            # Sin registro ya enviado no hay nada que retener: abrir otro
            # incidente al volver seria duplicar.
            return
        self._guardar_en_espera(pid, clave, caja, episodio, time.monotonic())

    # ---------- ciclo principal ----------
    def procesar(self, frame):
        """Analiza un frame. Devuelve la lista de incidentes nuevos."""
        self.n_frames += 1
        personas, epps, hay_seguimiento = self._detectar(frame)

        # El EPP se asocia a cada persona una sola vez, y lo consumen tanto la
        # regla anti-fantasma como la evaluación de la infracción.
        partes_por_pid = {p["id"]: self._partes_de(epps, p) for p in personas}
        # Cajas que no parecen cuerpos: un chaleco cajado como 'Person'. Se
        # siguen difuminando, pero no se vigilan ni se les abren registros,
        # porque no hay nadie detrás.
        vigiladas = [p for p in personas
                     if parece_cuerpo(p, partes_por_pid[p["id"]])]

        # Se ejecuta antes de mirar a las personas del frame: los episodios de
        # quienes dejaron de verse se apartan (o se cierran si se agoto la
        # gracia) en el mismo frame en que se pierden de vista.
        incidentes = self._depurar_invisibles()

        nuevos = {}
        ancho = alto = 0
        if self.zonas is not None:
            # Las zonas se dibujan en relativo (0..1) y las cajas vienen en
            # píxeles: hace falta el tamaño del frame para pasar de una a otra.
            alto, ancho = frame.shape[:2]

        for p in vigiladas:
            pid = p["id"]
            self.ultimo_visto[pid] = self.n_frames
            self.caja_vista[pid] = p["caja"]
            partes = partes_por_pid[pid]
            estado = evaluar_persona(partes)
            # Si no hay EPP detectado, la confianza de la persona es la unica
            # señal disponible; con 0 el incidente no significaria nada.
            confianza = max((e["conf"] for e in partes), default=p["conf"])

            zona = None
            if self.zonas is not None:
                # El difuminado, en cambio, no depende de la zona: se aplica a
                # todo el frame más abajo, sea quien sea y donde esté.
                zona = zona_de(p["caja"], self.zonas, ancho, alto)
                if zona is None:
                    # Fuera de toda zona vigilada: ni estado ni aviso. Si tenía
                    # el registro abierto, pasa a espera con su gracia.
                    if pid in self.episodio:
                        self._apartar_por_zona(pid, p["caja"])
                    continue
                episodio = self.episodio.get(pid)
                if episodio is not None and episodio.get("zona") != zona:
                    # Cruzó a otra zona: el episodio que traía sigue anclado al
                    # suyo y queda en espera, y aquí se abre el de la nueva.
                    self._apartar_por_zona(pid, p["caja"])

            if hay_seguimiento:
                ventana = self.historial.setdefault(pid, deque(maxlen=VENTANA_SUAVIZADO))
                ventana.append(estado)
                if sum(1 for s in ventana if s == estado) >= MIN_FRAMES_PARA_ALERTAR:
                    self._registrar_cambio(pid, estado, confianza, nuevos,
                                           p["caja"], zona)
                self.ultimo_estado[pid] = estado
            else:
                # Sin IDs no hay identidad estable entre frames, pero el estado
                # se sigue notificando una sola vez por cambio.
                self._registrar_cambio(pid, estado, confianza, nuevos, p["caja"], zona)

        # El difuminado va antes de dibujar, para que la evidencia salga limpia.
        # Va sobre las cajas SIN FILTRAR: la regla anti-fantasma decide a quién
        # se vigila, no a quién se difumina. El anonimato no admite excepciones
        # ni descartes.
        for p in personas:
            cabezas = [e for e in epps if e["nombre"] in CLASES_CABEZA]
            self.difumar_rostros(frame, p["caja"], cabezas)
        if not vigiladas and epps:
            # No hay nadie creíble a quien difuminar: o YOLO no acertó la clase
            # 'Person' (gafas, sombra, perfil) y la persona sigue en el encuadre,
            # o todo lo que se ve es un EPP suelto. Sin una caja de persona
            # donde recortar, se difumina el frame entero.
            difumar_roi(self.detector, frame)

        # Solo se enmarca y se etiqueta a quien se vigila: la caja de un
        # chaleco cajado como persona no debe salir con etiqueta de alerta.
        for p in vigiladas:
            pid = p["id"]
            x1, y1, x2, y2 = p["caja"]
            cv2.rectangle(frame, (x1, y1), (x2, y2), COLORES["Person"], 1)
            texto(frame, f"ID {pid}", (x1, max(15, y1 - 8)), 0.5, COLORES["Person"])
            visible = nuevos.get(pid, (frozenset(), 0.0))[0]
            if "sin_casco" in visible or "falta_casco" in visible:
                etiqueta = ("ALERTA: SIN CASCO" if "sin_casco" in visible
                            else "ALERTA: FALTA CASCO")
                texto(frame, etiqueta, (x1 + 5, y1 + 30), 0.7, (0, 255, 255))
            if "sin_chaleco" in visible or "falta_chaleco" in visible:
                etiqueta = ("ALERTA: SIN CHALECO" if "sin_chaleco" in visible
                            else "ALERTA: FALTA CHALECO")
                texto(frame, etiqueta, (x1 + 5, y1 + 60), 0.7, (255, 0, 255))

        for e in epps:
            color = COLORES.get(e["nombre"], (255, 255, 255))
            x1, y1, x2, y2 = e["caja"]
            cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
            texto(frame, f"{e['nombre']} {e['conf']:.2f}", (x1, max(15, y1 - 5)), 0.5, color)

        ahora = time.time()
        self.fps = 1.0 / max(ahora - self.t_prev, 1e-6)
        self.t_prev = ahora
        texto(frame, f"Personas: {len(vigiladas)} | FPS: {self.fps:.1f}",
              (10, 25), 0.6, COLOR_TEXTO)

        # La evidencia se genera con las marcas ya dibujadas.
        # Solo se notifica lo que la politica vigente marque como infraccion.
        for pid, (estado, confianza, evento) in nuevos.items():
            notificables = confirmar_infracciones(estado)
            if notificables or evento == "fin":
                incidente = self._registrar(frame, pid, notificables,
                                            confianza, evento)
                if incidente is not None:
                    incidentes.append(incidente)
                self._consola(pid, notificables, evento)

        return incidentes

    @staticmethod
    def _consola(pid, estado, evento="inicio"):
        """Escribe en consola el momento del ciclo de vida del aviso.

        INICIO y PING avisan sin EPP, FIN cierra el registro; el ping repite
        los datos ya registrados para que conste que la situacion no cambio.
        """
        hora = datetime.now().strftime("%H:%M:%S")
        if evento == "fin":
            print(f"[{hora}] Persona {pid}: FIN del registro (ya no esta sin EPP)")
            return
        if not estado:
            return
        marcador = "INFRACCIONES" if evento == "inicio" else "SIGUE SIN CAMBIOS"
        print(f"[{hora}] Persona {pid}: {marcador} -> {', '.join(sorted(estado))}")
