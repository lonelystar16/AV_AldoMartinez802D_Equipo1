from ultralytics import YOLO

# Carga del modelo yolo26s
model = YOLO(r"Fase 2\Evidencias Proyecto\models\cascovision_yolo26s.pt")

# entrenamiento del modelo de dataset a traves de un archivo yaml que contiene la ruta de las imagenes y sus respectivas etiquetas
model.train(data=r"Fase 2\Evidencias Proyecto\Yolo\dataset\construccion-implementos.yaml", epochs=100, imgsz=640)