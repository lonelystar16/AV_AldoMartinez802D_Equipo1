"""Mediciones de punta a punta del D3 sobre el stack `docker compose --profile dev`.

Uso (desde Fase 2/Evidencias Proyecto, con el stack arriba):
    python e2e_mediciones.py muestrear <minutos> <salida_dir>   # PS-08: conexiones salientes
    python e2e_mediciones.py medir <salida_dir>                  # PR-01, PR-05, PS-07

Proyecto compose: variable CV_PROYECTO (por defecto cv-entrega).
"""
import ipaddress
import json
import os
import statistics
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

P = os.environ.get("CV_PROYECTO", "cv-entrega")
# CV_ARCHIVOS: archivos de compose separados por ";" (por defecto, el compose.yaml del directorio).
ARCHIVOS = [a for a in os.environ.get("CV_ARCHIVOS", "").split(";") if a]
DC = ["docker", "compose", "-p", P, *[x for a in ARCHIVOS for x in ("-f", a)], "--profile", "dev"]
SERVICIOS_MUESTREO = os.environ.get("CV_SERVICIOS", "api,edge,receptor-sim").split(",")


def sh(args, **kw):
    return subprocess.run(args, capture_output=True, text=True, encoding="utf-8", check=True, **kw).stdout


def psql(sql):
    out = sh(DC + ["exec", "-T", "db", "psql", "-U", "cascovision", "-d", "cascovision", "-At", "-F", "\t", "-c", sql])
    return [l.split("\t") for l in out.strip().splitlines() if l]


def ts(s):
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


def p95(xs):
    xs = sorted(xs)
    return xs[max(0, int(round(0.95 * len(xs))) - 1)]


# --- PS-08: conexiones TCP establecidas hacia fuera de la red local --------------
LEER_TCP = (
    "import socket,struct\n"
    "def ip4(h):return socket.inet_ntoa(struct.pack('<I',int(h,16)))\n"
    "def ip6(h):\n"
    " b=bytes.fromhex(h);b=b''.join(b[i:i+4][::-1] for i in range(0,16,4));return socket.inet_ntop(socket.AF_INET6,b)\n"
    "for f,c in (('/proc/net/tcp',ip4),('/proc/net/tcp6',ip6)):\n"
    " try:\n"
    "  for l in open(f).read().splitlines()[1:]:\n"
    "   p=l.split();\n"
    "   if p[3]=='01':a,pt=p[2].split(':');print(c(a),int(pt,16))\n"
    " except FileNotFoundError:pass\n"
)


def muestrear(minutos, salida):
    servicios = SERVICIOS_MUESTREO
    externas, muestras = {}, 0
    fin = time.time() + minutos * 60
    while time.time() < fin:
        for s in servicios:
            try:
                out = sh(DC + ["exec", "-T", s, "python", "-c", LEER_TCP])
            except subprocess.CalledProcessError:
                continue
            for l in out.splitlines():
                ip, puerto = l.split()
                a = ipaddress.ip_address(ip)
                if getattr(a, "ipv4_mapped", None):
                    a = a.ipv4_mapped
                if not (a.is_private or a.is_loopback or a.is_link_local):
                    externas.setdefault(f"{s} -> {a}:{puerto}", 0)
                    externas[f"{s} -> {a}:{puerto}"] += 1
        muestras += 1
        time.sleep(5)
    r = {"minutos": minutos, "muestras": muestras, "conexiones_externas": externas}
    Path(salida, "ps08.json").write_text(json.dumps(r, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(r, ensure_ascii=False))


# --- PR-01, PR-05, PS-07 ------------------------------------------------------
def medir(salida):
    salida = Path(salida)
    res = {}

    # PR-01: detección (detected_at del incidente) -> llegada a la baliza (received_at).
    alertas = [json.loads(l) for l in sh(DC + ["exec", "-T", "receptor-sim", "cat", "/data/alerts.jsonl"]).splitlines() if l.strip()]
    # Sin los incidentes ficticios del seed (evidencia demo/...).
    inc = psql("select detected_at, beacon_alert_latency_ms, beacon_alert_status from incidents "
               "where beacon_alert_status='alerted' and evidence_path not like 'demo/%' order by detected_at")
    detecciones = sorted(ts(d.replace(" ", "T")) for d, _, _ in inc)
    orden = [(ts(a["received_at"]) - ts(a["order"]["sent_at"])).total_seconds() * 1000 for a in alertas]
    # Solo el «inicio» trae la hora del cuadro (detected_at); los avisos repetidos
    # reusan el incidente. Cada inicio se empareja con la primera orden posterior.
    por_envio = sorted(alertas, key=lambda a: ts(a["order"]["sent_at"]))
    e2e = []
    for d in detecciones:
        sig = next((a for a in por_envio if ts(a["order"]["sent_at"]) >= d), None)
        if sig:
            e2e.append((ts(sig["received_at"]) - d).total_seconds())
    lat_agente = [int(l) for _, l, _ in inc if l]
    res["PR-01"] = {
        "ordenes_recibidas": len(alertas),
        "deteccion_a_baliza_s": {"n": len(e2e), "mediana": statistics.median(e2e) if e2e else None,
                                  "p95": p95(e2e) if e2e else None, "max": max(e2e) if e2e else None},
        "envio_a_llegada_ms": {"mediana": statistics.median(orden) if orden else None, "p95": p95(orden) if orden else None},
        "latencia_informada_por_agente_ms": {"n": len(lat_agente), "mediana": statistics.median(lat_agente) if lat_agente else None,
                                             "p95": p95(lat_agente) if lat_agente else None},
        "criterio": "< 5 s en el 95 %",
    }
    res["PR-01"]["aprobado"] = bool(e2e) and p95(e2e) < 5

    # PR-05: creación del incidente en la API -> correo en Mailpit.
    import urllib.request
    msgs = json.load(urllib.request.urlopen("http://127.0.0.1:8025/api/v1/messages?limit=500"))["messages"]
    creados = sorted(ts(c.replace(" ", "T")) for (c,) in psql("select created_at from incidents order by created_at"))
    lat_correo = []
    for m in msgs:
        llegada = ts(m["Created"])
        previas = [c for c in creados if c <= llegada]
        if previas:
            lat_correo.append((llegada - previas[-1]).total_seconds())
    res["PR-05"] = {"correos": len(msgs), "incidentes": len(creados),
                    "incidente_a_correo_s": {"n": len(lat_correo), "mediana": statistics.median(lat_correo) if lat_correo else None,
                                             "p95": p95(lat_correo) if lat_correo else None, "max": max(lat_correo) if lat_correo else None},
                    "criterio": "<= 30 s"}
    res["PR-05"]["aprobado"] = bool(lat_correo) and max(lat_correo) <= 30
    estados = psql("select status, count(*) from notifications group by status")
    res["PR-05"]["notifications"] = {s: int(n) for s, n in estados}

    # PS-07: bandera face_blurred en la base (la revisión de imágenes se hace aparte).
    fb = psql("select face_blurred, count(*) from incidents group by face_blurred")
    res["PS-07_db"] = {s: int(n) for s, n in fb}

    (salida / "e2e.json").write_text(json.dumps(res, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    print(json.dumps(res, indent=2, ensure_ascii=False, default=str))


if __name__ == "__main__":
    if sys.argv[1] == "muestrear":
        muestrear(float(sys.argv[2]), sys.argv[3])
    else:
        medir(sys.argv[2])
