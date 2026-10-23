"""Difuminado cuando la caja de 'Person' no incluye la cabeza (RF-06, tarea 4.5)."""

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parents[1] / "Yolo" / "modelamiento"))

import motor_cascovision as mc  # noqa: E402



class SinRostros:
    """YuNet que no encuentra caras: obliga a usar la caja de cabeza."""

    def getInputSize(self):
        return (0, 0)

    def setInputSize(self, tamano):
        pass

    def detect(self, imagen):
        return None, None


def test_cara_sobre_la_caja_de_la_persona_igual_se_difumina() -> None:
    """La caja de 'Person' empieza en los hombros y la cabeza queda encima."""
    rng = np.random.default_rng(3)
    frame = rng.integers(0, 255, (300, 300, 3), dtype=np.uint8)
    original = frame.copy()
    cabeza = {"nombre": "helmet", "caja": (120, 10, 180, 80), "conf": 0.6, "id": 9}

    n = mc.difumar_rostros(SinRostros(), frame, (90, 80, 210, 290), [cabeza])

    assert n == 1
    assert not np.array_equal(frame[10:80, 120:180], original[10:80, 120:180])
