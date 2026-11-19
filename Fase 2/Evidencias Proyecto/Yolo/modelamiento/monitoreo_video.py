"""Monitoreo de EPP desde una camara, un archivo o un enlace remoto.

Mismo motor, misma API y misma evidencia que `monitoreo_api.py`: cada
infraccion confirmada guarda su captura con los rostros difuminados en
`incidents/AAAA/MM/DD/` y la reporta por `evidence_path`, de modo que el
dashboard la sirve por `GET /incidents/{id}/evidence`, igual que con el agente
Edge real. Nada de eso cambia respecto de los otros scripts.

Lo que cambia es la fuente. Ademas de la camara y de un archivo local, acepta
una URL directa de video (mp4, m3u8, rtsp), que OpenCV abre tal cual, y
cualquier otra URL de pagina (YouTube y demas), que yt-dlp resuelve al stream
sin descargar el video. Si OpenCV no puede leer el stream resuelto --los
fragmentados de YouTube--, se baja el archivo a un temporal y se procesa ese.

La meta de 30 FPS se mide sobre `MonitorEPP.procesar()`, no sobre el pintado
de la ventana: ver `rendimiento.py`.

    python "Yolo/modelamiento/monitoreo_video.py" video.mp4
    python "Yolo/modelamiento/monitoreo_video.py" "https://ejemplo.com/a.mp4"
    python "Yolo/modelamiento/monitoreo_video.py" "https://youtube.com/watch?v=..."
    python "Yolo/modelamiento/monitoreo_video.py" --sin-api 0
"""

from __future__ import annotations

import argparse
import shutil
import sys
import tempfile
import time
from pathlib import Path
from urllib.parse import urlparse

import cv2

sys.path.insert(0, str(Path(__file__).resolve().parent))

from monitoreo_api import API_POR_DEFECTO, RAIZ_EVIDENCIA, ReporteAPI  # noqa: E402
from motor_cascovision import (  # noqa: E402
    CAMARA_POR_DEFECTO,
    PING_SEGUNDOS,
    RAIZ,
    RUTA_MODELO_EPP,
    MonitorEPP,
)
from rendimiento import (  # noqa: E402
    FPS_OBJETIVO,
    OPCIONES_MODELO,
    MedidorFPS,
    dibujar_hud,
    resolver_modelo,
)
from zonas import ErrorZonas, cargar_zonas, comprobar_solapes  # noqa: E402

VENTANA = "Monitoreo CascoVision desde video"

# Selector de formato de yt-dlp. Se pide solo video y nunca se mezcla con audio:
# para detectar EPP la pista de sonido no aporta y exigir la combinada obligaria
# a yt-dlp a pedir ffmpeg. Ademas un directo (`is_live`) publica el video y el
# audio por separado, de modo que un selector que exija ambos no encontraria
# nada y fallaria. Se limita a 720p para no arrastrar la meta de 30 FPS.
FORMATO_VIDEO = (
    "best[height<=720][ext=mp4]/best[height<=720]/best[ext=mp4]/"
    "bestvideo[height<=720]/bestvideo/best"
)

# Extensiones que OpenCV abre directamente desde una URL, sin pasar por yt-dlp.
EXTENSIONES_DIRECTAS = (
    ".mp4", ".m3u8", ".mkv", ".avi", ".mov", ".ts", ".flv", ".webm",
)
# Esquemas de stream en vivo: van tal cual a OpenCV y no se pueden descargar.
ESQUEMAS_EN_VIVO = ("rtsp://", "rtsps://", "rtmp://", "udp://", "srt://")

RUTA_ZONAS = RAIZ / "Fase 2" / "Evidencias Proyecto" / "config" / "zonas.json"


def _meta_fps(valor: str) -> float:
    """Valida la meta de FPS en el propio argparse, sin dejar que llegue a
    estallar dentro del medidor."""
    try:
        meta = float(valor)
    except ValueError:
        raise argparse.ArgumentTypeError(f"'{valor}' no es un numero")
    if meta <= 0:
        raise argparse.ArgumentTypeError(
            f"la meta de FPS debe ser mayor que cero, no {valor}")
    return meta


def _segundos(valor: str) -> float:
    """Valida `--segundos`: 0 significa sin limite, lo negativo no tiene sentido."""
    try:
        segundos = float(valor)
    except ValueError:
        raise argparse.ArgumentTypeError(f"'{valor}' no es un numero")
    if segundos < 0:
        raise argparse.ArgumentTypeError(f"no puede ser negativo: {valor}")
    return segundos


