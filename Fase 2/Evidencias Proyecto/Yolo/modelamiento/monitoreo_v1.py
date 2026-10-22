import cv2
import time
from ultralytics import YOLO

# ==================== CONFIGURACIÓN ====================
RUTA_MODELO_EPP = r"Fase 2\Evidencias Proyecto\models\cascovision_yolo26s.pt"
FUENTE_VIDEO = 0                 
CONF_MIN = 0.20                  
CLASE_PERSONA = "Person"

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

# ==================== MODELO YOLO ====================
model = YOLO(RUTA_MODELO_EPP)

# ==================== UTILIDADES ====================
def centro_dentro(caja, contenedor):
    """True si el centro de 'caja' está dentro de 'contenedor'."""
    cx = (caja[0] + caja[2]) // 2
    cy = (caja[1] + caja[3]) // 2
    return contenedor[0] <= cx <= contenedor[2] and contenedor[1] <= cy <= contenedor[3]

# ==================== VIDEO Y BUCLE PRINCIPAL ====================
cap = cv2.VideoCapture(FUENTE_VIDEO)
if not cap.isOpened():
    raise IOError("No se pudo abrir la fuente de video.")

print("\n--- Monitoreo CascoVision Iniciado ---")
print("Enfocado estrictamente en CASCO y CHALECO.")
print("Presiona 'q' en la ventana de video para finalizar.\n")

ultimo_estado = {}
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

    # Análisis por persona
    for p in personas:
        pid = p["id"]
        partes = [e for e in epps if centro_dentro(e["caja"], p["caja"])]
        nombres = {e["nombre"] for e in partes}
        
        infracciones = sorted(e["nombre"] for e in partes if e["nombre"].startswith("no_"))
        
        # --- REGLAS LÓGICAS PARA CASCO Y CHALECO ---
        if "helmet" not in nombres and "no_helmet" not in nombres:
            infracciones.append("falta_helmet")
        if "vest" not in nombres and "no_vest" not in nombres:
            infracciones.append("falta_vest")
            
        estado = tuple(sorted(infracciones))

        # Consola
        if ultimo_estado.get(pid) != estado:
            ultimo_estado[pid] = estado
            if estado:
                print(f"⚠️ Persona {pid}: INFRACCIONES -> {', '.join(estado)}")
            else:
                print(f"✅ Persona {pid}: Cumplimiento completo (Casco y Chaleco)")

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