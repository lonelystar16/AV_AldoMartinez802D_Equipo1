"""Genera los diagramas UML del D2 (tarea 3.5): clases, secuencia y componentes.

    python diagramas_uml.py [carpeta_salida]

Reutiliza el estilo y las funciones de diagramas_arquitectura.py.
"""

import sys
from pathlib import Path

import matplotlib.pyplot as plt
from matplotlib.patches import Arc, Circle, FancyBboxPatch, Polygon, Rectangle

from diagramas_arquitectura import (AZUL, GRIS, NAVY, ROJO, ROSA, TEXTO, caja, cilindro,
                                    etiqueta, flecha, lienzo, zona)

BLANCO = "white"
LINEA = 1.42  # alto de una línea de texto de 7 pt, en décimas de pulgada


# ---------------------------------------------------------------- clases
def clase(ax, x, y_top, w, nombre, atributos, metodos, este=None, existe=False):
    """Clase UML con tres compartimentos. Devuelve (x, y_inferior, w, h)."""
    cab = 2.7 if este else 2.0
    h = cab + 0.5 + LINEA * max(len(atributos), 1) + 0.5 + LINEA * max(len(metodos), 1) + 0.4
    y = y_top - h
    fill = AZUL if existe else BLANCO
    ax.add_patch(Rectangle((x, y), w, h, fc=fill, ec=NAVY, lw=1.2, zorder=3))
    yy = y_top - 0.95
    if este:
        ax.text(x + w / 2, yy, f"«{este}»", ha="center", va="center", fontsize=6.4,
                style="italic", color=TEXTO, zorder=4)
        yy -= 1.2
    ax.text(x + w / 2, yy, nombre, ha="center", va="center", fontsize=7.9,
            fontweight="bold", color=NAVY, zorder=4)
    y1 = y_top - cab
    ax.plot([x, x + w], [y1, y1], color=NAVY, lw=0.9, zorder=4)
    yy = y1 - 0.25 - LINEA / 2
    for a in atributos:
        ax.text(x + 0.6, yy, a, ha="left", va="center", fontsize=6.7, family="DejaVu Sans Mono",
                color=TEXTO, zorder=4)
        yy -= LINEA
    if not atributos:
        yy -= LINEA
    y2 = yy + LINEA / 2 - 0.25
    ax.plot([x, x + w], [y2, y2], color=NAVY, lw=0.9, zorder=4)
    yy = y2 - 0.25 - LINEA / 2
    for m in metodos:
        ax.text(x + 0.6, yy, m, ha="left", va="center", fontsize=6.7, family="DejaVu Sans Mono",
                color=TEXTO, zorder=4)
        yy -= LINEA
    return x, y, w, h


def rel(ax, p1, p2, tipo="asoc", texto=None, tpos=None, color="#333333"):
    """Relación UML: asoc (flecha), comp (rombo lleno), dep (punteada), real (triángulo hueco)."""
    if tipo == "comp":
        flecha(ax, p2, p1, cabeza="-", color=color, lw=1.0)
        dx, dy = p2[0] - p1[0], p2[1] - p1[1]
        n = (dx ** 2 + dy ** 2) ** 0.5 or 1
        ux, uy = dx / n, dy / n
        L, W = 1.6, 0.6
        pts = [p1, (p1[0] + ux * L / 2 - uy * W, p1[1] + uy * L / 2 + ux * W),
               (p1[0] + ux * L, p1[1] + uy * L), (p1[0] + ux * L / 2 + uy * W, p1[1] + uy * L / 2 - ux * W)]
        ax.add_patch(Polygon(pts, closed=True, fc=NAVY, ec=NAVY, lw=0.8, zorder=5))
    elif tipo == "dep":
        flecha(ax, p1, p2, ls=(0, (3, 2)), lw=1.0, color=color)
    elif tipo == "real":
        flecha(ax, p1, p2, ls=(0, (3, 2)), lw=1.0, cabeza="-|>", color=color)
        ax.add_patch(Polygon([p2, (p2[0] - 0.8, p2[1] - 1.4), (p2[0] + 0.8, p2[1] - 1.4)],
                             closed=True, fc="white", ec=color, lw=1.0, zorder=6))
    else:
        flecha(ax, p1, p2, lw=1.0, color=color)
    if texto:
        x, y = tpos or ((p1[0] + p2[0]) / 2, (p1[1] + p2[1]) / 2)
        ax.text(x, y, texto, ha="center", va="center", fontsize=6.3, color=NAVY, style="italic",
                zorder=7, bbox=dict(boxstyle="round,pad=0.12", fc="white", ec="none"))


