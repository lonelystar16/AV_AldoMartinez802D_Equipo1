#!/bin/sh
# PS-08 / DEF-06: arranca el agente N veces y registra cada 0,1 s las conexiones TCP
# hacia fuera de la red local, desde el mismo contenedor.
# Uso: sh ps08_arranques.sh <veces> <segundos_por_arranque>
N="$1"; T="$2"
python - <<'PY' &
import ipaddress, socket, struct, time
def ip4(h): return socket.inet_ntoa(struct.pack("<I", int(h, 16)))
def ip6(h):
    b = bytes.fromhex(h); b = b"".join(b[i:i + 4][::-1] for i in range(0, 16, 4))
    return socket.inet_ntop(socket.AF_INET6, b)
vistas = set()
with open("/tmp/externas.txt", "w") as salida:
    while True:
        for f, conv in (("/proc/net/tcp", ip4), ("/proc/net/tcp6", ip6)):
            try:
                lineas = open(f).read().splitlines()[1:]
            except FileNotFoundError:
                continue
            for l in lineas:
                p = l.split()
                if p[3] not in ("01", "02"):  # ESTABLISHED o SYN_SENT
                    continue
                a, pt = p[2].split(":")
                ip = ipaddress.ip_address(conv(a))
                ip = getattr(ip, "ipv4_mapped", None) or ip
                if not (ip.is_private or ip.is_loopback or ip.is_link_local):
                    clave = f"{ip}:{int(pt, 16)}"
                    if clave not in vistas:
                        vistas.add(clave); salida.write(clave + "\n"); salida.flush()
        time.sleep(0.1)
PY
MUESTREO=$!
i=0
while [ "$i" -lt "$N" ]; do
  i=$((i + 1))
  timeout "$T" python "/app/Fase 2/Evidencias Proyecto/src/edge/agente.py" --config /config/edge.json --sin-ventana >/dev/null 2>&1
done
sleep 2
kill "$MUESTREO" 2>/dev/null
echo "arranques=$N externas=$(wc -l < /tmp/externas.txt)"
cat /tmp/externas.txt
