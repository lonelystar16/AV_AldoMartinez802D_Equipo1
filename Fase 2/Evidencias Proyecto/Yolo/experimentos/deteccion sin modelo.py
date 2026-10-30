from ultralytics import YOLO

# 1. Cargar el modelo
model = YOLO(r"Fase 2\Evidencias Proyecto\models\cascovision_yolo26s.pt")

# 2. Inferencia en webcam sin FP16 forzado (usar half=False o omitirlo)
# Se usa stream=True para iterar eficientemente frame por frame
results = model.predict(source=0, show=True, stream=True)

# 3. Consumir el generador para procesar los frames
for r in results:
    pass