def es_url(texto: str) -> bool:
    """True si el texto trae esquema de red y no es una ruta de disco."""
    return urlparse(texto.strip()).scheme in {
        "http", "https", "rtsp", "rtsps", "rtmp", "udp", "srt",
    }


def es_url_directa(texto: str) -> bool:
    """True si OpenCV debe poder abrirla sin ayuda de yt-dlp.

    Los esquemas de stream en vivo siempre lo son. En http solo lo es si la
    ruta termina en una extension de video conocida: el resto de las URLs son
    paginas (YouTube, Vimeo, ...) y hay que resolverlas primero.
    """
    bajo = texto.strip().lower()
    if bajo.startswith(ESQUEMAS_EN_VIVO):
        return True
    if not bajo.startswith(("http://", "https://")):
        return False
    return urlparse(bajo).path.endswith(EXTENSIONES_DIRECTAS)


def _yt_dlp():
    """Importa yt-dlp solo cuando hace falta, con instrucciones si falta."""
    try:
        import yt_dlp
    except ImportError as error:
        raise SystemExit(
            "Ese enlace es una pagina de video y falta yt-dlp para resolverlo.\n"
            "Instalalo con:  uv sync --group dev --group yolo"
        ) from error
    return yt_dlp


def _opciones_yt_dlp(destino: Path | None = None) -> dict:
    """Opciones comunes para resolver y para descargar.

    `FORMATO_VIDEO` pide un solo archivo ya mezclado cuando existe, asi no se
    depende de ffmpeg, y cae al mejor video suelto cuando no, que es el caso de
    los directos.
    """
    opciones = {
        "format": FORMATO_VIDEO,
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
    }
    if destino is not None:
        opciones["outtmpl"] = str(destino / "video.%(ext)s")
    return opciones


def resolver_fuente(fuente: str) -> str:
    """Devuelve la URL del stream de una pagina, sin descargar el video.

    Una URL directa se pasa tal cual y no llega hasta aca.
    """
    yt_dlp = _yt_dlp()
    try:
        with yt_dlp.YoutubeDL(_opciones_yt_dlp()) as ydl:
            info = ydl.extract_info(fuente, download=False)
    except Exception as error:  # yt-dlp lanza sus propias excepciones
        raise SystemExit(f"yt-dlp no pudo resolver el enlace: {error}")

    # Un enlace de playlist devuelve la lista; con noplaylist deberia venir el
    # video suelto, pero se contempla por si el sitio no respeta la opcion.
    if isinstance(info, dict) and info.get("entries"):
        info = info["entries"][0]
    url = info.get("url") if isinstance(info, dict) else None
    if not url:
        raise SystemExit("yt-dlp resolvio el video pero no entrego una URL de stream.")

    visible = url.split("?")[0]
    print(f"Stream resuelto por yt-dlp: {visible[:110]}")
    return url


def descargar(fuente: str) -> Path:
    """Ultimo recurso: baja el video a un temporal y devuelve su ruta.

    OpenCV no siempre puede leer los streams fragmentados (DASH) que entrega
    YouTube. Cuando el stream resuelto no abre, se baja el archivo y se procesa
    ese; el stream en directo sigue siendo la via principal.
    """
    destino = Path(tempfile.mkdtemp(prefix="cascovision-video-"))
    yt_dlp = _yt_dlp()
    try:
        with yt_dlp.YoutubeDL(_opciones_yt_dlp(destino)) as ydl:
            ydl.download([fuente])
    except Exception as error:
        shutil.rmtree(destino, ignore_errors=True)
        raise SystemExit(f"yt-dlp no pudo descargar el video: {error}")

    candidatos = sorted(p for p in destino.glob("video.*") if p.is_file())
    if not candidatos:
        shutil.rmtree(destino, ignore_errors=True)
        raise SystemExit("yt-dlp termino sin dejar ningun archivo descargado.")
    return candidatos[0]


