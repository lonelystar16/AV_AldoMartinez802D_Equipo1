"""PR-02 del D3: cuadros analizados por segundo en cada agente, con 4 cámaras a la vez.

Corre DENTRO de cada contenedor edge (python -c o archivo copiado): cuenta cuántas veces
cambia /data/edge/ultimo_cuadro.jpg, que el agente reescribe en cada cuadro analizado.
Uso: python pr02_tasa.py <segundos>
"""
import os
import sys
import time

duracion = float(sys.argv[1])
ruta = "/data/edge/ultimo_cuadro.jpg"
previo, cambios = None, 0
inicio = time.monotonic()
while time.monotonic() - inicio < duracion:
    try:
        m = os.stat(ruta).st_mtime_ns
    except FileNotFoundError:
        m = None
    if m is not None and m != previo:
        if previo is not None:
            cambios += 1
        previo = m
    time.sleep(0.05)
print(f"{cambios} cuadros en {duracion:.0f} s = {cambios / duracion:.3f} cuadros/s")