def clases(salida: Path):
    fig, ax = lienzo("CascoVision · Diagrama de clases (agente Edge y API)")
    zona(ax, 1, 1, 64, 78.5, "paquete edge (agente Edge)", color=NAVY)
    zona(ax, 67, 1, 42, 78.5, "paquete api (FastAPI)", color=NAVY)

    # ---- agente Edge: el agente al centro y sus partes a cada lado
    ag = clase(ax, 25, 62, 17, "AgenteEdge",
               ["- config: CacheConfig", "- camaras: [CapturaRTSP]"],
               ["+ ejecutar()", "- procesar(cam, cuadro)"])
    cap = clase(ax, 2.5, 75, 19, "CapturaRTSP",
                ["- url: str", "- fps: int = 1"],
                ["+ leer_cuadro(): Frame", "+ reconectar()"])
    mon = clase(ax, 2.5, 61, 19, "MonitorEPP",
                ["- modelo: YOLO (YOLO26s)", "- detector_rostros: YuNet", "- historial: dict"],
                ["+ procesar(cuadro): list", "+ difumar_rostros(c)", "+ guardar_evidencia(c)"],
                existe=True)
    rep = clase(ax, 2.5, 44, 19, "ReporteAPI",
                ["- url, token: str", "- cola: deque (disco)"],
                ["+ enviar(incidente)", "+ vaciar_cola(): int"], existe=True)
    cfg = clase(ax, 45.5, 75, 18, "CacheConfig",
                ["- camaras, zonas, balizas", "- archivo: Path"],
                ["+ actualizar()", "+ baliza_de(zona)"])
    zon = clase(ax, 45.5, 63, 18, "EvaluadorZonas",
                ["- zonas: list[Zona]"], ["+ zona_de(caja): Zona"])
    sup = clase(ax, 45.5, 54, 18, "SupresorAlertas",
                ["- ventana_s = 60"], ["+ debe_alertar(id, zona)"])
    bal = clase(ax, 45.5, 44.5, 18, "ClienteBaliza",
                ["- token: str", "- timeout_s = 1.5", "- reintentos = 1"],
                ["+ alertar(b, inf)", "+ heartbeat(b): bool"])
    inf = clase(ax, 25, 31, 17, "Infraccion",
                ["track_id: int", "tipos: list[str]", "confianza: float", "momento: datetime"],
                [], este="dataclass")

    izq, der = ag[0], ag[0] + ag[2]
    rel(ax, (izq, 60.5), (cap[0] + cap[2], cap[1] + 2.5), "comp", "1..*", (23.2, 66.5))
    rel(ax, (izq, 57.5), (mon[0] + mon[2], mon[1] + 8), "comp")
    rel(ax, (izq, 54.5), (rep[0] + rep[2], rep[1] + 5), "comp")
    rel(ax, (der, 60.5), (cfg[0], cfg[1] + 3), "comp")
    rel(ax, (der, 58.5), (zon[0], zon[1] + 3), "comp")
    rel(ax, (der, 56.2), (sup[0], sup[1] + 3), "comp")
    rel(ax, (der, 54.2), (bal[0], bal[1] + 6), "comp")
    rel(ax, (mon[0] + mon[2], mon[1] + 1.5), (inf[0] + 4, inf[1] + inf[3]), "dep", "«crea»", (24.6, 40))
    rel(ax, (bal[0], bal[1] + 2), (inf[0] + inf[2], inf[1] + 6), "dep", "«usa»", (44, 31))

    # ---- API
    app = clase(ax, 68.5, 75, 21.5, "app (rutas)",
                ["- bearer: HTTPBearer"],
                ["+ health()", "+ create_incident(inc)", "+ list_incidents(f)",
                 "+ get_incident(id)", "+ get_evidence(id)", "+ edge_config()", "+ login(u, clave)"],
                este="FastAPI", existe=True)
    noti = clase(ax, 92, 75, 16, "Notificador", ["- twilio, smtp"], ["+ notificar(inc)"])
    aut = clase(ax, 92, 66, 16, "ServicioAuth", ["- jwt_secret"], ["+ verificar(jwt, roles)"])
    inc = clase(ax, 68.5, 55, 18, "IncidentCreate",
                ["camera_id, zone_id", "detected_at", "violation_type(s)", "confidence",
                 "evidence_path", "person_track_id"],
                ["validar rutas y fechas"], este="Pydantic", existe=True)
    bea = clase(ax, 68.5, 35, 18, "BeaconAlert", ["status", "latency_ms"], [],
                este="Pydantic", existe=True)
    alm = clase(ax, 90, 55, 17.5, "Almacen", [],
                ["+ crear(registro)", "+ listar(f, p, l)", "+ obtener(id)"],
                este="Protocol", existe=True)
    js = clase(ax, 88.6, 38, 9.6, "AlmacenJSON", [], ["…"], existe=True)
    pg = clase(ax, 98.8, 38, 9.6, "AlmacenPg", [], ["…"], existe=True)

    rel(ax, (app[0] + app[2], 72), (noti[0], 72), "asoc")
    rel(ax, (app[0] + app[2], 63), (aut[0], 63), "asoc")
    rel(ax, (77.5, app[1]), (77.5, inc[1] + inc[3]), "dep", "«valida»", (80.5, 57.5))
    rel(ax, (77.5, inc[1]), (77.5, bea[1] + bea[3]), "comp")
    rel(ax, (app[0] + app[2] - 2, app[1]), (alm[0] + 6, alm[1] + alm[3]), "asoc")
    rel(ax, (js[0] + 4.8, js[1] + js[3]), (alm[0] + 4, alm[1]), "real")
    rel(ax, (pg[0] + 4.8, pg[1] + pg[3]), (alm[0] + 13.5, alm[1]), "real")
    ax.text(98.5, 28.6, "CASCOVISION_STORAGE\nelige json o postgres", ha="center", va="center",
            fontsize=6.3, style="italic", color="#555555")

    # entre paquetes: el reporte envía el JSON que valida IncidentCreate
    yb = rep[1]
    ax.plot([12, 12, 66], [yb, 2.8, 2.8], color="#333333", lw=1.0, ls=(0, (3, 2)), zorder=4)
    ax.plot([66, 66], [2.8, 48], color="#333333", lw=1.0, ls=(0, (3, 2)), zorder=4)
    flecha(ax, (66, 48), (68.5, 48), ls=(0, (3, 2)), lw=1.0)
    ax.text(40, 2.8, "«envía» POST /incidents (JSON por HTTP)", ha="center", va="center",
            fontsize=6.6, style="italic", color=NAVY, zorder=6,
            bbox=dict(boxstyle="round,pad=0.15", fc="white", ec="none"))

    # leyenda
    ax.add_patch(Rectangle((45.5, 14.5), 5, 2.2, fc=AZUL, ec=NAVY, lw=1.0))
    ax.text(51.5, 15.6, "ya implementada", fontsize=6.8, va="center")
    ax.add_patch(Rectangle((45.5, 10.5), 5, 2.2, fc="white", ec=NAVY, lw=1.0))
    ax.text(51.5, 11.6, "por construir (4.4 a 4.20)", fontsize=6.8, va="center")

    fig.savefig(salida / "Diagrama_Clases.png", dpi=200, bbox_inches="tight", facecolor="white")
    plt.close(fig)