def abrir_fuente(fuente: str) -> tuple[cv2.VideoCapture, Path | None]:
    """Abre la fuente; devuelve la captura y el temporal, si hubo que bajar uno.

    El orden es deliberado: primero se intenta transmitir en directo. Solo se
    descarga cuando el stream resuelto no se puede abrir.
    """
    if fuente.isdigit():
        captura = cv2.VideoCapture(int(fuente))
        if not captura.isOpened():
            raise SystemExit(f"No se pudo abrir la camara {fuente}.")
        return captura, None

    ruta = Path(fuente)
    if ruta.is_file():
        captura = cv2.VideoCapture(str(ruta))
        if not captura.isOpened():
            raise SystemExit(f"No se pudo abrir el archivo {ruta}.")
        return captura, None

    if not es_url(fuente):
        raise SystemExit(
            f"No existe el archivo '{fuente}' y no parece una URL. "
            "Pasa una ruta local, un indice de camara o una URL.")

    resuelta = fuente if es_url_directa(fuente) else resolver_fuente(fuente)
    captura = cv2.VideoCapture(resuelta)
    if captura.isOpened():
        return captura, None

    # Un stream en vivo no tiene nada que descargar: ahi se rinde.
    if fuente.strip().lower().startswith(ESQUEMAS_EN_VIVO):
        raise SystemExit(f"No se pudo abrir el stream en vivo: {fuente}")

    print("OpenCV no pudo leer el stream; se descarga el video para procesarlo.")
    temporal = descargar(fuente)
    captura = cv2.VideoCapture(str(temporal))
    if not captura.isOpened():
        shutil.rmtree(temporal.parent, ignore_errors=True)
        raise SystemExit(f"No se pudo abrir el video descargado: {temporal}")
    return captura, temporal


def _cargar_zonas(ruta: Path, camera_id: str):
    """Carga las zonas de la camara indicada, o None si no se pidieron."""
    if ruta is None:
        return None
    try:
        config = cargar_zonas(ruta)
    except ErrorZonas as error:
        raise SystemExit(f"Zonas: {error}")
    if camera_id not in config:
        disponibles = ", ".join(sorted(config)) or "(ninguna)"
        raise SystemExit(
            f"Zonas: la camara '{camera_id}' no tiene zonas en {ruta}. "
            f"Camaras disponibles: {disponibles}")
    zonas = config[camera_id]
    # Un solape no detiene nada, pero conviene saberlo: quien pise las dos
    # zonas siempre cae en la que aparece antes en la lista.
    for aviso in comprobar_solapes(zonas):
        print(f"Aviso: {aviso}")
    return zonas


