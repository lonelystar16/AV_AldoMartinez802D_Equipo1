"""Cámara IP simulada: sirve un video por RTSP en H.264, como una cámara real.

ffmpeg codifica el video y lo manda por RTP a un socket local; este módulo
atiende el diálogo RTSP (OPTIONS, DESCRIBE, SETUP, PLAY, TEARDOWN) y reenvía
los paquetes intercalados en la conexión TCP del cliente.

shortcut: solo transporte TCP intercalado y sin autenticación; sirve para pruebas
y la demo. Para el entorno Docker se usa mediamtx (rtsp-sim, tarea 4.17).

Uso: python camara_rtsp_simulada.py video.mp4 [puerto]  →  rtsp://127.0.0.1:8554/camara
"""

import itertools
import re
import shutil
import socket
import socketserver
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path


class CamaraRTSP:
    def __init__(self, video: str, puerto: int = 8554, ruta: str = "camara"):
        self.video, self.puerto, self.ruta = str(video), puerto, ruta
        self.clientes: dict[socket.socket, threading.Lock] = {}
        self.sesiones = itertools.count(10_000_001)

    @property
    def url(self) -> str:
        return f"rtsp://127.0.0.1:{self.puerto}/{self.ruta}"

    def iniciar(self) -> "CamaraRTSP":
        if not shutil.which("ffmpeg"):
            raise RuntimeError("Se necesita ffmpeg en el PATH")
        # RTP en un puerto par y RTCP en el siguiente, como espera ffmpeg.
        self.rtp, self.rtcp = _par_udp()
        puerto_rtp = self.rtp.getsockname()[1]
        carpeta = Path(tempfile.mkdtemp(prefix="rtsp_sim_"))
        archivo_sdp = carpeta / "camara.sdp"
        self.ffmpeg = subprocess.Popen(
            ["ffmpeg", "-hide_banner", "-loglevel", "error", "-re", "-stream_loop", "-1",
             "-i", self.video, "-an", "-c:v", "libx264", "-preset", "ultrafast",
             "-tune", "zerolatency", "-pix_fmt", "yuv420p", "-g", "10",
             # SPS/PPS en el SDP y repetidos en cada cuadro clave, como una cámara real.
             "-flags", "+global_header", "-bsf:v", "dump_extra",
             "-f", "rtp", "-sdp_file", str(archivo_sdp),
             f"rtp://127.0.0.1:{puerto_rtp}?pkt_size=1200"],
            stdin=subprocess.DEVNULL)
        limite = time.monotonic() + 15
        while not (archivo_sdp.is_file() and "m=video" in archivo_sdp.read_text()):
            if self.ffmpeg.poll() is not None or time.monotonic() > limite:
                self.detener()
                raise RuntimeError("ffmpeg no generó el SDP del video")
            time.sleep(0.05)
        sdp = archivo_sdp.read_text()
        sdp = re.sub(r"c=IN IP4 \S+", "c=IN IP4 0.0.0.0", sdp)
        sdp = re.sub(r"m=video \d+", "m=video 0", sdp)
        self.sdp = sdp.strip().replace("\n", "\r\n") + "\r\na=control:trackID=0\r\n"

        threading.Thread(target=self._reenviar, daemon=True).start()
        camara = self

        class Manejador(socketserver.StreamRequestHandler):
            def handle(self):
                camara._atender(self.connection, self.rfile)

        socketserver.ThreadingTCPServer.allow_reuse_address = True
        self.servidor = socketserver.ThreadingTCPServer(("127.0.0.1", self.puerto), Manejador)
        self.servidor.daemon_threads = True
        self.puerto = self.servidor.server_address[1]  # por si se pidió el puerto 0
        threading.Thread(target=self.servidor.serve_forever, daemon=True).start()
        return self

    def detener(self) -> None:
        if getattr(self, "servidor", None):
            self.servidor.shutdown()
            self.servidor.server_close()
        for conexion in list(self.clientes):
            try:  # shutdown y no close: el lector del manejador aún tiene el socket abierto
                conexion.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
        self.clientes.clear()
        if getattr(self, "ffmpeg", None):
            self.ffmpeg.kill()
            self.ffmpeg.wait()
        for s in (getattr(self, "rtp", None), getattr(self, "rtcp", None)):
            if s:
                s.close()

    def __enter__(self):
        return self.iniciar()

    def __exit__(self, *_):
        self.detener()

    # ---------- RTP: de ffmpeg a cada cliente en PLAY ----------

    def _reenviar(self) -> None:
        while True:
            try:
                paquete = self.rtp.recv(65536)
            except OSError:
                return  # socket cerrado al detener
            trama = b"$\x00" + len(paquete).to_bytes(2, "big") + paquete
            for conexion, candado in list(self.clientes.items()):
                try:
                    with candado:
                        conexion.sendall(trama)
                except OSError:
                    self.clientes.pop(conexion, None)

    # ---------- RTSP ----------

    def _atender(self, conexion: socket.socket, entrada) -> None:
        candado = threading.Lock()
        sesion = str(next(self.sesiones))
        try:
            while True:
                primero = entrada.read(1)
                if not primero:
                    return
                if primero == b"$":  # RTCP intercalado del cliente: se descarta
                    cabecera = entrada.read(3)
                    entrada.read(int.from_bytes(cabecera[1:3], "big"))
                    continue
                lineas = [(primero + entrada.readline()).decode("latin-1").strip()]
                while (linea := entrada.readline().decode("latin-1").strip()):
                    lineas.append(linea)
                metodo, url = lineas[0].split()[:2]
                cabeceras = {k.strip().lower(): v.strip()
                             for k, _, v in (l.partition(":") for l in lineas[1:])}
                cseq = cabeceras.get("cseq", "0")
                if int(cabeceras.get("content-length", 0)):
                    entrada.read(int(cabeceras["content-length"]))

                extra, cuerpo, codigo = {}, "", "200 OK"
                if metodo == "OPTIONS":
                    extra["Public"] = "OPTIONS, DESCRIBE, SETUP, PLAY, TEARDOWN, GET_PARAMETER"
                elif metodo == "DESCRIBE":
                    if not url.rstrip("/").endswith("/" + self.ruta):
                        codigo = "404 Not Found"
                    else:
                        extra["Content-Base"] = url.rstrip("/") + "/"
                        extra["Content-Type"] = "application/sdp"
                        cuerpo = self.sdp
                elif metodo == "SETUP":
                    if "TCP" not in cabeceras.get("transport", ""):
                        codigo = "461 Unsupported Transport"
                    else:
                        extra["Transport"] = "RTP/AVP/TCP;unicast;interleaved=0-1"
                        extra["Session"] = sesion + ";timeout=60"
                elif metodo == "PLAY":
                    extra["Session"] = sesion
                    extra["Range"] = "npt=0.000-"
                elif metodo == "TEARDOWN":
                    self.clientes.pop(conexion, None)
                elif metodo != "GET_PARAMETER":
                    codigo = "405 Method Not Allowed"

                respuesta = f"RTSP/1.0 {codigo}\r\nCSeq: {cseq}\r\n"
                respuesta += "".join(f"{k}: {v}\r\n" for k, v in extra.items())
                respuesta += f"Content-Length: {len(cuerpo)}\r\n\r\n{cuerpo}"
                with candado:
                    conexion.sendall(respuesta.encode("latin-1"))
                if metodo == "PLAY" and codigo.startswith("200"):
                    self.clientes[conexion] = candado
                if metodo == "TEARDOWN":
                    return
        except (OSError, ValueError):
            return
        finally:
            self.clientes.pop(conexion, None)


def _par_udp() -> tuple[socket.socket, socket.socket]:
    for _ in range(50):
        rtp = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        rtp.bind(("127.0.0.1", 0))
        puerto = rtp.getsockname()[1]
        if puerto % 2 == 0:
            rtcp = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            try:
                rtcp.bind(("127.0.0.1", puerto + 1))
                return rtp, rtcp
            except OSError:
                rtcp.close()
        rtp.close()
    raise RuntimeError("No se encontró un par de puertos UDP libre")


if __name__ == "__main__":
    camara = CamaraRTSP(sys.argv[1], int(sys.argv[2]) if len(sys.argv) > 2 else 8554).iniciar()
    print(f"Cámara simulada en {camara.url} (Ctrl+C para detener)")
    try:
        while camara.ffmpeg.poll() is None:
            time.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        camara.detener()