# ---------------------------------------------------------------- secuencia
def secuencia(salida: Path):
    fig, ax = lienzo("CascoVision · Diagrama de secuencia: detección y alerta (CU-02 y CU-04)")
    actores = [("Cámara IP", 7), ("Agente Edge", 22), ("Baliza zonal", 38), ("API REST", 54),
               ("PostgreSQL", 69), ("Dashboard", 83), ("Twilio · SMTP", 98)]
    top, bottom = 74, 4
    for nombre, x in actores:
        caja(ax, x - 6.2, top, 12.4, 4.2, nombre, fill=GRIS if nombre in ("Cámara IP", "Baliza zonal", "Twilio · SMTP") else AZUL,
             tsize=8.0)
        ax.plot([x, x], [bottom, top], color="#7F7F7F", lw=0.9, ls=(0, (4, 3)), zorder=1)

    X = dict(actores)

    def msg(y, a, b, texto, ret=False, color="#222222", lw=1.1):
        flecha(ax, (X[a], y), (X[b], y), color=color, lw=lw, ls=(0, (4, 2)) if ret else "-",
               cabeza="->" if ret else "-|>")
        ax.text((X[a] + X[b]) / 2, y + 0.9, texto, ha="center", va="bottom", fontsize=6.9,
                color=color, zorder=6)

    def propio(y, a, texto, color="#222222"):
        x = X[a]
        ax.plot([x, x + 3, x + 3], [y + 0.8, y + 0.8, y - 0.8], color=color, lw=1.0, zorder=4)
        flecha(ax, (x + 3, y - 0.8), (x, y - 0.8), color=color, lw=1.0)
        ax.text(x + 3.6, y, texto, ha="left", va="center", fontsize=6.9, color=color, zorder=6)

    def activacion(a, y1, y2, fc="white"):
        ax.add_patch(Rectangle((X[a] - 0.6, y2), 1.2, y1 - y2, fc=fc, ec=NAVY, lw=0.9, zorder=3))

    activacion("Agente Edge", 70, 23)
    activacion("Baliza zonal", 55.5, 48.5, fc=ROSA)
    activacion("API REST", 36, 9)

    msg(70, "Cámara IP", "Agente Edge", "1: cuadro RTSP (1 por segundo)", color=ROJO, lw=1.4)
    propio(66, "Agente Edge", "2: detectar EPP (YOLO26s) y seguir (ByteTrack)", color=ROJO)
    propio(61.5, "Agente Edge", "3: zona_de(caja) · debe_alertar(track_id, zona)", color=ROJO)
    msg(55.5, "Agente Edge", "Baliza zonal", "4: POST /alert {alert_id, zone_id, violations}", color=ROJO, lw=1.4)
    propio(52, "Baliza zonal", "sonido + pantalla", color=ROJO)
    msg(48.5, "Baliza zonal", "Agente Edge", "5: 200 {status: alerting}", ret=True, color=ROJO)

    # fragmento opt de reintento
    ax.add_patch(Rectangle((14, 45), 32, 13.2, fc="none", ec="#7F7F7F", lw=0.9, zorder=2))
    ax.add_patch(Polygon([(14, 58.2), (19, 58.2), (19, 57), (18.2, 56.3), (14, 56.3)], closed=True,
                         fc="#EDEDED", ec="#7F7F7F", lw=0.9, zorder=2))
    ax.text(16.3, 57.3, "opt", fontsize=6.8, fontweight="bold", ha="center", va="center")
    ax.text(15, 46.1, "[sin respuesta en 1,5 s] reintento único con el mismo alert_id;\n"
            "a los 3 s → beacon_alert = failed", fontsize=6.3, style="italic", color="#555555",
            va="center")

    # llave de la ruta crítica
    ax.plot([2, 1.2, 1.2, 2], [71, 71, 48, 48], color=ROJO, lw=1.4)
    ax.text(1.7, 59.5, "≤ 4,5 s\n(RNF-02)", rotation=90, ha="center", va="center", fontsize=7.2,
            color=ROJO, fontweight="bold",
            bbox=dict(boxstyle="round,pad=0.2", fc="white", ec="none"))

    propio(42, "Agente Edge", "6: difuminar rostros (YuNet) y guardar evidencia")
    msg(36, "Agente Edge", "API REST", "7: POST /incidents (Bearer, asíncrono)")
    msg(31, "API REST", "PostgreSQL", "8: INSERT incidente")
    msg(27.5, "PostgreSQL", "API REST", "ok", ret=True)
    msg(23, "API REST", "Agente Edge", "9: 201 {id, status: open}", ret=True)
    msg(18.5, "API REST", "Dashboard", "10: evento WS (≤ 3 s)")
    msg(13, "API REST", "Twilio · SMTP", "11: SMS y correo (segundo plano, ≤ 30 s)")

    ax.add_patch(Rectangle((14, 21.5), 32, 18.5, fc="none", ec="#7F7F7F", lw=0.9, zorder=2))
    ax.add_patch(Polygon([(14, 40), (19, 40), (19, 38.8), (18.2, 38.1), (14, 38.1)], closed=True,
                         fc="#EDEDED", ec="#7F7F7F", lw=0.9, zorder=2))
    ax.text(16.3, 39.1, "alt", fontsize=6.8, fontweight="bold", ha="center", va="center")
    ax.text(20, 39.1, "[API disponible]", fontsize=6.3, style="italic", color="#555555", va="center")
    ax.plot([14, 46], [30.2, 30.2], color="#7F7F7F", lw=0.8, ls=(0, (3, 2)), zorder=2)
    ax.text(15, 29.2, "[API caída] el incidente queda en la cola en disco\ny se reenvía al volver",
            fontsize=6.3, style="italic", color="#555555", va="top")

    ax.text(55, 1.6, "Rojo: ruta crítica de la alerta. Los pasos 6 a 11 ocurren después y no suman a la latencia de la alerta física.",
            ha="center", va="center", fontsize=7.0, style="italic", color="#555555")

    fig.savefig(salida / "Diagrama_Secuencia.png", dpi=200, bbox_inches="tight", facecolor="white")
    plt.close(fig)