def main() -> None:
    analizador = argparse.ArgumentParser(
        description="Monitoreo de EPP desde una camara, un archivo o un enlace")
    analizador.add_argument("fuente", nargs="?", default="0",
                            help="Indice de camara (0 por defecto), ruta de un "
                                 "archivo de video o URL (directa o de pagina)")
    analizador.add_argument("--api", default=API_POR_DEFECTO,
                            help="URL base de la API REST")
    analizador.add_argument("--camera-id", default=CAMARA_POR_DEFECTO,
                            help=f"Id de la camara reportada ({CAMARA_POR_DEFECTO} "
                                 "por defecto)")
    analizador.add_argument("--fps", type=_meta_fps, default=FPS_OBJETIVO,
                            help=f"Meta de FPS del modelo ({FPS_OBJETIVO:.0f} por "
                                 "defecto)")
    analizador.add_argument("--modelo", choices=OPCIONES_MODELO, default="auto",
                            help="Modelo a cargar: 'auto' deja que el motor elija "
                                 "(prefiere el .onnx); 'pt' usa la GPU de PyTorch "
                                 "y es el que alcanza los 30 FPS sin CUDA en ONNX")
    analizador.add_argument("--ping", type=int, default=PING_SEGUNDOS,
                            help=f"Segundos entre avisos de una persona que sigue "
                                 f"sin EPP ({PING_SEGUNDOS} por defecto). "
                                 "0 desactiva el ping")
    analizador.add_argument("--zonas", default=None,
                            help=f"JSON de zonas para filtrar por zona de riesgo "
                                 f"(por defecto no se filtra; ejemplo {RUTA_ZONAS})")
    analizador.add_argument("--sin-api", action="store_true",
                            help="No reportar a la API: solo ventana y evidencia local")
    analizador.add_argument("--segundos", type=_segundos, default=0.0,
                            help="Detener pasados N segundos. Un directo no tiene "
                                 "fin, asi que sin limite el script no terminaria; "
                                 "0 lo desactiva (por defecto)")
    argumentos = analizador.parse_args()

    zonas = _cargar_zonas(Path(argumentos.zonas) if argumentos.zonas else None,
                          argumentos.camera_id)

    reporte: ReporteAPI | None = None
    if argumentos.sin_api:
        print("Aviso: --sin-api; los incidentes no se envian a la API.")
    else:
        reporte = ReporteAPI(argumentos.api)
        if not reporte.token:
            print("Aviso: EDGE_API_TOKEN no esta definido; "
                  "la API rechazara los incidentes (401/503).")

    ruta_modelo = resolver_modelo(argumentos.modelo)
    monitor = MonitorEPP(ruta_modelo=ruta_modelo,
                         carpeta_evidencia=RAIZ_EVIDENCIA,
                         al_registrar=reporte.enviar if reporte else None,
                         ping_segundos=argumentos.ping,
                         camera_id=argumentos.camera_id,
                         zonas=zonas)

    cap, temporal = abrir_fuente(argumentos.fuente)
    medidor = MedidorFPS(meta=argumentos.fps)

    print("\n--- Monitoreo CascoVision desde video ---")
    print(f"Fuente:  {argumentos.fuente}")
    print(f"Modelo:  {ruta_modelo or RUTA_MODELO_EPP}")
    print(f"API:     {'(desactivada)' if reporte is None else reporte.url + '/incidents'}")
    print(f"Camara:  {argumentos.camera_id}")
    print(f"Evidencia: {RAIZ_EVIDENCIA}")
    if zonas:
        print(f"Zonas vigiladas: {', '.join(z['id'] for z in zonas)}")
        print("Solo se reporta dentro de esas zonas; fuera de ellas no se abre registro.")
    else:
        print("Sin zonas configuradas: se vigila todo el encuadre.")
    print("Evidencia: rostros difuminados con YuNet antes de guardar.")
    print("INICIO: aviso inmediato al ver a alguien sin EPP.")
    if argumentos.ping > 0:
        print(f"PING:   si sigue sin cambios, se reavisa cada {argumentos.ping} s.")
    else:
        print("PING:   desactivado (0 s).")
    print("FIN:    aviso al cumplir, o al terminar el video.")
    print(f"Meta de rendimiento: {argumentos.fps:.0f} FPS.")
    if argumentos.segundos:
        print(f"Limite:  se detiene a los {argumentos.segundos:.0f} s.")
    print("Presiona 'q' para finalizar.\n")

    limite = time.perf_counter() + argumentos.segundos
    try:
        while True:
            # Un directo no tiene fin: sin este corte el script no terminaria.
            if argumentos.segundos and time.perf_counter() >= limite:
                print(f"\nLimite de {argumentos.segundos:.0f} s alcanzado.")
                break
            ok, frame = cap.read()
            if not ok:
                break
            t0 = time.perf_counter()
            incidentes = monitor.procesar(frame)
            # Solo se cronometra el modelo: el imshow y el waitKey no cuentan.
            medidor.registrar(time.perf_counter() - t0)

            for incidente in incidentes:
                if reporte is None:
                    marca = "local"
                else:
                    marca = "OK" if reporte.disponible else "encolado"
                evento = incidente.get("event", "inicio")
                print(f"  -> {evento.upper()} {incidente['violation_types']} "
                      f"pid={incidente['person_track_id']} [{marca}]")

            if reporte is not None and not reporte.disponible and not reporte.pendientes:
                enviados = reporte.vaciar_cola()
                if enviados:
                    print(f"  API recuperada: {enviados} incidentes enviados "
                          "desde la cola.")

            dibujar_hud(frame, medidor)
            cv2.imshow(VENTANA, frame)
            if cv2.waitKey(1) & 0xFF == ord("q"):
                break
    finally:
        # El video tiene fin fijo: quien quedo sin cerrar aqui quedaria abierto
        # en la API para siempre, asi que se cierran los episodios pendientes.
        for cierre in monitor.cerrar_episodios():
            marca = "local" if reporte is None else (
                "OK" if reporte.disponible else "encolado")
            print(f"  -> FIN {cierre['violation_types']} "
                  f"pid={cierre['person_track_id']} [{marca}]")

        cap.release()
        cv2.destroyAllWindows()

        if reporte is not None and reporte.pendientes:
            enviados = reporte.vaciar_cola()
            if enviados:
                print(f"Cola vaciada: {enviados} incidentes enviados.")
            else:
                print(f"Quedan {len(reporte.pendientes)} incidentes en la cola local.")

        if temporal is not None:
            shutil.rmtree(temporal.parent, ignore_errors=True)

        print(medidor.linea_resumen())


if __name__ == "__main__":
    main()
