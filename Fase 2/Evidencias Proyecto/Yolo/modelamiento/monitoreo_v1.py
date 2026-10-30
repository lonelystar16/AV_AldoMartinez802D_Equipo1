"""Monitoreo de EPP en la cámara local, con ping más frecuente.

Variante del monitoreo local con un ping de **30 segundos** en lugar de los
60 s del motor (`monitoreo_v2.py`). Se usa cuando se quiere más agilidad en el
recordatorio.

El ciclo de vida del aviso de cada persona es el mismo que en el motor:

- **INICIO**: alguien aparece sin EPP. Se avisa de inmediato.
- **PING**: si sigue sin cambios, se vuelve a avisar cada 30 s con los mismos
  datos ya registrados, sin abrir un registro nuevo.
- **FIN**: la persona se pone el EPP, o deja de verse hasta vencer la gracia.
  Se cierra el registro.

"""

import math
import time

import cv2
from ultralytics import YOLO

from motor_cascovision import (
    FRAME_PARA_DESCARTAR,
    GRACIA_CIERRE_SEGUNDOS,
    RUTA_MODELO_EPP,
    RUTA_YUNET,
    alcance_reaparicion,
    cargar_yunet,
    centro_caja,
    difumar_roi,
    difumar_rostros,
)

# ==================== CONFIGURACIÓN ====================
# La ruta del modelo la resuelve el motor: prefiere el .onnx exportado y cae
# al .pt si no está. Escrita a mano aquí, además, dependía del CWD.
FUENTE_VIDEO = 0
CONF_MIN = 0.20
CLASE_PERSONA = "Person"

# Intervalo del ping de mantenimiento, en segundos. Es lo que diferencia este
# script de `monitoreo_v2.py`, que usa los 60 s del motor.
PING_SEGUNDOS = 30

# Lista estricta: el sistema ignorará guantes, botas y cualquier otro objeto
CLASES_PERMITIDAS = {"Person", "helmet", "no_helmet", "vest", "no_vest", "none"}
PALABRAS_LENTES = ("glass", "lente", "goggle")

COLORES = {
    "helmet": (0, 255, 0),       # Verde para casco
    "vest": (255, 255, 0),       # Celeste/Cian para chaleco
    "Person": (255, 0, 0),       # Azul para persona
    "no_helmet": (0, 255, 255),  # Amarillo
    "no_vest": (255, 0, 255),    # Magenta
}
FONT = cv2.FONT_HERSHEY_SIMPLEX

# Clases que anclan la cabeza, para el respaldo de difuminado cuando YuNet no
# detecta un rostro.
CLASES_CABEZA = {"helmet", "no_helmet"}

# ==================== MODELO YOLO ====================
model = YOLO(RUTA_MODELO_EPP)
detector_rostros = cargar_yunet(RUTA_YUNET)


# ==================== UTILIDADES ====================
def centro_dentro(caja, contenedor):
    """True si el centro de 'caja' está dentro de 'contenedor'."""
    cx = (caja[0] + caja[2]) // 2
    cy = (caja[1] + caja[3]) // 2
    return contenedor[0] <= cx <= contenedor[2] and contenedor[1] <= cy <= contenedor[3]


# El detector alterna entre la clase 'no_helmet' y la lógica de 'falta_helmet'
# según si llegó a verse la cabeza. Identificar la falta por el nombre que le
# dio el detector abriría un registro nuevo cada vez que parpadea: la falta se
# nombra por lo que falta, no por cómo la llamó YOLO.
CLAVES_FALTA = {
    "no_helmet": "sin_casco",
    "falta_helmet": "sin_casco",
    "no_vest": "sin_chaleco",
    "falta_vest": "sin_chaleco",
}


def clave_falta(estado):
    """Clave semántica de las faltas de una persona.

    `("no_helmet",)` y `("falta_helmet",)` son la misma falta y devuelven la
    misma clave: así el parpadeo del detector no parte la infracción en dos.
    """
    return tuple(sorted({CLAVES_FALTA.get(nombre, nombre) for nombre in estado}))


def retomar_episodio(pid, clave):
    """Vuelve a enganchar al episodio en espera con la misma falta.

    El detector de 'Person' parpadea y ByteTrack le reparte otro id al volver.
    Si se abriera un INICIO en ese hueco, una persona que nunca salió de la
    cámara quedaría partida en dos registros. Solo se retoma si además
    reaparece más o menos donde se fue, para no darle a alguien que entra por
    otro lado el episodio de la anterior. Devuelve True si lo retomó.
    """
    centro = centro_caja(caja_vista.get(pid))
    for i in range(len(en_espera) - 1, -1, -1):
        item = en_espera[i]
        if item["clave"] != clave:
            continue
        if centro is not None and item["centro"] is not None:
            if math.hypot(centro[0] - item["centro"][0],
                          centro[1] - item["centro"][1]) > item["radio"]:
                continue
        en_espera.pop(i)
        episodios[pid] = item["episodio"]
        return True
    return False


