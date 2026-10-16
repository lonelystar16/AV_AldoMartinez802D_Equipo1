"""Motor de análisis de EPP de CascoVision.

Reune la lógica de detección de casco y chaleco, el difuminado de rostros y el
registro de incidentes. `monitoreo_v2.py` lo ejecuta contra la cámara local y
`monitoreo_api.py` lo reutiliza para reportar los incidentes a la API REST.

Los umbrales de zona no son estimaciones: salen de medir las 1426 imágenes
etiquetadas del dataset (train + val + test).
"""

import time
import urllib.request
from collections import deque
from datetime import datetime, timezone
from pathlib import Path

import cv2
from ultralytics import YOLO

# ==================== CONFIGURACIÓN ====================


def buscar_raiz_proyecto(inicio: Path) -> Path:
    """Sube desde el script hasta encontrar la carpeta que contiene 'Fase 2'."""
    for carpeta in (inicio, *inicio.parents):
        if (carpeta / "Fase 2").is_dir():
            return carpeta
    return inicio.parents[3]


RAIZ = buscar_raiz_proyecto(Path(__file__).resolve().parent)

RUTA_MODELO_RELATIVA = (
    Path("Fase 2")
    / "Evidencias Proyecto"
    / "Yolo"
    / "runs"
    / "detect"
    / "train-9"
    / "resultado"
    / "best.pt"
)
_CANDIDATOS = [RAIZ / RUTA_MODELO_RELATIVA, Path.cwd() / RUTA_MODELO_RELATIVA]
RUTA_MODELO_EPP = next((p for p in _CANDIDATOS if p.is_file()), _CANDIDATOS[0])

# Detector de rostros YuNet. Es una red neuronal, no una cascada Haar: detecta
# frontales y de perfil, y entrega las coordenadas de ambos ojos como landmarks.
RUTA_YUNET = RAIZ / "Fase 2" / "Evidencias Proyecto" / "models" / "face_detection_yunet_2023mar.onnx"
URL_YUNET = ("https://github.com/opencv/opencv_zoo/raw/main/models/"
             "face_detection_yunet/face_detection_yunet_2023mar.onnx")
YUNET_UMBRAL = 0.6
YUNET_NMS = 0.3

CONF_MIN = 0.20

# Confianza mínima por clase: un positivo flojo no debe "limpiar" una infracción.
CONF_MIN_POR_CLASE = {
    "Person": 0.40,
    "helmet": 0.30,
    "no_helmet": 0.30,
    "vest": 0.35,
    "none": 0.25,
}

CLASE_PERSONA = "Person"

# Tracker de seguimiento. Se fija explicitamente porque el checkpoint trained
# arrastra 'tracktrack.yaml' en sus args y ese devuelve boxes.id nulo.
TRACKER = "bytetrack.yaml"

# Lista estricta: el sistema ignora guantes, botas, gafas y cualquier otro objeto.
# 'none' sí se procesa, pero se reinterpreta por zona (ver clasificar_none).
CLASES_PERMITIDAS = {"Person", "helmet", "no_helmet", "vest", "none"}

# Clases que anclan la cabeza, usadas como respaldo si YuNet no encuentra un rostro.
CLASES_CABEZA = {"helmet", "no_helmet", "goggles", "no_goggle"}


CORTE_CABEZA = 0.33
TAMANO_CHALECO = 0.25
SOLAPAMIENTO_MIN = 0.35

VENTANA_SUAVIZADO = 5
MIN_FRAMES_PARA_ALERTAR = 2
FRAME_PARA_DESCARTAR = 45

# --- Difuminado a escala ---
OJO_REL_ANCHO = 0.55
OJO_REL_ALTO = 0.34
OJO_REL_Y_SIN_LANDMARKS = 0.41
# Respaldo sin detector: banda conservadora sobre la caja de cabeza, con el
# percentil 25 de las medidas reales (0.14 x 0.22) para que casi nunca se salga.
CABECA_REL_ANCHO = 0.14
CABECA_REL_ALTO = 0.22

COLORES = {
    "helmet": (0, 255, 0),       # Verde para casco
    "vest": (255, 255, 0),       # Celeste/Cian para chaleco
    "Person": (255, 0, 0),       # Azul para persona
    "no_helmet": (0, 255, 255),  # Amarillo
    "no_vest": (255, 0, 255),    # Magenta
}
COLOR_TEXTO = (255, 255, 255)
COLOR_CONTORNO = (0, 0, 0)
FONT = cv2.FONT_HERSHEY_SIMPLEX

