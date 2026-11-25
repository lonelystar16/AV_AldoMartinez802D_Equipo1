"""PS-01 a PS-05 y PS-09 del D3 contra el stack en vivo (perfil dev).

Uso (desde Fase 2/Evidencias Proyecto): python seguridad_vivo.py
Lee las credenciales de .env sin imprimirlas.
"""
import base64
import json
import re
import secrets
import subprocess
import urllib.error
import urllib.parse
import urllib.request

ENV = dict(re.findall(r"^([A-Z_]+)=(.*)$", open(".env", encoding="utf-8").read(), re.M))
API = "http://127.0.0.1:8000"
res = []


def pedir(url, metodo="GET", cuerpo=None, token=None):
    h = {"Content-Type": "application/json"}
    if token:
        h["Authorization"] = f"Bearer {token}"
    r = urllib.request.Request(url, data=json.dumps(cuerpo).encode() if cuerpo is not None else None,
                               headers=h, method=metodo)
    try:
        with urllib.request.urlopen(r, timeout=10) as x:
            return x.status, x.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()


def caso(id_, desc, ok, detalle):
    res.append((id_, desc, "APROBADO" if ok else "NO APROBADO", detalle))


def login(correo, clave):
    s, b = pedir(API + "/auth/login", "POST", {"email": correo, "password": clave})
    assert s == 200, (s, b)
    return json.loads(b)["access_token"]


admin = login(ENV["CASCOVISION_ADMIN_EMAIL"], ENV["CASCOVISION_ADMIN_PASSWORD"])

# Supervisor de prueba para PS-02.
clave_sup = secrets.token_urlsafe(16)
correo_sup = f"supervisor.{secrets.token_hex(3)}@cascovision.local"
s, _ = pedir(API + "/users", "POST", {"email": correo_sup, "full_name": "Supervisor de prueba",
                                      "role": "supervisor", "password": clave_sup}, admin)
assert s == 201, s
sup = login(correo_sup, clave_sup)

# PS-01: sin JWT, JWT con firma alterada, token del agente en ruta del dashboard.
cab, carga, firma = admin.split(".")
alterado = f"{cab}.{carga}.{firma[:-4]}{'AAAA' if not firma.endswith('AAAA') else 'BBBB'}"
r1 = [pedir(API + "/incidents")[0], pedir(API + "/incidents", token=alterado)[0],
      pedir(API + "/incidents", token=ENV["EDGE_API_TOKEN"])[0]]
caso("PS-01", "Rutas sin JWT, con firma alterada o con el token del agente", r1 == [401, 401, 401], f"respuestas {r1}")

# PS-02: supervisor intenta crear un usuario y modificar una baliza.
r2 = [pedir(API + "/users", "POST", {"email": "x.y@cascovision.local", "full_name": "X", "role": "admin",
                                     "password": secrets.token_urlsafe(16)}, sup)[0],
      pedir(API + "/beacons/baliza-01", "PUT", {"ip": "192.0.2.50"}, sup)[0]]
caso("PS-02", "Supervisor crea usuario o modifica baliza", r2 == [403, 403], f"respuestas {r2}")

# PS-03: evidencia sin JWT.
s, b = pedir(API + "/incidents?limit=1", token=admin)
inc = json.loads(b)[0]["id"]
r3 = pedir(API + f"/incidents/{inc}/evidence")[0]
caso("PS-03", "Evidencia de un incidente sin JWT", r3 == 401, f"respuesta {r3}")

# PS-04: orden a la baliza simulada sin token y con token incorrecto.
orden = {"alert_id": "ps04", "zone_id": "zona-norte", "zone_name": "Z", "violations": ["missing_helmet"],
         "duration_s": 1, "sound": "siren", "sent_at": "2026-11-25T00:00:00Z"}
r4 = [pedir("http://127.0.0.1:8081/alert", "POST", orden)[0],
      pedir("http://127.0.0.1:8081/alert", "POST", orden, token="x" * 40)[0]]
caso("PS-04", "POST /alert sin token o con token incorrecto", r4 == [401, 401], f"respuestas {r4}")

# PS-05: inyección SQL en los filtros.
iny = urllib.parse.quote("' OR 1=1 --")
s1, b1 = pedir(API + f"/incidents?zone_id={iny}", token=admin)
s2, b2 = pedir(API + f"/reports?zone_id={iny}", token=admin)
filas = len(json.loads(b1)) if s1 == 200 else None
caso("PS-05", "zone_id=' OR 1=1 -- en /incidents y /reports", s1 == 200 and filas == 0 and s2 < 500,
     f"/incidents {s1} con {filas} filas; /reports {s2}")

# PS-09: contraseñas como hash bcrypt.
out = subprocess.run(["docker", "compose", "-p", "cv-entrega", "--profile", "dev", "exec", "-T", "db", "psql",
                      "-U", "cascovision", "-d", "cascovision", "-At", "-c",
                      "select count(*), count(*) filter (where password_hash ~ '^\\$2[aby]\\$') from users"],
                     capture_output=True, text=True, check=True).stdout.strip()
total, bc = map(int, out.split("|"))
caso("PS-09", "Contraseñas en la tabla users", total == bc and total > 0, f"{bc} de {total} con hash bcrypt")

for r in res:
    print(" | ".join(r))