# ==================== VIDEO Y BUCLE PRINCIPAL ====================
cap = cv2.VideoCapture(FUENTE_VIDEO)
if not cap.isOpened():
    raise IOError("No se pudo abrir la fuente de video.")

print("\n--- Monitoreo CascoVision Iniciado ---")
print("Enfocado estrictamente en CASCO y CHALECO.")
print("Evidencia: rostros difuminados con YuNet antes de dibujar.")
print(f"INICIO: aviso inmediato al ver a alguien sin EPP.")
print(f"PING:   si sigue sin cambios, se reavisa cada {PING_SEGUNDOS} s.")
print("FIN:    aviso al cumplir, para registrar cuando termino.")
print(f"GRACIA: quien se pierde de vista no cierra el registro hasta "
      f"{GRACIA_CIERRE_SEGUNDOS} s: si vuelve con la misma falta, sigue siendo "
      f"el mismo.")
print("Presiona 'q' en la ventana de video para finalizar.\n")

ultimo_estado = {}
# Episodio en curso por persona: cuando empezo y cuando fue el ultimo ping.
# Mientras este presente, se reavisa cada PING_SEGUNDOS sin abrir registro nuevo.
episodios = {}
# Seguimiento entre frames. Sin esto no se distingue a alguien a quien el
# detector de 'Person' dejó de ver de alguien que se fue de verdad.
marco = 0
ultimo_visto = {}
caja_vista = {}
# Episodios de quienes dejaron de verse: se retoman si vuelven con la misma
# falta y cerca de donde se fue, y se cierran al vencer la gracia.
en_espera = []
t_prev = time.time()

