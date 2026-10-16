import cv2
import os
import math
import urllib.request
from ultralytics import YOLO

# 1. Configurar y validar el detector de ojos
ruta_cascade_local = 'haarcascade_eye.xml'
if not os.path.exists(ruta_cascade_local):
    print("Descargando haarcascade_eye.xml...")
    urllib.request.urlretrieve("https://raw.githubusercontent.com/opencv/opencv/master/data/haarcascades/haarcascade_eye.xml", ruta_cascade_local)

eye_cascade = cv2.CascadeClassifier(ruta_cascade_local)
if eye_cascade.empty():
    raise IOError("Error crítico: No se pudo cargar el detector de ojos.")

# 2. Cargar el modelo YOLO entrenado
model = YOLO(r"Fase 2\Evidencias Proyecto\models\cascovision_yolo26s.pt")
model.model.float()

# Semaforización de colores (BGR) - Clases de lentes (4, 8) y none (5) excluidas
colors = {
    0: (0, 255, 0),    # helmet
    1: (0, 255, 0),    # gloves
    2: (255, 255, 0),  # vest
    3: (0, 255, 0),    # boots
    6: (255, 0, 0),    # Person
    7: (0, 0, 255),    # no_helmet
    9: (0, 0, 255),    # no_gloves
    10: (0, 0, 255)    # no_boots
}

# 3. Iniciar captura de video (webcam)
cap = cv2.VideoCapture(0)
print("\n--- Monitoreo CascoVision Iniciado ---")
print("Presiona la tecla 'q' en la ventana de video para finalizar.\n")

while cap.isOpened():
    ret, frame = cap.read()
    if not ret:
        print("Error: No se puede leer la señal de video.")
        break
        
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    
    # Inferencia silenciosa
    results = model.predict(source=frame, show=False, verbose=False)
    
    r = results[0]
    boxes = r.boxes
    
    if len(boxes) > 0:
        print("\n--- Estado EPP Frame ---")
        
        clases_detectadas_en_frame = []
        coord_persona = None 

        for box in boxes:
            cls_id = int(box.cls[0])
            
            # Omitir procesamiento para clases de anteojos (4, 8) y 'none' (5)
            if cls_id in [4, 5, 8]:
                continue
                
            conf = math.ceil((box.conf[0] * 100)) / 100
            cls_name = model.names[cls_id]
            x1, y1, x2, y2 = map(int, box.xyxy[0])
            
            clases_detectadas_en_frame.append(cls_id)
            
            # A. Lógica para la Persona (Filtro Ocular Híbrido)
            if cls_id == 6:
                coord_persona = (x1, y1, x2, y2)
                alto_persona = y2 - y1
                ancho_persona = x2 - x1
                y_limite_cabeza = y1 + int(alto_persona * 0.40)
                
                roi_cabeza_color = frame[y1:y_limite_cabeza, x1:x2]
                roi_cabeza_gray = gray[y1:y_limite_cabeza, x1:x2]
                
                if roi_cabeza_color.size > 0:
                    # Parámetros relajados para detección en condiciones subóptimas
                    eyes = eye_cascade.detectMultiScale(roi_cabeza_gray, scaleFactor=1.05, minNeighbors=3, minSize=(10, 10))
                    
                    if len(eyes) > 0:
                        min_ex = min([e[0] for e in eyes])
                        max_ex_ew = max([e[0] + e[2] for e in eyes])
                        min_ey = min([e[1] for e in eyes])
                        max_ey_eh = max([e[1] + e[3] for e in eyes])
                        
                        # Padding agrandado para asegurar cobertura total de lentes/sombras
                        padding_y = int((max_ey_eh - min_ey) * 0.40)
                        padding_x = int((max_ex_ew - min_ex) * 0.25)
                        
                        ojos_x1 = max(0, min_ex - padding_x)
                        ojos_y1 = max(0, min_ey - padding_y)
                        ojos_x2 = min(roi_cabeza_color.shape[1], max_ex_ew + padding_x)
                        ojos_y2 = min(roi_cabeza_color.shape[0], max_ey_eh + padding_y)
                        
                        roi_bloque_ojos = roi_cabeza_color[ojos_y1:ojos_y2, ojos_x1:ojos_x2]
                        if roi_bloque_ojos.size > 0:
                            blurred_eyes = cv2.GaussianBlur(roi_bloque_ojos, (45, 25), 10)
                            roi_cabeza_color[ojos_y1:ojos_y2, ojos_x1:ojos_x2] = blurred_eyes
                    
                    else:
                        # FALLBACK GEOMÉTRICO: Franja anatómica si falla el clasificador Haar
                        y_fallback_inicio = int(alto_persona * 0.08)
                        y_fallback_fin = int(alto_persona * 0.20)
                        x_fallback_inicio = int(ancho_persona * 0.15)
                        x_fallback_fin = ancho_persona - int(ancho_persona * 0.15)
                        
                        y_fallback_inicio = max(0, min(y_fallback_inicio, roi_cabeza_color.shape[0]))
                        y_fallback_fin = max(0, min(y_fallback_fin, roi_cabeza_color.shape[0]))
                        
                        roi_fallback = roi_cabeza_color[y_fallback_inicio:y_fallback_fin, x_fallback_inicio:x_fallback_fin]
                        
                        if roi_fallback.size > 0:
                            blurred_fallback = cv2.GaussianBlur(roi_fallback, (45, 25), 10)
                            roi_cabeza_color[y_fallback_inicio:y_fallback_fin, x_fallback_inicio:x_fallback_fin] = blurred_fallback
                
                cv2.rectangle(frame, (x1, y1), (x2, y2), colors[6], 1)
                
            # B. Lógica para Implementos Activos
            else:
                color = colors.get(cls_id, (255, 255, 255))
                cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
                cv2.putText(frame, f"{cls_name} {conf}", (x1, y1 - 5), cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 2)

            # C. Impresión de alertas en consola
            if cls_id in [7, 9, 10]:
                print(f"⚠️ INFRACCIÓN: Detectado '{cls_name}' con {conf} de confianza.")
            elif cls_id in [0, 1, 2, 3]:
                print(f"✅ CUMPLIMIENTO: Detectado '{cls_name}' con {conf} de confianza.")
        
        # D. Inferencia de Chaleco (Torso)
        if 6 in clases_detectadas_en_frame and 2 not in clases_detectadas_en_frame:
            print("⚠️ INFRACCIÓN CRÍTICA: Falta 'vest' (chaleco reflectante no detectado en el torso).")
            if coord_persona:
                px1, py1, px2, py2 = coord_persona
                y_torso = py1 + int((py2 - py1) * 0.5)
                cv2.putText(frame, "ALERTA: FALTA CHALECO", (px1, y_torso), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 255), 2)

    cv2.imshow("Monitoreo CascoVision en Tiempo Real", frame)
    
    # Salir con la tecla 'q'
    if cv2.waitKey(1) & 0xFF == ord('q'):
        print("\nCerrando sistema...")
        break

cap.release()
cv2.destroyAllWindows()