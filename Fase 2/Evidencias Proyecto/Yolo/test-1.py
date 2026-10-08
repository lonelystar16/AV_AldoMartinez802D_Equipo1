from ultralytics import YOLO
import math

# Se carga el modelo entrenado con los diferentes implementos de seguridad
model = YOLO(r"C:\Users\jikonyx\Documents\vscode\AV_AldoMartinez802D_Equipo1\Fase 2\Evidencias Proyecto\Yolo\runs\detect\train-9\weights\best.pt")

# 2. Inferencia en webcam sin FP16 forzado
# Se usa stream=True para iterar eficientemente frame por frame
results = model.predict(source=0, show=True, stream=True)

# 3. Consumir el generador para procesar los frames
for r in results:
    # Obtener el objeto de cajas detectadas en el frame actual
    boxes = r.boxes
    
    if len(boxes) > 0:
        print("\n--- Detecciones en el frame ---")
        
        # se itera sobre cada objeto detectado en el frame
        for box in boxes:
            # Obtener el ID de la clase y su nivel de confianza
            cls_id = int(box.cls[0])
            conf = math.ceil((box.conf[0] * 100)) / 100
            
            # recupera el diccionario de nombres de clases del modelo para obtener el nombre de la clase detectada
            cls_name = model.names[cls_id]
            
            # Validar e imprimir el estado del implemento
            # Clases de implementos faltantes: 7 (no_helmet), 8 (no_goggle), 9 (no_gloves), 10 (no_boots)
            if cls_id in [7, 8, 9, 10]:
                print(f"⚠️ INFRACCIÓN: Detectado '{cls_name}' con {conf}% de confianza.")
            
            # Clases de implementos correctos: 0 (helmet), 1 (gloves), 2 (vest), 3 (boots), 4 (goggles)
            elif cls_id in [0, 1, 2, 3, 4]:
                print(f"✅ CUMPLIMIENTO: Detectado '{cls_name}' con {conf}% de confianza.")
                
            # Identificación general a través de cada clase detectada, sin importar si es un implemento o no
            else:
                print(f"ℹ️ Info: Detectado '{cls_name}' ({conf}%)")
    else:
        # Opcional: imprimir algo si no hay nadie en cámara para saber que el ciclo sigue vivo
        pass