# ---------------------------------------------------------------- componentes
def componente(ax, x, y, w, h, nombre, sub=None, fill=AZUL, z=2):
    caja(ax, x, y, w, h, nombre, "component", sub, fill=fill, z=z, tsize=8.2, ssize=6.8)
    # icono de componente UML
    ix, iy = x + w - 3.2, y + h - 2.6
    ax.add_patch(Rectangle((ix, iy), 2.2, 1.8, fc="white", ec=NAVY, lw=0.8, zorder=z + 2))
    for dy in (0.3, 1.0):
        ax.add_patch(Rectangle((ix - 0.5, iy + dy), 1.0, 0.45, fc="white", ec=NAVY, lw=0.7, zorder=z + 3))


def interfaz(ax, x, y, nombre, lado="arriba", desde=None, z=5):
    """Interfaz provista (círculo). `desde` es el punto del componente que la provee."""
    if desde:
        ax.plot([desde[0], x], [desde[1], y], color=NAVY, lw=1.0, zorder=z - 1)
    ax.add_patch(Circle((x, y), 0.9, fc="white", ec=NAVY, lw=1.2, zorder=z))
    dx, dy, ha = {"arriba": (0, 1.9, "center"), "abajo": (0, -1.9, "center"),
                  "der": (1.6, 0, "left"), "izq": (-1.6, 0, "right")}[lado]
    ax.text(x + dx, y + dy, nombre, ha=ha, va="center", fontsize=6.8, fontweight="bold",
            color=NAVY, zorder=z + 1)


