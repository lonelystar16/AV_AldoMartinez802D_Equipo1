"""PS-07 del D3: ninguna evidencia guardada debe tener un rostro detectable.

Uso: python ps07_rostros.py <yunet.onnx> <carpeta_evidencias> <video_original>
Control: el mismo detector sobre cuadros del video original (sin difuminar) muestra
que los rostros de ese video sí son detectables; si no lo fueran, la prueba no
diría nada.
"""
import sys
from pathlib import Path

import cv2

modelo, carpeta, video = sys.argv[1], Path(sys.argv[2]), sys.argv[3]
UMBRAL = 0.6


def rostros(img):
    h, w = img.shape[:2]
    det = cv2.FaceDetectorYN.create(modelo, "", (w, h), UMBRAL)
    _, caras = det.detect(img)
    return 0 if caras is None else len(caras)


evid = sorted(p for p in carpeta.rglob("*") if p.suffix.lower() in (".jpg", ".jpeg", ".png"))
con_rostro = [p.name for p in evid if rostros(cv2.imread(str(p))) > 0]

cap = cv2.VideoCapture(video)
n = control = 0
while True:
    ok, f = cap.read()
    if not ok:
        break
    n += 1
    if n % 10 == 0 and rostros(f) > 0:
        control += 1
cap.release()

print(f"evidencias revisadas={len(evid)} con rostro detectable={len(con_rostro)} {con_rostro[:5]}")
print(f"control: cuadros originales muestreados={n // 10} con rostro detectable={control}")
print("PS-07", "APROBADO" if evid and not con_rostro else "NO APROBADO / SIN MUESTRA")
