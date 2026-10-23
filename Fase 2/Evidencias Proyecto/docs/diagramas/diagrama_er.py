"""Genera el diagrama ER del D2 (tarea 3.2).

    python diagrama_er.py [carpeta_salida]

Reutiliza el estilo de diagramas_arquitectura.py.
"""

import sys
from pathlib import Path

import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle

from diagramas_arquitectura import AZUL, NAVY, TEXTO, lienzo

FILA = 1.45


def tabla(ax, x, y_top, w, nombre, columnas, nueva=True):
    """columnas: (clave, nombre, tipo); clave en {'PK', 'FK', 'UQ', 'PK FK', ''}."""
    h = 2.4 + FILA * len(columnas) + 0.5
    y = y_top - h
    ax.add_patch(Rectangle((x, y), w, h, fc="white", ec=NAVY, lw=1.3, zorder=3))
    ax.add_patch(Rectangle((x, y_top - 2.4), w, 2.4, fc=NAVY if nueva else "#2E75B6", ec=NAVY,
                           lw=1.3, zorder=3))
    ax.text(x + w / 2, y_top - 1.2, nombre, ha="center", va="center", fontsize=8.2,
            fontweight="bold", color="white", zorder=4)
    yy = y_top - 2.4 - 0.25 - FILA / 2
    for clave, col, tipo in columnas:
        if clave:
            ax.text(x + 0.5, yy, clave, ha="left", va="center", fontsize=5.8, fontweight="bold",
                    color="#C00000" if "PK" in clave else NAVY, zorder=4)
        ax.text(x + 3.6, yy, col, ha="left", va="center", fontsize=6.6,
                family="DejaVu Sans Mono", color=TEXTO, zorder=4,
                fontweight="bold" if "PK" in clave else "normal")
        ax.text(x + w - 0.5, yy, tipo, ha="right", va="center", fontsize=6.0, color="#555555",
                zorder=4)
        yy -= FILA
    return x, y, w, h


def relacion(ax, p1, p2, c1="1", c2="N", ls="-", codo=None):
    pts = [p1] + ([codo] if codo else []) + [p2]
    xs, ys = zip(*pts)
    ax.plot(xs, ys, color=NAVY, lw=1.1, ls=ls, zorder=2)
    for (px, py), (qx, qy), c in ((p1, pts[1], c1), (p2, pts[-2], c2)):
        dx, dy = qx - px, qy - py
        n = (dx ** 2 + dy ** 2) ** 0.5 or 1
        ax.text(px + dx / n * 1.6 + (0.9 if abs(dy) > abs(dx) else 0),
                py + dy / n * 1.6 + (0.9 if abs(dx) >= abs(dy) else 0), c,
                ha="center", va="center", fontsize=7.2, fontweight="bold", color="#C00000",
                zorder=5)


