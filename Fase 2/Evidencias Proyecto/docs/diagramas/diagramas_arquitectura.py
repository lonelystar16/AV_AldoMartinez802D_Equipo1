"""Genera los diagramas del capítulo de arquitectura del D2 (tarea 3.1).

    python diagramas_arquitectura.py [carpeta_salida]

Produce Diagrama_Arquitectura.png (vista lógica y comunicación entre servicios)
y Diagrama_Despliegue.png (vista de despliegue UML). Usa el mismo estilo que el
diagrama de casos de uso del SRS. Coordenadas en décimas de pulgada.
"""

import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.patches import Arc, Ellipse, FancyArrowPatch, FancyBboxPatch, Polygon, Rectangle  # noqa: E402

NAVY = "#1F3864"
AZUL = "#DEE9F6"
GRIS = "#F2F2F2"
ROJO = "#C00000"
ROSA = "#FBE3E3"
VERDE = "#E2F0D9"
NARANJA = "#FDF0E3"
TEXTO = "#222222"


def lienzo(titulo):
    fig = plt.figure(figsize=(11, 8.5))
    ax = fig.add_axes([0, 0, 1, 1])
    ax.set_xlim(0, 110)
    ax.set_ylim(0, 85)
    ax.set_aspect("equal")
    ax.axis("off")
    ax.text(55, 82.3, titulo, ha="center", va="center", fontsize=13.5,
            fontweight="bold", color=NAVY)
    return fig, ax


def caja(ax, x, y, w, h, titulo, este=None, sub=None, fill=AZUL, ec=NAVY, lw=1.4,
         tsize=8.6, ssize=7.4, arriba=False, z=2):
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0,rounding_size=0.8",
                                fc=fill, ec=ec, lw=lw, zorder=z))
    lineas = []
    if este:
        lineas.append((f"«{este}»", ssize - 0.4, "normal", "italic"))
    lineas.append((titulo, tsize, "bold", "normal"))
    for s in (sub or []):
        lineas.append((s, ssize, "normal", "normal"))
    paso = [l[1] * 0.205 for l in lineas]
    alto = sum(paso)
    yy = (y + h - 1.0) if arriba else (y + h / 2 + alto / 2)
    for (t, fs, fw, st), p in zip(lineas, paso):
        yy -= p / 2
        ax.text(x + w / 2, yy, t, ha="center", va="center", fontsize=fs,
                fontweight=fw, style=st, color=NAVY if fw == "bold" else TEXTO, zorder=z + 1)
        yy -= p / 2


def cilindro(ax, x, y, w, h, titulo, este=None, sub=None, fill=VERDE, z=2):
    e = min(2.4, h * 0.25)
    ax.add_patch(Rectangle((x, y + e / 2), w, h - e, fc=fill, ec="none", zorder=z))
    ax.add_patch(Ellipse((x + w / 2, y + e / 2), w, e, fc=fill, ec="none", zorder=z))
    ax.add_patch(Arc((x + w / 2, y + e / 2), w, e, theta1=180, theta2=360, ec=NAVY, lw=1.3,
                     zorder=z + 0.1))
    ax.plot([x, x], [y + e / 2, y + h - e / 2], color=NAVY, lw=1.3, zorder=z + 0.1)
    ax.plot([x + w, x + w], [y + e / 2, y + h - e / 2], color=NAVY, lw=1.3, zorder=z + 0.1)
    ax.add_patch(Rectangle((x + 0.05, y + e / 2), w - 0.1, 0.4, fc=fill, ec="none", zorder=z + 0.05))
    ax.add_patch(Ellipse((x + w / 2, y + h - e / 2), w, e, fc=fill, ec=NAVY, lw=1.3, zorder=z + 0.2))
    lineas = []
    if este:
        lineas.append((f"«{este}»", 6.8, "normal", "italic"))
    lineas.append((titulo, 8.4, "bold", "normal"))
    for s in (sub or []):
        lineas.append((s, 7.0, "normal", "normal"))
    paso = [l[1] * 0.205 for l in lineas]
    yy = y + h / 2 - e * 0.1 + sum(paso) / 2
    for (t, fs, fw, st), p in zip(lineas, paso):
        yy -= p / 2
        ax.text(x + w / 2, yy, t, ha="center", va="center", fontsize=fs, fontweight=fw,
                style=st, color=NAVY if fw == "bold" else TEXTO, zorder=z + 1)
        yy -= p / 2


