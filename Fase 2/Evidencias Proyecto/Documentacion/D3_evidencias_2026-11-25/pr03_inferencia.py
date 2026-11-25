"""PR-03 del D3: tiempo de inferencia del modelo entregado en CPU, 500 cuadros.

Uso: python pr03_inferencia.py <modelo.onnx> <video.mp4>
Criterio: <= 0,5 s por cuadro (presupuesto del D2 §2.4).
"""
import statistics
import sys
import time

import cv2
from ultralytics import YOLO

modelo, video = sys.argv[1], sys.argv[2]
N = 500
cap = cv2.VideoCapture(video)
cuadros = []
while len(cuadros) < N:
    ok, f = cap.read()
    if not ok:  # el video es más corto: se repite, como hace rtsp-sim
        cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
        continue
    cuadros.append(f)
cap.release()

m = YOLO(modelo, task="detect")
for f in cuadros[:10]:  # calentamiento, no se mide
    m.predict(f, device="cpu", verbose=False)

t = []
for f in cuadros:
    a = time.perf_counter()
    m.predict(f, device="cpu", verbose=False)
    t.append(time.perf_counter() - a)

t.sort()
p95 = t[int(0.95 * len(t)) - 1]
print(f"cuadros={len(t)} media={statistics.mean(t)*1000:.1f} ms mediana={statistics.median(t)*1000:.1f} ms "
      f"p95={p95*1000:.1f} ms max={t[-1]*1000:.1f} ms")
print("PR-03", "APROBADO" if p95 <= 0.5 else "NO APROBADO")