def er(salida: Path):
    fig, ax = lienzo("CascoVision · Modelo entidad-relación (PostgreSQL)")

    cam = tabla(ax, 2, 77, 25, "cameras", [
        ("PK", "id", "text"), ("", "name", "text"), ("", "rtsp_url", "text"),
        ("", "location", "text"), ("", "active", "bool"), ("", "last_frame_at", "timestamptz"),
        ("", "created_at", "timestamptz")])
    zon = tabla(ax, 2, 55, 25, "zones", [
        ("PK", "id", "text"), ("FK", "camera_id", "text"), ("", "name", "text"),
        ("", "polygon", "jsonb"), ("", "suppression_s", "int = 60"), ("", "active", "bool")])
    bal = tabla(ax, 2, 33, 25, "beacons", [
        ("PK", "id", "text"), ("FK UQ", "zone_id", "text"), ("", "name", "text"),
        ("", "ip", "inet"), ("", "duration_s", "int 1–30"), ("", "sound", "text"),
        ("", "message", "varchar(40)"), ("", "online", "bool"), ("", "battery_pct", "int"),
        ("", "last_seen_at", "timestamptz")])
    inc = tabla(ax, 38, 70, 30, "incidents", [
        ("PK", "id", "uuid"), ("FK", "camera_id", "text"), ("FK", "zone_id", "text"),
        ("", "detected_at", "timestamptz"), ("", "violation_type", "text"),
        ("", "violation_types", "text[]"), ("", "confidence", "float8"),
        ("", "evidence_path", "text"), ("", "beacon_alert_status", "text"),
        ("", "beacon_alert_latency_ms", "int"), ("", "person_track_id", "int"),
        ("", "status", "text"), ("", "created_at", "timestamptz")], nueva=False)
    eve = tabla(ax, 80, 77, 27, "incident_events", [
        ("PK", "id", "bigserial"), ("FK", "incident_id", "uuid"), ("FK", "user_id", "uuid"),
        ("", "from_status", "text"), ("", "to_status", "text"), ("", "comment", "text"),
        ("", "created_at", "timestamptz")])
    usr = tabla(ax, 80, 54, 27, "users", [
        ("PK", "id", "uuid"), ("UQ", "email", "text"), ("", "full_name", "text"),
        ("", "phone", "text"), ("", "password_hash", "text"), ("", "role", "text"),
        ("", "active", "bool"), ("", "last_login_at", "timestamptz")])
    noti = tabla(ax, 80, 28, 27, "notifications", [
        ("PK", "id", "bigserial"), ("FK", "incident_id", "uuid"), ("FK", "user_id", "uuid"),
        ("", "channel", "text"), ("", "status", "text"), ("", "attempts", "int"),
        ("", "sent_at", "timestamptz"), ("", "error", "text")])
    sh = tabla(ax, 40.5, 25, 25, "shifts", [
        ("PK", "id", "smallint"), ("", "name", "text"), ("", "starts_at", "time"),
        ("", "ends_at", "time")])

    # cameras 1—N zones, zones 1—0..1 beacons
    relacion(ax, (14.5, cam[1]), (14.5, 55), "1", "N")
    relacion(ax, (14.5, zon[1]), (14.5, 33), "1", "0..1")
    # cameras y zones 1—N incidents
    relacion(ax, (27, 72), (38, 66), "1", "N")
    relacion(ax, (27, 50), (38, 62.5), "1", "N")
    # incidents 1—N incident_events / notifications
    relacion(ax, (68, 66), (80, 72), "1", "N")
    relacion(ax, (68, 52), (80, 18.5), "1", "N")
    # users 1—N incident_events / notifications
    relacion(ax, (93.5, 54), (93.5, eve[1]), "1", "N")
    relacion(ax, (93.5, usr[1]), (93.5, 28), "1", "N")
    # shifts: relación lógica por la hora de detected_at
    ax.plot([53, 53], [inc[1], 25], color=NAVY, lw=1.0, ls=(0, (3, 2)), zorder=2)
    ax.text(54, (inc[1] + 25) / 2, "por hora de detected_at\n(vista de reportes)", fontsize=6.3,
            style="italic", color="#555555", va="center")

    # leyenda
    ax.add_patch(Rectangle((40.5, 5.5), 4, 1.8, fc="#2E75B6", ec=NAVY))
    ax.text(45.3, 6.4, "tabla existente (migraciones 001 y 002)", fontsize=6.8, va="center")
    ax.add_patch(Rectangle((40.5, 2.7), 4, 1.8, fc=NAVY, ec=NAVY))
    ax.text(45.3, 3.6, "tabla nueva (migración 003, tarea 4.8)", fontsize=6.8, va="center")
    ax.text(80, 4.5, "PK clave primaria · FK clave foránea · UQ único\n1 / N / 0..1: cardinalidad",
            fontsize=6.6, va="center", color="#555555")

    fig.savefig(salida / "Diagrama_ER.png", dpi=200, bbox_inches="tight", facecolor="white")
    plt.close(fig)


if __name__ == "__main__":
    carpeta = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parent
    er(carpeta)
    print("Diagrama ER generado en", carpeta)