def nodo(ax, x, y, w, h, titulo, este="device", sub=None, d=2.2, fill=GRIS, z=1,
         tsize=9.2):
    """Nodo UML de despliegue (caja con profundidad)."""
    ax.add_patch(Polygon([(x, y + h), (x + d, y + h + d), (x + w + d, y + h + d), (x + w, y + h)],
                         closed=True, fc="#D9D9D9", ec=NAVY, lw=1.3, zorder=z))
    ax.add_patch(Polygon([(x + w, y), (x + w + d, y + d), (x + w + d, y + h + d), (x + w, y + h)],
                         closed=True, fc="#BFBFBF", ec=NAVY, lw=1.3, zorder=z))
    ax.add_patch(Rectangle((x, y), w, h, fc=fill, ec=NAVY, lw=1.5, zorder=z))
    ax.text(x + w / 2, y + h - 1.3, f"«{este}»", ha="center", va="center", fontsize=7.0,
            style="italic", color=TEXTO, zorder=z + 1)
    ax.text(x + w / 2, y + h - 3.0, titulo, ha="center", va="center", fontsize=tsize,
            fontweight="bold", color=NAVY, zorder=z + 1)
    for i, s in enumerate(sub or []):
        ax.text(x + w / 2, y + h - 4.7 - i * 1.55, s, ha="center", va="center",
                fontsize=7.2, color=TEXTO, zorder=z + 1)


def flecha(ax, p1, p2, color="#333333", lw=1.2, ls="-", cabeza="-|>", rad=0.0, z=4,
           ambos=False):
    estilo = "<|-|>" if ambos else cabeza
    ax.add_patch(FancyArrowPatch(p1, p2, arrowstyle=estilo, mutation_scale=11, color=color,
                                 lw=lw, ls=ls, connectionstyle=f"arc3,rad={rad}",
                                 shrinkA=0, shrinkB=0, zorder=z))


def etiqueta(ax, x, y, texto, color=NAVY, fs=7.2, fondo="white", negrita=True, z=6,
             ha="center"):
    ax.text(x, y, texto, ha=ha, va="center", fontsize=fs, color=color,
            fontweight="bold" if negrita else "normal", zorder=z,
            bbox=dict(boxstyle="round,pad=0.22", fc=fondo, ec=color, lw=0.7))


def zona(ax, x, y, w, h, texto, color="#7F7F7F"):
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0,rounding_size=1.2",
                                fc="none", ec=color, lw=1.2, ls=(0, (5, 3)), zorder=0.5))
    ax.text(x + 1.2, y + h - 1.3, texto, ha="left", va="center", fontsize=8.2,
            style="italic", color=color, zorder=0.6)


