"""Agente Edge de CascoVision (tarea 4.4).

Lee una cámara (RTSP, archivo de video o índice de webcam) a 1 cuadro por
segundo y detecta la falta de EPP con el motor YOLO26 + ByteTrack. Solo avisa
de las personas que están dentro de la zona de riesgo de la cámara. Activa la
baliza zonal según `docs/PROTOCOLO_BALIZA.md` e informa a la API en segundo
plano, con una cola en disco por si la API no responde.

    $env:EDGE_API_TOKEN = "<token de la API>"
    $env:BALIZA_TOKEN = "<token de la baliza>"
    python "Fase 2/Evidencias Proyecto/src/edge/agente.py" --config config.json
"""

import argparse
import json
import os
import queue
import sys
import threading
import time
import urllib.error
import urllib.request
import uuid
from datetime import datetime, timezone
from pathlib import Path

import cv2
import numpy as np

PROYECTO = Path(__file__).resolve().parents[2]  # Fase 2/Evidencias Proyecto
# shortcut: el motor sigue en Yolo/modelamiento para no chocar con el trabajo
# en curso en esa carpeta; moverlo a src/edge al armar la imagen Docker (4.17).
sys.path.insert(0, str(PROYECTO / "Yolo" / "modelamiento"))

from monitoreo_api import ReporteAPI  # noqa: E402
from motor_cascovision import PING_SEGUNDOS, MonitorEPP  # noqa: E402

CONFIG_EJEMPLO = Path(__file__).with_name("config.example.json")


class Zona:
    """Polígono de la zona de riesgo, en coordenadas relativas (0 a 1)."""

    def __init__(self, puntos=None):
        self.puntos = np.array(puntos or [[0, 0], [1, 0], [1, 1], [0, 1]], dtype=np.float32)

    def contiene(self, caja, ancho, alto) -> bool:
        # Cuenta el punto de los pies: la persona está en la zona si pisa dentro.
        x1, _, x2, y2 = caja
        punto = (float((x1 + x2) / 2 / ancho), float(y2 / alto))
        return cv2.pointPolygonTest(self.puntos, punto, False) >= 0

    def dibujar(self, frame) -> None:
        alto, ancho = frame.shape[:2]
        contorno = (self.puntos * [ancho, alto]).astype(np.int32)
        cv2.polylines(frame, [contorno], True, (0, 165, 255), 2)


class MonitorZonal(MonitorEPP):
    """El motor de EPP, limitado a la zona de riesgo de la cámara (RF-04)."""

    def __init__(self, zona: Zona, **opciones):
        super().__init__(**opciones)
        self.zona = zona
        self.tamano = (1, 1)

    def procesar(self, frame):
        self.tamano = (frame.shape[1], frame.shape[0])
        incidentes = super().procesar(frame)
        self.zona.dibujar(frame)
        return incidentes

    def _registrar_cambio(self, pid, estado, confianza, nuevos, caja=None):
        if caja is not None and not self.zona.contiene(caja, *self.tamano):
            estado = frozenset()  # fuera de la zona no hay nada que avisar
        return super()._registrar_cambio(pid, estado, confianza, nuevos, caja)


