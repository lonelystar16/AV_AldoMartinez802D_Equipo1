"""Agente Edge: analiza la cámara y reporta los incidentes a la API REST.

Reutiliza el mismo motor que `monitoreo_v2.py`. La diferencia es que aqui cada
infraccion confirmada viaja por HTTP directo a la API, con reintentos y cola
local, para no perder evidencia si la API no responde.

La API exige el token del agente Edge (variable EDGE_API_TOKEN): debe tener el
mismo valor en la terminal de la API y en la de este agente.

    python -m uvicorn app.main:app --app-dir src/api --reload
    python "Yolo/testing y modelamiento/monitoreo_api.py"
"""

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request
from collections import deque
from datetime import datetime
from pathlib import Path

import cv2

sys.path.insert(0, str(Path(__file__).resolve().parent))

from motor_cascovision import RAIZ, MonitorEPP  # noqa: E402

API_POR_DEFECTO = "http://localhost:8000"
COLA_INCIDENTES = RAIZ / "Fase 2" / "Evidencias Proyecto" / "db" / "cola_incidentes.jsonl"
RAIZ_EVIDENCIA = RAIZ / "Fase 2" / "Evidencias Proyecto" / "incidents"
TIMEOUT_S = 10
ESPERA_REINTENTO_S = 5
MAX_INTENTOS = 3
MAX_COLA = 500


class ReporteAPI:
    """Envia incidentes a la API, con reintentos y cola local en disco."""

    def __init__(self, url: str = API_POR_DEFECTO, archivo_cola: Path = COLA_INCIDENTES,
                 token: str | None = None):
        self.url = url.rstrip("/")
        self.token = token if token is not None else os.getenv("EDGE_API_TOKEN", "")
        self.archivo_cola = archivo_cola
        self.pendientes: deque = deque(self._leer_cola())
        self.disponible = True

    # ---------- cola ----------
    def _leer_cola(self) -> list[dict]:
        if not self.archivo_cola.is_file():
            return []
        salida = []
        for linea in self.archivo_cola.read_text(encoding="utf-8").splitlines():
            if linea.strip():
                try:
                    salida.append(json.loads(linea))
                except json.JSONDecodeError:
                    continue
        return salida[-MAX_COLA:]

    def _encolar(self, incidente: dict) -> None:
        self.pendientes.append(incidente)
        while len(self.pendientes) > MAX_COLA:
            self.pendientes.popleft()
        self.archivo_cola.parent.mkdir(parents=True, exist_ok=True)
        with self.archivo_cola.open("w", encoding="utf-8") as archivo:
            for pendiente in self.pendientes:
                archivo.write(json.dumps(pendiente, ensure_ascii=False) + "\n")

    # ---------- envio ----------
    def enviar(self, incidente: dict) -> bool:
        cuerpo = json.dumps({
            "camera_id": incidente["camera_id"],
            "zone_id": incidente["zone_id"],
            "detected_at": incidente["detected_at"],
            "violation_type": incidente["violation_type"],
            "confidence": incidente["confidence"],
            "evidence_path": incidente["evidence_path"],
            "face_blurred": incidente.get("face_blurred", False),
            "beacon_alert": incidente["beacon_alert"],
            "person_track_id": incidente.get("person_track_id"),
            "violation_types": incidente.get("violation_types"),
        }).encode("utf-8")

        cabeceras = {"Content-Type": "application/json"}
        if self.token:
            cabeceras["Authorization"] = f"Bearer {self.token}"
        peticion = urllib.request.Request(
            f"{self.url}/incidents", data=cuerpo, method="POST", headers=cabeceras,
        )
        for intento in range(MAX_INTENTOS):
            try:
                with urllib.request.urlopen(peticion, timeout=TIMEOUT_S) as respuesta:
                    if respuesta.status == 201:
                        self.disponible = True
                        return True
            except urllib.error.HTTPError as error:
                if error.code in (400, 401, 403, 422):
                    # El incidente es invalido o no autorizado: reintentar no sirve.
                    print(f"  API rechazo el incidente ({error.code}): {error.reason}")
                    self.disponible = True
                    return False
            except (urllib.error.URLError, OSError) as error:
                self.disponible = False
                if intento < MAX_INTENTOS - 1:
                    time.sleep(ESPERA_REINTENTO_S)
                else:
                    print(f"  API sin respuesta ({error}); se guarda en cola local.")
            except TimeoutError:
                self.disponible = False
                if intento < MAX_INTENTOS - 1:
                    time.sleep(ESPERA_REINTENTO_S)
        self._encolar(incidente)
        return False

    def vaciar_cola(self) -> int:
        """Reintenta enviar lo pendiente. Devuelve cuantos se enviaron."""
        enviados = 0
        pendientes = deque(self.pendientes)
        self.pendientes.clear()
        while pendientes:
            incidente = pendientes.popleft()
            if self.enviar(incidente):
                enviados += 1
            else:
                pendientes.appendleft(incidente)
                break
        if not pendientes:
            if self.archivo_cola.is_file():
                self.archivo_cola.unlink()
        return enviados


def main() -> None:
    analizador = argparse.ArgumentParser(description="Agente Edge de CascoVision")
    analizador.add_argument("--api", default=API_POR_DEFECTO,
                            help="URL base de la API REST")
    analizador.add_argument("--fuente", type=int, default=0,
                            help="Indice de la camara (0 por defecto)")
    argumentos = analizador.parse_args()

    reporte = ReporteAPI(argumentos.api)
    if not reporte.token:
        print("Aviso: EDGE_API_TOKEN no está definido; la API rechazará los incidentes (401/503).")
    monitor = MonitorEPP(carpeta_evidencia=RAIZ_EVIDENCIA,
                         al_registrar=reporte.enviar)

    cap = cv2.VideoCapture(argumentos.fuente)
    if not cap.isOpened():
        raise IOError("No se pudo abrir la fuente de video.")

    print("\n--- Agente Edge CascoVision ---")
    print(f"API:     {reporte.url}/incidents")
    print(f"Cola:    {reporte.archivo_cola}")
    print(f"Evidencia:{RAIZ_EVIDENCIA}")
    print("Presiona 'q' para finalizar.\n")

    try:
        while True:
            ok, frame = cap.read()
            if not ok:
                break
            incidentes = monitor.procesar(frame)
            for incidente in incidentes:
                marca = "OK" if reporte.disponible else "encolado"
                print(f"  -> {incidente['violation_types']} pid={incidente['person_track_id']} [{marca}]")
            if not reporte.disponible and not reporte.pendientes:
                enviados = reporte.vaciar_cola()
                if enviados:
                    print(f"  API recuperada: {enviados} incidentes enviados desde la cola.")
            cv2.imshow("Agente Edge CascoVision", frame)
            if cv2.waitKey(1) & 0xFF == ord("q"):
                break
    finally:
        cap.release()
        cv2.destroyAllWindows()
        if reporte.pendientes:
            print(f"\nQuedan {len(reporte.pendientes)} incidentes en la cola local.")


if __name__ == "__main__":
    main()
