"""Entrenamiento del detector de EPP de CascoVision.

Lanza la corrida de Ultralytics sobre el dataset de 5 clases y deja la corrida
en `Yolo/runs/detect/<nombre>/`. El script no decide nada: solo aplica los
parametros que se le pasan, para que la configuracion de cada corrida quede
registrada en los `args.yaml` que genera Ultralytics.

Ejemplos:

    # Corrida de referencia (5 clases, desde la base COCO)
    uv run python "Fase 2/Evidencias Proyecto/Yolo/modelamiento/entrenamiento.py"

    # Reanudar o variant
    uv run python "Fase 2/Evidencias Proyecto/Yolo/modelamiento/entrenamiento.py" \
        --name train-11 --epochs 150 --batch 8
"""

import argparse
import sys
from pathlib import Path

from ultralytics import YOLO

# Raiz del repositorio: la carpeta que contiene "Fase 2".
RAIZ = next((p for p in Path(__file__).resolve().parents if (p / "Fase 2").is_dir()),
            Path(__file__).resolve().parents[4])

RUTA_DATOS = RAIZ / "Fase 2" / "Evidencias Proyecto" / "Yolo" / "dataset" / "construccion-implementos.yaml"
RUTA_PROYECTO = RAIZ / "Fase 2" / "Evidencias Proyecto" / "Yolo" / "runs" / "detect"
MODELO_BASE = "yolo26s.pt"


def parse_args() -> argparse.Namespace:
    analizador = argparse.ArgumentParser(description="Entrenamiento del detector de EPP")
    analizador.add_argument("--data", default=str(RUTA_DATOS),
                            help="Ruta del YAML del dataset")
    analizador.add_argument("--model", default=MODELO_BASE,
                            help="Modelo base. 'yolo26s.pt' para partir de COCO")
    analizador.add_argument("--name", default="train-10",
                            help="Nombre de la corrida dentro del proyecto de runs")
    analizador.add_argument("--epochs", type=int, default=100)
    analizador.add_argument("--batch", type=int, default=16)
    analizador.add_argument("--imgsz", type=int, default=640)
    analizador.add_argument("--patience", type=int, default=30,
                            help="Epocas sin mejora antes de detener. train-9 uso 100 "
                                 "y sobreajusto")
    analizador.add_argument("--device", default="0",
                            help="'0' para la GPU, 'cpu' para forzar CPU")
    analizador.add_argument("--workers", type=int, default=4)
    analizador.add_argument("--seed", type=int, default=0)
    analizador.add_argument("--project", default=str(RUTA_PROYECTO))
    analizador.add_argument("--resume", action="store_true",
                            help="Continuar una corrida interrumpida")
    return analizador.parse_args()


def main() -> None:
    args = parse_args()

    if not Path(args.data).is_file():
        sys.exit(f"No se encuentra el YAML del dataset: {args.data}")

    # Ultralytics descarga el modelo base la primera vez (yolo26s.pt).
    modelo = YOLO(args.model)

    if args.resume:
        # Reanuda el ultimo checkpoint de la corrida: el estado del optimizador
        # y el contador de epocas se recuperan del propio checkpoint.
        modelo.train(data=args.data, resume=True)
        return

    modelo.train(
        data=args.data,
        epochs=args.epochs,
        batch=args.batch,
        imgsz=args.imgsz,
        patience=args.patience,
        device=args.device,
        workers=args.workers,
        seed=args.seed,
        project=args.project,
        name=args.name,
        exist_ok=True,
        # train-9 dejo cos_lr en false y las perdidas de validacion se
        # estancaron: el decaimiento coseno las estabiliza.
        cos_lr=True,
        close_mosaic=10,
        optimizer="auto",
    )


if __name__ == "__main__":
    main()