def requiere(ax, desde, hacia, texto=None, tpos=None):
    flecha(ax, desde, hacia, ls=(0, (3, 2)), lw=1.0)
    if texto:
        ax.text(*(tpos or ((desde[0] + hacia[0]) / 2, (desde[1] + hacia[1]) / 2)), texto,
                ha="center", va="center", fontsize=6.3, style="italic", color="#555555",
                bbox=dict(boxstyle="round,pad=0.12", fc="white", ec="none"), zorder=6)


def componentes(salida: Path):
    fig, ax = lienzo("CascoVision · Diagrama de componentes (UML)")

    # Agente Edge
    caja(ax, 2, 30, 40, 47, "Agente Edge", "component", ["contenedor edge"], fill="#F4F8FC",
         arriba=True, z=1)
    componente(ax, 4, 34, 17, 8, "Captura", ["RTSP · 1 FPS"])
    componente(ax, 23, 34, 17, 8, "Detección", ["YOLO26s · ByteTrack"])
    componente(ax, 4, 47.5, 17, 8, "Lógica de alerta", ["zonas · supresión"])
    componente(ax, 23, 47.5, 17, 8, "Cliente de baliza", ["/alert · heartbeat"])
    componente(ax, 4, 59, 17, 8, "Privacidad", ["YuNet · evidencia"])
    componente(ax, 23, 59, 17, 8, "Reporte y config.", ["cola en disco · caché"])
    flecha(ax, (21, 38), (23, 38), lw=1.0)
    flecha(ax, (31.5, 42), (12.5, 47.5), lw=1.0)
    flecha(ax, (21, 51.5), (23, 51.5), lw=1.0)
    flecha(ax, (12.5, 55.5), (12.5, 59), lw=1.0)
    flecha(ax, (21, 63), (23, 63), lw=1.0)

    # Baliza
    componente(ax, 55, 62, 22, 11, "Firmware de la baliza", ["StickS3 · M5Unified"], fill=GRIS)
    interfaz(ax, 50, 67.5, "IAlerta", "arriba", desde=(55, 67.5))
    requiere(ax, (40, 51.5), (49.2, 66.9), "POST /alert · GET /health", (46.5, 58.5))

    # API
    caja(ax, 55, 12, 30, 44, "API REST", "component", ["contenedor api"], fill="#F4F8FC",
         arriba=True, z=1)
    componente(ax, 57, 38, 12.5, 9, "Incidentes", ["/incidents"])
    componente(ax, 70.5, 38, 12.5, 9, "Configuración", ["/cameras /zones"])
    componente(ax, 57, 27, 12.5, 9, "Autenticación", ["JWT · roles"])
    componente(ax, 70.5, 27, 12.5, 9, "Tiempo real", ["WebSocket"])
    componente(ax, 57, 15.5, 12.5, 9, "Almacen", ["JSON · Postgres"])
    componente(ax, 70.5, 15.5, 12.5, 9, "Notificador", ["SMS · correo"])

    interfaz(ax, 47, 42, "IIncidentes", "abajo", desde=(55, 42))
    interfaz(ax, 47, 33.5, "IConfigEdge", "abajo", desde=(55, 33.5))
    requiere(ax, (40, 62), (46.3, 42.7))
    requiere(ax, (40, 60), (46.4, 34.3))

    interfaz(ax, 90, 45, "IConsultas", "der", desde=(85, 45))
    interfaz(ax, 90, 33, "IEventos", "der", desde=(85, 33))

    # Dashboard
    componente(ax, 92.5, 52, 15.5, 11, "Dashboard", ["React · nginx"])
    requiere(ax, (97, 52), (90.4, 45.8))
    requiere(ax, (103, 52), (90.6, 33.8), "REST + JWT · WS", (101.5, 44))

    # Base de datos y externos
    cilindro(ax, 57, 1.5, 12.5, 8.5, "PostgreSQL", "component")
    requiere(ax, (63.25, 15.5), (63.25, 10), "SQL", (66, 12.8))
    componente(ax, 90, 13, 18, 10, "Twilio · SMTP", ["servicios externos"], fill=GRIS)
    requiere(ax, (83, 20), (90, 18), "HTTPS · SMTP", (86.6, 21.6))

    # Cámaras
    componente(ax, 4, 15, 17, 9, "Cámara IP", ["firmware existente"], fill=GRIS)
    interfaz(ax, 12.5, 27.5, "RTSP", "der", desde=(12.5, 24))
    requiere(ax, (12.5, 34), (12.5, 28.4))

    ax.text(23, 8, "○ interfaz provista    ⇢ dependencia (componente que la usa)",
            ha="center", va="center", fontsize=7.0, style="italic", color="#555555")

    fig.savefig(salida / "Diagrama_Componentes.png", dpi=200, bbox_inches="tight",
                facecolor="white")
    plt.close(fig)


if __name__ == "__main__":
    carpeta = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parent
    carpeta.mkdir(parents=True, exist_ok=True)
    clases(carpeta)
    secuencia(carpeta)
    componentes(carpeta)
    print("Diagramas UML generados en", carpeta)
