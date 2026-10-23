"""Exporta el detector a ONNX y mide el tiempo por cuadro en CPU (tarea 4.3).

Mide dos cosas sobre un cuadro de 640x480, en el mismo PC:
  - la inferencia sola (YOLO26s),
  - el ciclo completo del motor (inferencia, ByteTrack, reglas y difuminado),
que es lo que entra en el presupuesto de latencia del D2 (§2.4, ≤ 0,5 s).

    python "Fase 2/Evidencias Proyecto/Yolo/modelamiento/exportar_onnx.py" [--repeticiones 50]
"""

import argparse
import platform
import statistics
import time
from pathlib import Path

import cv2
from ultralytics import YOLO

from motor_cascovision import RUTA_MODELO_EPP, MonitorEPP

IMAGEN = Path(__file__).with_name("testeo.jpg")


def medir(funcion, repeticiones: int) -> dict:
    for _ in range(3):  # calentamiento
        funcion()
    tiempos = []
    for _ in range(repeticiones):
        inicio = time.perf_counter()
        funcion()
        tiempos.append((time.perf_counter() - inicio) * 1000)
    tiempos.sort()
    return {"media_ms": round(statistics.mean(tiempos), 1),
            "p95_ms": round(tiempos[int(0.95 * (len(tiempos) - 1))], 1)}


def main() -> None:
    opciones = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    opciones.add_argument("--repeticiones", type=int, default=50)
    args = opciones.parse_args()

    ruta_onnx = Path(YOLO(str(RUTA_MODELO_EPP)).export(format="onnx", imgsz=640, simplify=True))
    print(f"ONNX: {ruta_onnx} ({ruta_onnx.stat().st_size / 1e6:.1f} MB)")

    cuadro = cv2.resize(cv2.imread(str(IMAGEN)), (640, 480))
    print(f"CPU: {platform.processor() or platform.machine()} · {args.repeticiones} repeticiones")
    for ruta in (RUTA_MODELO_EPP, ruta_onnx):
        modelo = YOLO(str(ruta), task="detect")
        clases = sorted({modelo.names[int(c)] for c in modelo.predict(cuadro, verbose=False)[0].boxes.cls})
        inferencia = medir(lambda: modelo.predict(cuadro, verbose=False), args.repeticiones)
        motor = MonitorEPP(ruta_modelo=ruta, carpeta_evidencia=Path("edge-datos") / "incidents")
        ciclo = medir(lambda: motor.procesar(cuadro.copy()), args.repeticiones)
        print(f"{ruta.suffix}: inferencia {inferencia} · ciclo del motor {ciclo} · clases {clases}")


if __name__ == "__main__":
    main()