TIPOS_INFRACCION = {
    "falta_casco": "missing_helmet",
    "sin_casco": "missing_helmet",
    "falta_chaleco": "missing_reflective_vest",
    "sin_chaleco": "missing_reflective_vest",
}


# ==================== UTILIDADES ====================
def solapamiento(caja, contenedor):
    """Fracción del área de 'caja' contenida en 'contenedor' (0.0 - 1.0)."""
    ax1, ay1, ax2, ay2 = caja
    bx1, by1, bx2, by2 = contenedor
    ix = max(0.0, min(ax2, bx2) - max(ax1, bx1))
    iy = max(0.0, min(ay2, by2) - max(ay1, by1))
    area = max(1.0, float(ax2 - ax1) * float(ay2 - ay1))
    return (ix * iy) / area


def posicion_relativa(caja, persona):
    """(relYc, relH) del EPP respecto a la caja de la persona."""
    _, py1, _, py2 = persona
    ex1, ey1, ex2, ey2 = caja
    alto = max(1.0, float(py2 - py1))
    return ((ey1 + ey2) / 2.0 - py1) / alto, (ey2 - ey1) / alto


def clasificar_none(caja, persona):
    """Reinterpreta 'none' según la zona del cuerpo en que cae.

    El modelo no tiene clase 'no_vest': la clase 5 'none' es una caja genérica
    de "sin implemento". Medido sobre el dataset, es del tamaño de un chaleco
    (relH 0.45 frente a 0.42) y se ubica en el torso (relYc 0.53). Por eso se
    resuelve por zona en vez de asumir que siempre significa chaleco.
    """
    rel_yc, rel_h = posicion_relativa(caja, persona)
    if rel_yc >= CORTE_CABEZA:
        return "no_vest"
    if rel_h < TAMANO_CHALECO:
        return "no_helmet"
    # Caja grande en la zona de la cabeza: accesorio mal etiquetado, se descarta.
    return None


def mejor_de_par(candidatos):
    """Resuelve el conflicto helmet/no_helmet por confianza."""
    if not candidatos:
        return None
    return max(candidatos, key=lambda e: e["conf"])["nombre"]


def evaluar_persona(parte):
    """Devuelve el frozenset de infracciones de una persona."""
    pares = {"casco": [], "chaleco": []}
    for e in parte:
        if e["nombre"] in ("helmet", "no_helmet"):
            pares["casco"].append(e)
        elif e["nombre"] in ("vest", "no_vest"):
            pares["chaleco"].append(e)

    casco = mejor_de_par(pares["casco"])
    chaleco = mejor_de_par(pares["chaleco"])

    infracciones = []
    if casco is None:
        infracciones.append("falta_casco")
    elif casco == "no_helmet":
        infracciones.append("sin_casco")
    if chaleco is None:
        infracciones.append("falta_chaleco")
    elif chaleco == "no_vest":
        infracciones.append("sin_chaleco")
    return frozenset(infracciones)


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


def detectar_rostros(detector, imagen):
    """[(caja_cara, ojos), ...] donde 'ojos' son las coordenadas x1,y1,x2,y2."""
    alto, ancho = imagen.shape[:2]
    if detector.getInputSize() != (ancho, alto):
        detector.setInputSize((ancho, alto))
    _, caras = detector.detect(imagen)
    if caras is None:
        return []
    salida = []
    for c in caras:
        caja = (float(c[0]), float(c[1]), float(c[2]), float(c[3]))
        # indices 4-7: ojo derecho (x,y) e izquierdo (x,y)
        ojos = (float(c[4]), float(c[5]), float(c[6]), float(c[7]))
        salida.append((caja, ojos))
    return salida


def clave_violacion(estado):
    """Clave semántica de un estado: falta_casco y sin_casco son la misma falta.

    Sin esto, el parpadeo de la deteccion 'none' hace que una persona genere un
    incidente nuevo cada vez que alterna entre 'falta_chaleco' y 'sin_chaleco'.
    """
    return tuple(sorted({TIPOS_INFRACCION[i] for i in estado if i in TIPOS_INFRACCION}))


def texto(frame, cadena, org, escala, color, grosor=2):
    """Texto con contorno para que se lea sobre cualquier fondo."""
    cv2.putText(frame, cadena, org, FONT, escala, COLOR_CONTORNO, grosor + 2, cv2.LINE_AA)
    cv2.putText(frame, cadena, org, FONT, escala, color, grosor, cv2.LINE_AA)