# ---------------------------------------------------------------- arquitectura
def arquitectura(salida: Path):
    fig, ax = lienzo("CascoVision · Arquitectura lógica y comunicación entre servicios")

    zona(ax, 1, 1, 87, 78.5, "Red local de la faena · on-premise (el video no sale de la obra)")
    zona(ax, 90, 1, 19, 78.5, "Internet · solo salida")

    # Cámaras (apiladas)
    for k in (2, 1):
        ax.add_patch(FancyBboxPatch((3 + k * 0.9, 58 + k * 0.9), 15, 10,
                                    boxstyle="round,pad=0,rounding_size=0.8",
                                    fc=GRIS, ec=NAVY, lw=1.0, zorder=1.5))
    caja(ax, 3, 58, 15, 10, "Cámaras IP ×N", "existentes", ["video H.264"], fill=GRIS)

    # Agente Edge
    caja(ax, 20, 42, 46, 34, "Agente Edge", "contenedor edge",
         ["Python 3.12 · Ultralytics · OpenCV"], fill="#F4F8FC", arriba=True, z=1)
    m = dict(tsize=7.7, ssize=6.8, lw=1.1)
    caja(ax, 22, 59, 13, 6.5, "Captura RTSP", sub=["1 cuadro/s por cámara"],
         fill=ROSA, ec=ROJO, **m)
    caja(ax, 37, 59, 13, 6.5, "YOLO26s + ByteTrack", sub=["inferencia en CPU"],
         fill=ROSA, ec=ROJO, **m)
    caja(ax, 52, 59, 12.5, 6.5, "Zonas y supresión", sub=["polígonos · 60 s"],
         fill=ROSA, ec=ROJO, **m)
    caja(ax, 52, 51, 12.5, 6.5, "Cliente de baliza", sub=["1,5 s × 2 · heartbeat"],
         fill=ROSA, ec=ROJO, **m)
    caja(ax, 37, 51, 13, 6.5, "Difuminado YuNet", sub=["antes de guardar"], **m)
    caja(ax, 52, 43.3, 12.5, 6.5, "Evidencia", sub=["incidents/AAAA/MM/DD"], **m)
    caja(ax, 37, 43.3, 13, 6.5, "Cliente API", sub=["asíncrono, con cola"], **m)
    caja(ax, 22, 43.3, 13, 6.5, "Caché de config.", sub=["zonas y balizas"], **m)

    flecha(ax, (35, 62.25), (37, 62.25), color=ROJO, lw=1.6)
    flecha(ax, (50, 62.25), (52, 62.25), color=ROJO, lw=1.6)
    flecha(ax, (58.25, 59), (58.25, 57.5), color=ROJO, lw=1.6)
    flecha(ax, (52, 54.25), (50, 54.25), ls=(0, (3, 2)))
    flecha(ax, (50, 51.8), (52, 49.8))
    flecha(ax, (52, 46.55), (50, 46.55))
    flecha(ax, (37, 46.55), (35, 46.55), ls=(0, (1, 1.5)))
    ax.text(27.5, 53.6, "después de la\nalerta: difuminar,\nguardar, informar", ha="center",
            va="center", fontsize=6.6, style="italic", color="#555555", zorder=3)

    # Baliza
    caja(ax, 71, 54, 16, 11, "Baliza zonal ×N", "dispositivo",
         ["M5Stack StickS3", "sonido + pantalla"], fill=GRIS)

    # Volumen de evidencia
    cilindro(ax, 71, 36.5, 16, 10, "evidencia", "volumen", ["solo difuminada"], fill=NARANJA)

    # API
    caja(ax, 44, 5, 22, 32, "API REST", "contenedor api",
         ["FastAPI · uvicorn :8000"], fill="#F4F8FC", arriba=True, z=1)
    rutas = [("GET /health", "pública"), ("POST /incidents", "token Edge"),
             ("GET /edge/config", "token Edge"), ("/auth · /incidents", "JWT"),
             ("/cameras /zones /beacons", "JWT"), ("GET …/evidence", "JWT"),
             ("WS /ws/incidents", "JWT"), ("Notificador", "SMS · correo")]
    for i, (r, a) in enumerate(rutas):
        yy = 26.2 - i * 2.55
        ax.add_patch(Rectangle((45.3, yy - 1.05), 19.4, 2.1, fc="white", ec="#9DB3D1",
                               lw=0.6, zorder=2))
        ax.text(46, yy, r, ha="left", va="center", fontsize=6.9, family="monospace",
                color=TEXTO, zorder=3)
        ax.text(64.2, yy, a, ha="right", va="center", fontsize=6.4, style="italic",
                color=NAVY, zorder=3)

    # PostgreSQL
    cilindro(ax, 71, 4, 16, 11, "PostgreSQL", "contenedor db", ["incidentes · config", "usuarios"])

    # Dashboard y usuarios
    caja(ax, 22, 18, 17, 11, "Dashboard web", "contenedor dashboard",
         ["React · nginx", "proxy /api y /ws"])
    caja(ax, 3, 18, 14, 11, "Usuarios", "navegador",
         ["prevencionista", "supervisor · admin"], fill=GRIS)

    # Externos
    caja(ax, 92, 30, 15.5, 9, "Twilio", "externo", ["API de SMS"], fill=GRIS)
    caja(ax, 92, 17, 15.5, 9, "Servidor SMTP", "externo", ["correo"], fill=GRIS)
    ax.text(99.75, 9.5, "Prevencionista:\nSMS al celular y\ncorreo con imagen\ndifuminada",
            ha="center", va="center", fontsize=6.8, style="italic", color="#555555")

    # Comunicación entre servicios
    flecha(ax, (18, 63), (22, 62.25), color=ROJO, lw=1.6)
    etiqueta(ax, 19.6, 66.2, "I-01", color=ROJO)
    flecha(ax, (64.5, 55.5), (71, 58.5), color=ROJO, lw=1.6)
    etiqueta(ax, 67.6, 59.8, "I-02", color=ROJO)
    flecha(ax, (64.5, 52.5), (71, 55.5), ls=(0, (4, 2)))
    etiqueta(ax, 67.9, 51.2, "I-03")
    flecha(ax, (64.5, 46), (71, 42.5))
    etiqueta(ax, 68.0, 46.9, "rw", negrita=False)
    flecha(ax, (43.5, 43.3), (52, 37), ambos=True)
    etiqueta(ax, 44.8, 39.6, "I-04 · I-05")
    flecha(ax, (66, 30), (74, 36.9), ls=(0, (4, 2)))
    etiqueta(ax, 69.0, 31.6, "ro", negrita=False)
    flecha(ax, (66, 10), (71, 9.5), ambos=True)
    etiqueta(ax, 68.5, 12.5, "I-08")
    flecha(ax, (39, 23.5), (44, 23.5), ambos=True)
    etiqueta(ax, 41.5, 27.5, "I-06\nI-07")
    flecha(ax, (17, 23.5), (22, 23.5), ambos=True)
    etiqueta(ax, 19.5, 26.6, "HTTPS", negrita=False)
    flecha(ax, (66, 22), (92, 34))
    etiqueta(ax, 79.0, 28.0, "I-09")
    flecha(ax, (66, 19.5), (92, 21))
    etiqueta(ax, 80.0, 20.3, "I-10")

    # Leyenda
    ax.add_patch(Rectangle((3, 3), 36, 12, fc="white", ec="#BFBFBF", lw=0.8, zorder=2))
    ax.plot([4.5, 9.5], [12.4, 12.4], color=ROJO, lw=1.8, zorder=3)
    ax.text(10.5, 12.4, "Ruta crítica de la alerta: < 5 s,", fontsize=6.9, va="center", zorder=3)
    ax.text(10.5, 10.6, "no pasa por la API (RNF-02)", fontsize=6.9, va="center", zorder=3)
    ax.plot([4.5, 9.5], [8.4, 8.4], color="#333333", lw=1.2, ls=(0, (4, 2)), zorder=3)
    ax.text(10.5, 8.4, "Consulta periódica o lectura", fontsize=6.9, va="center", zorder=3)
    ax.text(4.5, 5.3, "I-xx: interfaz descrita en la tabla de\ncomunicación entre servicios (§4)",
            fontsize=6.6, va="center", style="italic", color="#555555", zorder=3)

    fig.savefig(salida / "Diagrama_Arquitectura.png", dpi=200, bbox_inches="tight",
                facecolor="white")
    plt.close(fig)


