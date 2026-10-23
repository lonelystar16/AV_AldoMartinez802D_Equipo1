"""Prueba del agente Edge contra una cámara IP simulada por RTSP (tarea 4.4).

Necesita ffmpeg con libx264 en el PATH; sin ffmpeg, la prueba se omite.
"""

import shutil
import socket
import subprocess
import sys
import time
from pathlib import Path

import pytest

cv2 = pytest.importorskip("cv2")
if not shutil.which("ffmpeg"):
    pytest.skip("ffmpeg no está instalado", allow_module_level=True)

sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).parents[1] / "src" / "edge"))

import agente  # noqa: E402
from camara_rtsp_simulada import CamaraRTSP  # noqa: E402


@pytest.fixture(scope="module")
def video(tmp_path_factory):
    ruta = tmp_path_factory.mktemp("rtsp") / "patron.mp4"
    subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-f", "lavfi",
                    "-i", "testsrc=size=320x240:rate=10", "-t", "3", "-pix_fmt", "yuv420p",
                    str(ruta)], check=True)
    return ruta


def puerto_libre() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def leer(cap, segundos: float = 3.0) -> int:
    """Lee como el agente en vivo (grab continuo) y cuenta los cuadros."""
    n, limite = 0, time.monotonic() + segundos
    while time.monotonic() < limite and cap.grab():
        n += 1
    return n


def test_agente_lee_la_camara_rtsp_en_vivo(video):
    with CamaraRTSP(video, puerto_libre()) as camara:
        cap = agente.abrir(camara.url)
        try:
            assert cap.isOpened()
            assert leer(cap) >= 10  # la cámara emite a 10 FPS
            ok, cuadro = cap.retrieve()
            assert ok and cuadro.shape == (240, 320, 3)
        finally:
            cap.release()


def test_agente_se_reconecta_cuando_vuelve_la_camara(video):
    puerto = puerto_libre()
    camara = CamaraRTSP(video, puerto).iniciar()
    cap = agente.abrir(camara.url)
    try:
        assert leer(cap, 1.5) > 0
        camara.detener()  # la cámara se cae
        inicio = time.monotonic()
        while cap.grab():  # vacía lo que quedó en el búfer
            assert time.monotonic() - inicio < 10, "grab() no detectó la caída"
        cap.release()  # aquí el agente imprime «Cámara sin señal» y reabre

        camara = CamaraRTSP(video, puerto).iniciar()  # vuelve en la misma URL
        cap = agente.abrir(camara.url)  # lo mismo que hace el bucle del agente
        assert cap.isOpened() and leer(cap) > 0
    finally:
        cap.release()
        camara.detener()
