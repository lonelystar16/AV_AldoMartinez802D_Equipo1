"""Monitoreo de EPP en la cámara local, sin API.

Analiza el video de la cámara, difumina los rostros y guarda evidencia de cada
infracción confirmada en `incidents/`. Para reportar a la API REST usa
`monitoreo_api.py`, que reutiliza el mismo motor.
"""

import cv2

from motor_cascovision import RAIZ, RUTA_MODELO_EPP, MonitorEPP

FUENTE_VIDEO = 0
VENTANA = "Monitoreo CascoVision en Tiempo Real"


def main() -> None:
    monitor = MonitorEPP(carpeta_evidencia=RAIZ / "Fase 2" / "Evidencias Proyecto" / "incidents")
    cap = cv2.VideoCapture(FUENTE_VIDEO)
    if not cap.isOpened():
        raise IOError("No se pudo abrir la fuente de video.")

    print("\n--- Monitoreo CascoVision Iniciado ---")
    print(f"Modelo:  {RUTA_MODELO_EPP}")
    print("Enfocado estrictamente en CASCO y CHALECO.")
    print(f"Suavizado: alerta tras {2} de {5} frames.")
    print(f"Evidencia: {monitor.carpeta_evidencia}")
    print("Presiona 'q' en la ventana de video para finalizar.\n")

    try:
        while True:
            ok, frame = cap.read()
            if not ok:
                break
            monitor.procesar(frame)
            cv2.imshow(VENTANA, frame)
            if cv2.waitKey(1) & 0xFF == ord("q"):
                break
    finally:
        cap.release()
        cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
