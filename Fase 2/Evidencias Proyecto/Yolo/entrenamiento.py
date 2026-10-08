from pathlib import Path
from ultralytics import YOLO

# Obtener la carpeta donde está este script
BASE_DIR = Path(__file__).resolve().parent

# Ruta absoluta al archivo .yaml dentro de esa misma carpeta
DATASET_PATH = BASE_DIR / "clothing_dataset.yaml"

model = YOLO("yolo26s.pt")

# Iniciar entrenamiento apuntando a la ruta absoluta
model.train(
    data=str(DATASET_PATH),
    epochs=50,
    imgsz=640,
    workers=2  # Evita sobrecargar la CPU en Windows
)