import cv2
import os
import urllib.request
from ultralytics import YOLO

# 1. Ruta local donde se guardará el archivo en tu carpeta 'testing y modelamiento'
ruta_cascade_local = 'haarcascade_eye.xml'

# Si el archivo no existe, lo descargamos automáticamente
if not os.path.exists(ruta_cascade_local):
    print(f"Descargando {ruta_cascade_local} desde el repositorio oficial de OpenCV...")
    url = "https://raw.githubusercontent.com/opencv/opencv/master/data/haarcascades/haarcascade_eye.xml"
    urllib.request.urlretrieve(url, ruta_cascade_local)
    print("Descarga completada.")

# Cargar el detector desde el archivo local
eye_cascade = cv2.CascadeClassifier(ruta_cascade_local)

if eye_cascade.empty():
    raise IOError("Error crítico: El archivo se descargó pero OpenCV no pudo cargarlo.")

# 2. Cargar el modelo YOLO
model = YOLO(r"Fase 2\Evidencias Proyecto\models\cascovision_yolo26s.pt")
model.model.float()

# 3. Cargar imagen de prueba
ruta_imagen = r"Fase 2\Evidencias Proyecto\Yolo\testing y modelamiento\testeo.jpg"
frame = cv2.imread(ruta_imagen)

if frame is None:
    raise ValueError(f"Error crítico: No se pudo cargar la imagen: {ruta_imagen}")

gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

# Mapeo de clases de implementos de seguridad
class_names = {
    0: "helmet", 1: "gloves", 2: "vest", 3: "boots", 4: "goggles", 
    6: "Person", 7: "no_helmet", 8: "no_goggle", 9: "no_gloves", 10: "no_boots"
}

# Colores para semaforización visual (Verde = Cumple, Rojo = No cumple, Azul = Persona)
colors = {
    0: (0, 255, 0),    # helmet
    1: (0, 255, 0),    # gloves
    2: (255, 255, 0),  # vest 
    3: (0, 255, 0),    # boots
    4: (0, 255, 0),    # goggles
    6: (255, 0, 0),    # Person
    7: (0, 0, 255),    # no_helmet
    8: (0, 0, 255),    # no_goggle
    9: (0, 0, 255),    # no_gloves
    10: (0, 0, 255)    # no_boots
}

# 4. Inferencia del modelo
results = model.predict(source=frame, show=False)

# 5. Procesamiento de resultados
for r in results:
    boxes = r.boxes
    for box in boxes:
        cls_id = int(box.cls[0])
        conf = float(box.conf[0])
        x1, y1, x2, y2 = map(int, box.xyxy[0])
        
        # Filtro de privacidad: Difuminado ocular únicamente
        if cls_id == 6:
            alto_persona = y2 - y1
            y_limite_cabeza = y1 + int(alto_persona * 0.40) # Buscar ojos solo en el 40% superior
            
            roi_cabeza_color = frame[y1:y_limite_cabeza, x1:x2]
            roi_cabeza_gray = gray[y1:y_limite_cabeza, x1:x2]
            
            if roi_cabeza_color.size > 0:
                eyes = eye_cascade.detectMultiScale(roi_cabeza_gray, scaleFactor=1.1, minNeighbors=5, minSize=(10, 10))
                for (ex, ey, ew, eh) in eyes:
                    roi_ojo = roi_cabeza_color[ey:ey+eh, ex:ex+ew]
                    if roi_ojo.size > 0:
                        # Difuminado focalizado en los ojos
                        blurred_eye = cv2.GaussianBlur(roi_ojo, (15, 15), 5)
                        roi_cabeza_color[ey:ey+eh, ex:ex+ew] = blurred_eye
                        
            # Opcional: Dibujar caja alrededor de la persona
            cv2.rectangle(frame, (x1, y1), (x2, y2), colors[6], 1)
            
        # Detección de EPP (Casco, Guantes, Anteojos, Chaleco, Botas)
        elif cls_id in class_names:
            label_text = f"{class_names[cls_id]} {conf:.2f}"
            color = colors.get(cls_id, (255, 255, 255))
            
            # Dibujar caja y etiqueta para el implemento
            cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
            
            # Fondo para el texto (mejora la legibilidad)
            (w, h), _ = cv2.getTextSize(label_text, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 1)
            cv2.rectangle(frame, (x1, y1 - 20), (x1 + w, y1), color, -1)
            cv2.putText(frame, label_text, (x1, y1 - 5), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 0), 1)

# 6. Despliegue de imagen final
cv2.imshow("Monitoreo de EPP con Privacidad Ocular", frame)
cv2.waitKey(0)
cv2.destroyAllWindows()