class ClienteBaliza:
    """Cliente del protocolo de la baliza: `POST /alert` y `GET /health`."""

    ESPERA_S = 1.5
    FALLOS_FUERA_DE_LINEA = 3

    def __init__(self, url: str, token: str, zona_id: str, zona_nombre: str,
                 duracion_s: int = 10):
        self.url = (url or "").rstrip("/")
        self.token = token
        self.zona_id = zona_id
        self.zona_nombre = zona_nombre[:20]
        self.duracion_s = duracion_s
        self.en_linea = bool(self.url)
        self.fallos = 0

    def _pedir(self, metodo: str, ruta: str, cuerpo: dict | None = None) -> dict:
        datos = json.dumps(cuerpo).encode("utf-8") if cuerpo is not None else None
        cabeceras = {"Content-Type": "application/json"}
        if cuerpo is not None:
            cabeceras["Authorization"] = f"Bearer {self.token}"
        peticion = urllib.request.Request(self.url + ruta, data=datos, method=metodo,
                                          headers=cabeceras)
        with urllib.request.urlopen(peticion, timeout=self.ESPERA_S) as respuesta:
            return json.loads(respuesta.read() or b"{}")

    def alertar(self, violaciones: list[str]) -> dict:
        """Ordena la alerta y devuelve el `beacon_alert` que se informa a la API."""
        if not self.en_linea:
            return {"status": "skipped_offline", "latency_ms": None}
        orden = {
            "alert_id": str(uuid.uuid4()),  # el reintento usa el mismo id
            "zone_id": self.zona_id,
            "zone_name": self.zona_nombre,
            "violations": violaciones,
            "duration_s": self.duracion_s,
            "sound": "siren",
            "sent_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        }
        inicio = time.perf_counter()
        for _ in range(2):  # un intento y un reintento: 3 s como máximo (RNF-02)
            try:
                self._pedir("POST", "/alert", orden)
                return {"status": "alerted",
                        "latency_ms": round((time.perf_counter() - inicio) * 1000)}
            except urllib.error.HTTPError as error:
                # 400, 401, 409 o 413: es un error de configuración, reintentar no sirve.
                print(f"  Baliza rechazó la orden ({error.code}): revisar token o zona.")
                return {"status": "failed", "latency_ms": None}
            except OSError:  # incluye URLError y el tiempo de espera agotado
                continue
        return {"status": "failed", "latency_ms": None}

    def revisar(self) -> bool:
        """Heartbeat. Devuelve True si la baliza cambió de estado."""
        if not self.url:
            return False
        antes = self.en_linea
        try:
            self._pedir("GET", "/health")
            self.fallos, self.en_linea = 0, True
        except OSError:
            self.fallos += 1
            if self.fallos >= self.FALLOS_FUERA_DE_LINEA:
                self.en_linea = False
        return self.en_linea != antes


class ReporteAsincrono:
    """Envía a la API desde otro hilo: una API lenta no frena el análisis (AD-04)."""

    def __init__(self, reporte: ReporteAPI):
        self.reporte = reporte
        self.cola: queue.Queue = queue.Queue()
        threading.Thread(target=self._trabajar, daemon=True).start()

    def enviar(self, incidente: dict) -> None:
        self.cola.put(dict(incidente))

    def _trabajar(self) -> None:
        while True:
            try:
                incidente = self.cola.get(timeout=10)
            except queue.Empty:
                if self.reporte.pendientes:
                    self.reporte.vaciar_cola()
                continue
            if self.reporte.enviar(incidente) and self.reporte.pendientes:
                self.reporte.vaciar_cola()
            self.cola.task_done()

    def esperar(self, segundos: float = 15) -> None:
        """Da tiempo a enviar lo último; lo que falte ya quedó en la cola en disco."""
        limite = time.monotonic() + segundos
        while self.cola.unfinished_tasks and time.monotonic() < limite:
            time.sleep(0.2)


def abrir(fuente: str):
    return cv2.VideoCapture(int(fuente) if fuente.isdigit() else fuente)


def guardar_cuadro(frame, carpeta: Path) -> None:
    """Deja el último cuadro (ya difuminado) para la vista en vivo del monitor."""
    carpeta.mkdir(parents=True, exist_ok=True)
    temporal = carpeta / "ultimo_cuadro.tmp.jpg"
    cv2.imwrite(str(temporal), frame)
    try:
        os.replace(temporal, carpeta / "ultimo_cuadro.jpg")
    except OSError:
        pass  # el monitor lo está leyendo; se reemplaza en el próximo cuadro


def main() -> None:
    opciones = argparse.ArgumentParser(description="Agente Edge de CascoVision")
    opciones.add_argument("--config", type=Path, default=CONFIG_EJEMPLO)
    opciones.add_argument("--fuente", help="URL RTSP, archivo de video o índice de cámara")
    opciones.add_argument("--fps", type=float, default=1.0, help="Cuadros analizados por segundo")
    opciones.add_argument("--modelo", type=Path, help="Modelo .pt u .onnx (por defecto, el del repo)")
    opciones.add_argument("--ping", type=int, default=PING_SEGUNDOS,
                          help="Segundos entre avisos de quien sigue sin EPP")
    opciones.add_argument("--bucle", action="store_true", help="Repite el archivo de video al terminar")
    opciones.add_argument("--sin-ventana", action="store_true", help="No abre la ventana de video")
    args = opciones.parse_args()

    cfg = json.loads(args.config.read_text(encoding="utf-8"))
    # La URL de la cámara puede traer credenciales: mejor por variable de entorno.
    fuente = str(args.fuente or os.getenv("CAMARA_FUENTE") or cfg["fuente"])
    datos = PROYECTO / cfg.get("carpeta_datos", "edge-datos")
    # shortcut: la configuración sale de un JSON local; pasa a GET /edge/config cuando exista (4.15).
    baliza = ClienteBaliza(cfg["baliza"]["url"], os.getenv("BALIZA_TOKEN", ""),
                           cfg["zone_id"], cfg["zone_name"], cfg["baliza"].get("duracion_s", 10))
    reporte = ReporteAsincrono(ReporteAPI(cfg["api"], archivo_cola=datos / "cola_incidentes.jsonl"))
    if not reporte.reporte.token:
        print("Aviso: EDGE_API_TOKEN no está definido; la API rechazará los incidentes.")

    def al_registrar(incidente: dict) -> None:
        if incidente["event"] in ("inicio", "ping"):
            incidente["beacon_alert"] = baliza.alertar(incidente["violation_types"])
        incidente["camera_id"], incidente["zone_id"] = cfg["camera_id"], cfg["zone_id"]
        reporte.enviar(incidente)
        b = incidente["beacon_alert"]
        print(f"  -> {incidente['event'].upper()} {incidente['violation_types']} "
              f"persona {incidente['person_track_id']} · baliza {b['status']}"
              + (f" en {b['latency_ms']} ms" if b["latency_ms"] is not None else ""))

    monitor = MonitorZonal(Zona(cfg.get("poligono")), ruta_modelo=args.modelo,
                           carpeta_evidencia=PROYECTO / "incidents",
                           al_registrar=al_registrar, ping_segundos=args.ping)

    cap = abrir(fuente)
    if not cap.isOpened():
        raise IOError(f"No se pudo abrir la fuente de video: {fuente}")
    es_archivo = Path(fuente).is_file()
    periodo = 1.0 / args.fps
    paso = max(1, round((cap.get(cv2.CAP_PROP_FPS) or 30) / args.fps)) if es_archivo else 1
    print(f"Agente Edge · cámara {cfg['camera_id']} · zona {cfg['zone_id']} · {args.fps:g} FPS")
    print(f"Fuente: {'archivo' if es_archivo else 'en vivo'} · API {cfg['api']} · baliza {baliza.url or 'sin configurar'}")

    n, ultimo, ultimo_latido = 0, 0.0, float("-inf")
    try:
        while True:
            if not cap.grab():
                if es_archivo and args.bucle:
                    cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                    continue
                if es_archivo:
                    break
                print("Cámara sin señal; se reconecta en 2 s.")
                cap.release()
                time.sleep(2)
                cap = abrir(fuente)
                continue
            n += 1
            ahora = time.monotonic()
            # En vivo se lee todo (el búfer no se atrasa) y se analiza 1 cuadro por período.
            if (es_archivo and n % paso) or (not es_archivo and ahora - ultimo < periodo):
                continue
            ultimo = ahora
            ok, frame = cap.retrieve()
            if not ok:
                continue

            if ahora - ultimo_latido >= 30:  # heartbeat de la baliza (RNF-14)
                ultimo_latido = ahora
                if baliza.revisar():
                    print(f"  Baliza {'en línea' if baliza.en_linea else 'FUERA DE LÍNEA'}")

            monitor.procesar(frame)
            guardar_cuadro(frame, datos)
            if not args.sin_ventana:
                cv2.imshow("Agente Edge CascoVision", frame)
                if cv2.waitKey(1) & 0xFF == ord("q"):
                    break
            if es_archivo:
                time.sleep(periodo)  # el archivo avanza al ritmo de una cámara
    finally:
        cap.release()
        cv2.destroyAllWindows()
        reporte.esperar()
        if reporte.reporte.pendientes:
            print(f"Quedan {len(reporte.reporte.pendientes)} incidentes en la cola local.")


if __name__ == "__main__":
    main()