# ---------------------------------------------------------------- despliegue
def despliegue(salida: Path):
    fig, ax = lienzo("CascoVision · Diagrama de despliegue (UML)")

    zona(ax, 1, 1, 79, 78.5, "LAN de la faena")
    zona(ax, 83, 1, 26, 40, "Internet")

    # Servidor Edge
    nodo(ax, 28, 8, 46, 66, "Servidor Edge", "device",
         ["PC x86-64 · CPU de 4+ núcleos · 16 GB RAM · SSD 256 GB",
          "Ubuntu 24.04 LTS o Windows 11"], z=1)
    caja(ax, 30, 10, 42, 54, "Docker Engine + Docker Compose", "execution environment",
         ["red interna «cascovision» (bridge) · restart: unless-stopped"],
         fill="#F4F8FC", arriba=True, tsize=8.6, ssize=7.0, z=1.5)

    c = dict(tsize=8.6, ssize=6.8, lw=1.2)
    caja(ax, 32, 46, 38, 10.5, "edge", "contenedor",
         ["python:3.12-slim · YOLO26s · ByteTrack · YuNet",
          "sin puertos publicados · sale a cámaras (:554) y balizas (:80)"], **c)
    caja(ax, 32, 33.5, 18.5, 10, "dashboard", "contenedor",
         ["nginx: React + proxy /api, /ws", "publica :443 (y :80 → 443)"], **c)
    caja(ax, 51.5, 23, 18.5, 20.5, "api", "contenedor",
         ["python:3.12-slim", "FastAPI · uvicorn :8000", "solo red interna",
          "notificador SMS y correo"], **c)
    caja(ax, 32, 23, 18.5, 9, "db", "contenedor",
         ["postgres:16 · :5432", "solo red interna"], **c)

    cilindro(ax, 32, 11.5, 8.5, 9.5, "pgdata", "volumen", ["db"])
    cilindro(ax, 41.5, 11.5, 9, 9.5, "evidencia", "volumen", ["edge rw · api ro"], fill=NARANJA)
    cilindro(ax, 51.5, 11.5, 9, 9.5, "edge-datos", "volumen", ["cola · caché"])
    cilindro(ax, 61.5, 11.5, 8.5, 9.5, "modelos", "volumen", ["edge: ro"])

    # Conexiones internas
    flecha(ax, (60.75, 46), (60.75, 43.5), lw=1.0)
    etiqueta(ax, 65.0, 44.8, ":8000", fs=6.6, negrita=False)
    flecha(ax, (50.5, 38.5), (51.5, 38.5), lw=1.0)
    etiqueta(ax, 51.0, 31.8, ":8000", fs=6.6, negrita=False)
    flecha(ax, (51.5, 27.5), (50.5, 27.5), lw=1.0)
    etiqueta(ax, 51.0, 21.4, ":5432", fs=6.6, negrita=False)

    # Cámaras y usuarios
    nodo(ax, 3, 55, 17, 13, "Cámara IP ×N", "device", ["RTSP :554 · H.264", "PoE, IP fija"])
    nodo(ax, 3, 27, 17, 13, "Equipo del usuario", "device", ["PC, tablet o teléfono", "navegador web"])

    # Baliza
    nodo(ax, 84, 50, 21, 22, "Baliza zonal ×N", "device",
         ["M5Stack StickS3 (ESP32-S3)", "batería 250 mAh · USB-C"], z=1)
    caja(ax, 86, 52, 17, 9.5, "firmware-baliza", "artifact",
         ["M5Unified · HTTP :80", "/alert · /health"], tsize=8.0, ssize=6.8, lw=1.1)

    # Internet
    caja(ax, 86, 26, 20, 9, "Twilio", "servicio externo", ["API REST de SMS · :443"], fill=GRIS,
         tsize=8.2, ssize=6.8)
    caja(ax, 86, 13, 20, 9, "Servidor SMTP", "servicio externo", ["STARTTLS · :587"], fill=GRIS,
         tsize=8.2, ssize=6.8)
    ax.text(96, 6.5, "Solo texto e imagen\ndifuminada (RNF-08)", ha="center", va="center",
            fontsize=6.8, style="italic", color="#555555")

    # Firewall
    ax.add_patch(Rectangle((79.2, 8), 1.6, 30, fc="#E7B5A3", ec="#A0522D", lw=1.0, zorder=3))
    ax.text(80.0, 23, "firewall", rotation=90, ha="center", va="center", fontsize=6.8,
            color="#7A2E10", zorder=4)

    # Rutas de comunicación (UML: líneas con protocolo)
    flecha(ax, (20, 61), (32, 53), color=ROJO, lw=1.5)
    etiqueta(ax, 24.6, 63.4, "RTSP/TCP :554\nLAN cableada", color=ROJO, fs=6.6)
    flecha(ax, (70, 52), (86, 56.5), color=ROJO, lw=1.5)
    etiqueta(ax, 79.5, 45.0, "HTTP :80\nPOST /alert (token)\nGET /health\nWiFi WPA2",
             color=ROJO, fs=6.6)
    ax.plot([79.5, 79.5], [48.4, 54.6], color=ROJO, lw=0.6, ls=":", zorder=5)
    flecha(ax, (20, 34), (32, 38.5), ambos=True, lw=1.3)
    etiqueta(ax, 25.5, 30.0, "HTTPS :443\nJWT · WebSocket", fs=6.6)
    flecha(ax, (70, 30), (86, 30), lw=1.3)
    etiqueta(ax, 76.0, 34.5, "HTTPS :443\nSMTP :587\nsolo salida", fs=6.6)
    flecha(ax, (70, 28), (86, 17.5), lw=1.3)

    # Nota
    ax.text(3, 13.5, "Desarrollo y pruebas (perfil «dev»):\n"
            "rtsp-sim reemplaza a la cámara\n(MediaMTX con video pregrabado) y\n"
            "receptor-sim a la baliza (mismo\nprotocolo). La API publica :8000.",
            ha="left", va="center", fontsize=6.8, color="#333333",
            bbox=dict(boxstyle="round,pad=0.5", fc="#FFFBEA", ec="#C9B458", lw=0.8))

    fig.savefig(salida / "Diagrama_Despliegue.png", dpi=200, bbox_inches="tight",
                facecolor="white")
    plt.close(fig)


if __name__ == "__main__":
    carpeta = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parent
    carpeta.mkdir(parents=True, exist_ok=True)
    arquitectura(carpeta)
    despliegue(carpeta)
    print("Diagramas generados en", carpeta)