# ==================== MOTOR ====================
class MonitorEPP:
    """Detecta infracciones de EPP, difumina rostros y registra incidentes."""

    def __init__(self, ruta_modelo=None, ruta_yunet=None, carpeta_evidencia="incidents",
                 al_registrar=None):
        ruta_modelo = ruta_modelo or RUTA_MODELO_EPP
        if not Path(ruta_modelo).is_file():
            raise IOError(f"No se encontró el modelo YOLO: {ruta_modelo}")
        self.model = YOLO(str(ruta_modelo))
        self.detector = cargar_yunet(ruta_yunet or RUTA_YUNET)
        self.carpeta_evidencia = Path(carpeta_evidencia)
        self.al_registrar = al_registrar
        self.historial: dict[int, deque] = {}
        self.ultimo_estado: dict[int, frozenset] = {}
        self.estado_confirmado: dict[int, frozenset] = {}
        self.violacion_confirmada: dict[int, tuple] = {}
        self.ultimo_visto: dict[int, int] = {}
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
        """EPP asociados a la persona, con 'none' ya reinterpretables por zona."""
        partes = []
        for e in epps:
            if solapamiento(e["caja"], persona["caja"]) < SOLAPAMIENTO_MIN:
                continue
            nombre = e["nombre"]
            if nombre == "none":
                nombre = clasificar_none(e["caja"], persona["caja"])
                if nombre is None:
                    continue
            partes.append({**e, "nombre": nombre})
        return partes

    def _registrar_cambio(self, pid, estado, confianza, nuevos):
        """Anota un estado confirmado solo si cambia la infraccion semantica."""
        clave = clave_violacion(estado)
        if self.violacion_confirmada.get(pid) == clave:
            return
        self.violacion_confirmada[pid] = clave
        self.estado_confirmado[pid] = estado
        nuevos[pid] = (estado, confianza)

    # ---------- difuminado ----------
    @staticmethod
    def _difumar_roi(detector, roi):
        """Difumina la banda de ojos de cada rostro dentro del ROI.

        Devuelve el número de rostros difuminados.
        """
        if roi.size == 0:
            return 0
        n = 0
        for cara, ojos in detectar_rostros(detector, roi):
            fx, fy, fw, fh = cara
            if fw < 8 or fh < 8:
                continue
            cx = (ojos[0] + ojos[2]) / 2.0
            cy = (ojos[1] + ojos[3]) / 2.0
            if not (fx <= cx <= fx + fw and fy <= cy <= fy + fh):
                # Landmarks fuera de la caja: se cae a la posición anatómica.
                cx, cy = fx + fw / 2.0, fy + fh * OJO_REL_Y_SIN_LANDMARKS
            bx, by, bw, bh = banda_dentro(cara, cx, cy,
                                          fw * OJO_REL_ANCHO, fh * OJO_REL_ALTO)
            region = roi[by:by + bh, bx:bx + bw]
            if region.size == 0:
                continue
            k = int(min(max(bw, bh) * 2, 99)) | 1
            roi[by:by + bh, bx:bx + bw] = cv2.GaussianBlur(region, (k, k), 0)
            n += 1
        return n

    def difumar_rostros(self, frame, persona, cabezas):
        """Anonimiza el rostro de una persona. YuNet cubre frontal y perfil."""
        x1, y1, x2, y2 = persona
        alto_f, ancho_f = frame.shape[:2]
        x1, y1 = max(0, x1), max(0, y1)
        x2, y2 = min(ancho_f, x2), min(alto_f, y2)
        if x2 <= x1 or y2 <= y1:
            return 0
        roi = frame[y1:y2, x1:x2]
        n = self._difumar_roi(self.detector, roi)
        if n:
            return n
        # Sin rostro detectado: banda conservadora sobre la caja de cabeza.
        return self._difumar_cabeza(roi, cabezas)

    @staticmethod
    def _difumar_cabeza(roi, cabezas):
        if not cabezas:
            return 0
        mejor = max(cabezas, key=lambda c: c["caja"][2] * c["caja"][3])
        hx, hy, hw, hh = mejor["caja"]
        alto_roi, ancho_roi = roi.shape[:2]
        bx, by, bw, bh = banda_dentro(
            (0, 0, ancho_roi, alto_roi), hx + hw / 2.0, hy + hh / 2.0,
            hw * CABECA_REL_ANCHO, hh * CABECA_REL_ALTO)
        region = roi[by:by + bh, bx:bx + bw]
        if region.size == 0:
            return 0
        k = int(min(max(bw, bh) * 2, 99)) | 1
        roi[by:by + bh, bx:bx + bw] = cv2.GaussianBlur(region, (k, k), 0)
        return 1

    # ---------- evidencia ----------
    def guardar_evidencia(self, frame):
        """Guarda el frame ya difuminado en incidents/AAAA/MM/DD/."""
        ahora = datetime.now(timezone.utc)
        carpeta = self.carpeta_evidencia / ahora.strftime("%Y/%m/%d")
        carpeta.mkdir(parents=True, exist_ok=True)
        nombre = f"incidente-{ahora.strftime('%H%M%S-%f')}.jpg"
        ruta = carpeta / nombre
        cv2.imwrite(str(ruta), frame)
        return ruta.as_posix(), ahora

    def _registrar(self, frame, pid, estado, confianza):
        """Crea el incidente y lo entrega al callback si hay uno."""
        evidencia, momento = self.guardar_evidencia(frame)
        tipos = sorted({TIPOS_INFRACCION[i] for i in estado if i in TIPOS_INFRACCION})
        incidente = {
            "camera_id": f"camara-01",
            "zone_id": "zona-norte",
            "detected_at": momento.isoformat().replace("+00:00", "Z"),
            "violation_type": tipos[0] if tipos else "missing_helmet",
            "violation_types": tipos,
            "confidence": round(min(1.0, max(0.0, confianza)), 4),
            "evidence_path": evidencia,
            "person_track_id": int(pid),
            "beacon_alert": {"status": "skipped_offline", "latency_ms": None},
        }
        if self.al_registrar:
            self.al_registrar(incidente)
        return incidente

    # ---------- ciclo principal ----------
    def procesar(self, frame):
        """Analiza un frame. Devuelve la lista de incidentes nuevos."""
        self.n_frames += 1
        personas, epps, hay_seguimiento = self._detectar(frame)

        for pid in [p for p, v in self.ultimo_visto.items()
                    if self.n_frames - v > FRAME_PARA_DESCARTAR]:
            self.ultimo_visto.pop(pid, None)
            self.historial.pop(pid, None)
            self.ultimo_estado.pop(pid, None)
            self.estado_confirmado.pop(pid, None)
            self.violacion_confirmada.pop(pid, None)

        incidentes, nuevos = [], {}
        for p in personas:
            pid = p["id"]
            self.ultimo_visto[pid] = self.n_frames
            partes = self._partes_de(epps, p)
            estado = evaluar_persona(partes)
            # Si no hay EPP detectado, la confianza de la persona es la unica
            # señal disponible; con 0 el incidente no significaria nada.
            confianza = max((e["conf"] for e in partes), default=p["conf"])

            if hay_seguimiento:
                ventana = self.historial.setdefault(pid, deque(maxlen=VENTANA_SUAVIZADO))
                ventana.append(estado)
                if sum(1 for s in ventana if s == estado) >= MIN_FRAMES_PARA_ALERTAR:
                    self._registrar_cambio(pid, estado, confianza, nuevos)
                self.ultimo_estado[pid] = estado
                visible = self.estado_confirmado.get(pid, estado)
            else:
                # Sin IDs no hay identidad estable entre frames, pero el estado
                # se sigue notificando una sola vez por cambio.
                self._registrar_cambio(pid, estado, confianza, nuevos)
                visible = self.estado_confirmado.get(pid, estado)

        # El difuminado va antes de dibujar, para que la evidencia salga limpia.
        for p in personas:
            cabezas = [e for e in epps if e["nombre"] in CLASES_CABEZA]
            self.difumar_rostros(frame, p["caja"], cabezas)

        for p in personas:
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
        texto(frame, f"Personas: {len(personas)} | FPS: {self.fps:.1f}",
              (10, 25), 0.6, COLOR_TEXTO)

        # La evidencia se genera con las marcas ya dibujadas.
        for pid, (estado, confianza) in nuevos.items():
            if estado:
                incidentes.append(self._registrar(frame, pid, estado, confianza))
                self._consola(pid, estado)
        return incidentes

    @staticmethod
    def _consola(pid, estado):
        if estado:
            print(f"[{datetime.now().strftime('%H:%M:%S')}] "
                  f"Persona {pid}: INFRACCIONES -> {', '.join(sorted(estado))}")
        else:
            print(f"[{datetime.now().strftime('%H:%M:%S')}] "
                  f"Persona {pid}: Cumplimiento completo (Casco y Chaleco)")
