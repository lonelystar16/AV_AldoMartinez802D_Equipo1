"""Agente Edge de CascoVision, limitado a zonas de riesgo.

Misma base que `monitoreo_api.py`: el mismo motor, la misma API, la misma cola
local y los mismos reintentos. La diferencia es el filtro: solo se abre registro
de quien está dentro de una zona de riesgo configurada. Quien pasa por fuera no
genera ni estado ni incidente, porque la idea no es estar mirando todo el
encuadre, sino lo que ocurre donde de verdad hay riesgo.

Un episodio queda anclado a la zona donde nació. Si la persona sale de ella,
el registro no se cierra en el acto: pasa a espera durante
GRACIA_CIERRE_SEGUNDOS (15 s), y si vuelve a la misma zona a tiempo se retoma
con el mismo episode_id, sin un INICIO nuevo. Si no vuelve, se cierra con FIN.

Las zonas viven en `Fase 2/Evidencias Proyecto/config/zonas.json`, en
coordenadas relativas al frame (0..1) para que sirvan en cualquier resolución.
Si el archivo no existe, cópialo desde `zonas.json.example` y edita los polígonos
reales de cada cámara. Ver `zonas.py`.

    python "Yolo/modelamiento/monitoreo_sector.py" --camera-id camara-01
"""

import argparse
import sys
from pathlib import Path

import cv2

sys.path.insert(0, str(Path(__file__).resolve().parent))

from monitoreo_api import API_POR_DEFECTO, RAIZ_EVIDENCIA, ReporteAPI  # noqa: E402
from motor_cascovision import RAIZ, PING_SEGUNDOS, MonitorEPP  # noqa: E402
from zonas import ErrorZonas, cargar_zonas, comprobar_solapes  # noqa: E402

RUTA_ZONAS = RAIZ / "Fase 2" / "Evidencias Proyecto" / "config" / "zonas.json"
CAMARA_POR_DEFECTO = "camara-01"


def main() -> None:
    analizador = argparse.ArgumentParser(
        description="Agente Edge de CascoVision por zonas de riesgo")
    analizador.add_argument("--api", default=API_POR_DEFECTO,
                            help="URL base de la API REST")
    analizador.add_argument("--zonas", default=str(RUTA_ZONAS),
                            help=f"Ruta del JSON de zonas ({RUTA_ZONAS})")
    analizador.add_argument("--camera-id", default=CAMARA_POR_DEFECTO,
                            help=f"Id de la camara en el JSON de zonas "
                                 f"({CAMARA_POR_DEFECTO} por defecto)")
    analizador.add_argument("--fuente", type=int, default=0,
                            help="Indice de la camara (0 por defecto)")
    analizador.add_argument("--ping", type=int, default=PING_SEGUNDOS,
                            help=f"Segundos entre avisos de una persona que sigue "
                                 f"sin EPP ({PING_SEGUNDOS} por defecto). 0 desactiva el ping")
    argumentos = analizador.parse_args()

    # Sin zonas validas no se arranca: un agente que nunca avisa porque su
    # configuración no se entendió es peor que uno caído, porque nadie se entera.
    ruta_zonas = Path(argumentos.zonas)
    try:
        config = cargar_zonas(ruta_zonas)
    except ErrorZonas as error:
        raise SystemExit(f"Zonas: {error}")

    if argumentos.camera_id not in config:
        disponibles = ", ".join(sorted(config)) or "(ninguna)"
        raise SystemExit(
            f"Zonas: la cámara '{argumentos.camera_id}' no tiene zonas en "
            f"{ruta_zonas}. Cámaras disponibles: {disponibles}")

    zonas = config[argumentos.camera_id]
    # Un solape no detiene nada, pero conviene saberlo: quien pise las dos
    # zonas siempre cae en la que aparece antes en la lista.
    for aviso in comprobar_solapes(zonas):
        print(f"Aviso: {aviso}")

    reporte = ReporteAPI(argumentos.api)
    if not reporte.token:
        print("Aviso: EDGE_API_TOKEN no está definido; la API rechazará los incidentes (401/503).")
    monitor = MonitorEPP(carpeta_evidencia=RAIZ_EVIDENCIA,
                         al_registrar=reporte.enviar,
                         ping_segundos=argumentos.ping,
                         camera_id=argumentos.camera_id,
                         zonas=zonas)

    cap = cv2.VideoCapture(argumentos.fuente)
    if not cap.isOpened():
        raise IOError("No se pudo abrir la fuente de video.")

    print("\n--- Agente Edge CascoVision (zonas) ---")
    print(f"API:     {reporte.url}/incidents")
    print(f"Cámara:  {argumentos.camera_id}")
    print(f"Cola:    {reporte.archivo_cola}")
    print(f"Evidencia:{RAIZ_EVIDENCIA}")
    print(f"Zonas vigiladas: {', '.join(z['id'] for z in zonas)}")
    print("Solo se reporta dentro de esas zonas; fuera de ellas no se abre registro.")
    print("El rostro se difumina igual en todo el frame, esté o no en zona.")
    print("INICIO: aviso inmediato al ver a alguien sin EPP dentro de una zona.")
    if argumentos.ping > 0:
        print(f"PING:   si sigue sin cambios, se reavisa cada {argumentos.ping} s "
              "(actualiza el mismo registro en la API).")
    else:
        print("PING:   desactivado (0 s).")
    print("FIN:    aviso al cumplir, o al llevar 15 s fuera de su zona.")
    print("Presiona 'q' para finalizar.\n")

    try:
        while True:
            ok, frame = cap.read()
            if not ok:
                break
            incidentes = monitor.procesar(frame)
            for incidente in incidentes:
                marca = "OK" if reporte.disponible else "encolado"
                evento = incidente.get("event", "inicio")
                print(f"  -> {evento.upper()} {incidente['violation_types']} "
                      f"pid={incidente['person_track_id']} "
                      f"[{incidente['zone_id']}] [{marca}]")
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