while True:
    ok, frame = cap.read()
    if not ok:
        break

    results = model.track(frame, persist=True, conf=CONF_MIN, verbose=False)
    boxes = results[0].boxes
    ids = boxes.id.int().tolist() if boxes.id is not None else list(range(len(boxes)))

    personas, epps = [], []
    for i, box in enumerate(boxes):
        cls_name = model.names[int(box.cls[0])]

        # --- TRANSFORMACIÓN DE 'NONE' A 'NO_VEST' ---
        if cls_name == "none":
            cls_name = "no_vest"

        # Filtro estricto: solo permitimos lo que está en la lista blanca
        if cls_name not in CLASES_PERMITIDAS or any(p in cls_name.lower() for p in PALABRAS_LENTES):
            continue

        item = {
            "nombre": cls_name,
            "caja": tuple(map(int, box.xyxy[0])),
            "conf": float(box.conf[0]),
            "id": ids[i],
        }
        (personas if cls_name == CLASE_PERSONA else epps).append(item)

    # Seguimiento: se apartan los episodios de quienes dejaron de verse y se
    # cierran los vencidos. Va antes del análisis para que el cierre salga en
    # el mismo frame en que se pierde de vista.
    marco += 1
    instante = time.monotonic()
    for perdido in [k for k, v in ultimo_visto.items()
                    if marco - v > FRAME_PARA_DESCARTAR]:
        ultimo_visto.pop(perdido, None)
        caja = caja_vista.pop(perdido, None)
        clave_perdida = clave_falta(ultimo_estado.pop(perdido, ()))
        episodio = episodios.pop(perdido, None)
        if episodio is not None:
            en_espera.append({"pid": perdido, "clave": clave_perdida,
                              "centro": centro_caja(caja),
                              "radio": alcance_reaparicion(caja),
                              "episodio": episodio, "perdido": instante})

    # La persona no volvió: ya no puede afirmarse que siga sin EPP, se cierra.
    for i in range(len(en_espera) - 1, -1, -1):
        if instante - en_espera[i]["perdido"] > GRACIA_CIERRE_SEGUNDOS:
            vencido = en_espera.pop(i)
            print(f"✅ Persona {vencido['pid']}: FIN del registro (ya no esta sin EPP)")

    # El difuminado va antes de dibujar, para que la evidencia salga limpia.
    for p in personas:
        cabezas = [e for e in epps if e["nombre"] in CLASES_CABEZA]
        difumar_rostros(detector_rostros, frame, p["caja"], cabezas)
    if not personas and epps:
        # YOLO no acerto la clase 'Person' (gafas, sombra, perfil) y la
        # persona sigue en el encuadre. Sin su caja no hay donde recortar,
        # asi que se difumina el frame entero: el anonimato no depende de
        # que el detector acierte.
        difumar_roi(detector_rostros, frame)

    # Análisis por persona
    for p in personas:
        pid = p["id"]
        # Este frame sí la vio: cuenta para la gracia de cierre.
        ultimo_visto[pid] = marco
        caja_vista[pid] = p["caja"]
        partes = [e for e in epps if centro_dentro(e["caja"], p["caja"])]
        nombres = {e["nombre"] for e in partes}

        infracciones = sorted(e["nombre"] for e in partes if e["nombre"].startswith("no_"))

        # --- REGLAS LÓGICAS PARA CASCO Y CHALECO ---
        if "helmet" not in nombres and "no_helmet" not in nombres:
            infracciones.append("falta_helmet")
        if "vest" not in nombres and "no_vest" not in nombres:
            infracciones.append("falta_vest")

        estado = tuple(sorted(infracciones))

        # Ciclo de vida del aviso: INICIO, PING o FIN. Se decide sobre la
        # clave semántica y no sobre el estado crudo: que el detector diga
        # 'no_helmet' o 'falta_helmet' no abre otro registro para la misma
        # persona y la misma falta.
        anterior = ultimo_estado.get(pid)
        clave = clave_falta(estado)
        clave_anterior = clave_falta(anterior) if anterior else ()
        ultimo_estado[pid] = estado
        ahora = time.monotonic()

        if clave and clave != clave_anterior:
            # INICIO: se avisa de inmediato, sin esperar el ping de nadie.
            # Salvo que retome el episodio en espera: entonces no hay nadie
            # nuevo, es la misma persona volviendo a la vista. Solo se intenta
            # si esta persona era desconocida (acaba de perderse o es nueva),
            # para que un cambio de falta en alguien visible no se quede con
            # el episodio que otro dejó en espera.
            if not (anterior is None and retomar_episodio(pid, clave)):
                episodios[pid] = {"inicio": ahora, "ultimo_ping": ahora}
                print(f"⚠️ Persona {pid}: INICIO -> {', '.join(estado)}")
        elif clave:
            # Sigue sin EPP: PING si ya vencio el intervalo.
            episodio = episodios.get(pid)
            if episodio is None:
                episodios[pid] = {"inicio": ahora, "ultimo_ping": ahora}
                print(f"⚠️ Persona {pid}: INICIO -> {', '.join(estado)}")
            elif ahora - episodio["ultimo_ping"] >= PING_SEGUNDOS:
                episodio["ultimo_ping"] = ahora
                print(f"🔁 Persona {pid}: SIGUE SIN CAMBIOS -> {', '.join(estado)}")
        elif clave_anterior:
            # FIN: ya no está sin EPP, se cierra el registro.
            episodios.pop(pid, None)
            print(f"✅ Persona {pid}: FIN del registro (ya no esta sin EPP)")

        # Dibujo del recuadro de la persona
        x1, y1, x2, y2 = p["caja"]
        cv2.rectangle(frame, (x1, y1), (x2, y2), COLORES["Person"], 1)
        cv2.putText(frame, f"ID {pid}", (x1, y1 - 8), FONT, 0.5, COLORES["Person"], 2)

        # Alertas visuales en pantalla si faltan elementos
        if "helmet" not in nombres and "no_helmet" not in nombres:
            cv2.putText(frame, "ALERTA: FALTA CASCO", (x1 + 5, y1 + 30),
                        FONT, 0.7, (0, 255, 255), 2)
        if "vest" not in nombres and "no_vest" not in nombres:
            cv2.putText(frame, "ALERTA: FALTA CHALECO", (x1 + 5, y1 + 60),
                        FONT, 0.7, (255, 0, 255), 2)

    # Dibujo de Casco o Chaleco detectado sobre el frame
    for e in epps:
        color = COLORES.get(e["nombre"], (255, 255, 255))
        x1, y1, x2, y2 = e["caja"]
        cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
        cv2.putText(frame, f"{e['nombre']} {e['conf']:.2f}", (x1, y1 - 5),
                    FONT, 0.5, color, 2)

    # HUD de rendimiento en texto oscuro
    ahora = time.time()
    fps = 1.0 / max(ahora - t_prev, 1e-6)
    t_prev = ahora
    cv2.putText(frame, f"Personas: {len(personas)} | FPS: {fps:.1f}", (10, 25),
                FONT, 0.6, (0, 0, 0), 2)

    cv2.imshow("Monitoreo CascoVision en Tiempo Real", frame)
    if cv2.waitKey(1) & 0xFF == ord("q"):
        break

cap.release()
cv2.destroyAllWindows()
