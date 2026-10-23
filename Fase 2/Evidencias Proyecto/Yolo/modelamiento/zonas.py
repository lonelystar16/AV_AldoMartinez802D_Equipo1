"""Zonas de riesgo: carga, validación y prueba de "está dentro".

Una zona es un polígono en coordenadas relativas al frame (0..1), así que la
misma configuración sirve para cualquier resolución y para cualquier cámara.

El lugar de una persona son sus pies: el centro inferior de su caja, es decir
lo que está pisando. No el centro del torso, que se corre hacia arriba si la
cámara encuadra más alto, o hacia abajo si encuadra más bajo, y haría que una
misma persona entrase y saliese de la zona sin moverse.

Si la configuración está mal se falla al arrancar. Un agente que nunca avisa
porque su JSON no se entendió es peor que un agente caído: nadie se entera.
"""

import json
import math
from pathlib import Path


class ErrorZonas(ValueError):
    """La configuración de zonas no se pudo entender."""


# Distancia, en unidades relativas, con la que un punto cuenta como caído
# exactamente sobre un borde. Solo sirve para dar estabilidad a la comparación
# de flotantes: nadie dibuja zonas con esa precisión.
TOLERANCIA = 1e-9


def _sobre_segmento(punto, a, b):
    """¿El punto yace sobre el segmento a-b?"""
    px, py = punto
    ax, ay = a
    bx, by = b
    dx, dy = bx - ax, by - ay
    largo = math.hypot(dx, dy)
    if largo < TOLERANCIA:
        return math.hypot(px - ax, py - ay) <= TOLERANCIA
    # Producto vectorial nulo: las tres puntos son colineales.
    cruzado = (px - ax) * dy - (py - ay) * dx
    if abs(cruzado) / largo > TOLERANCIA:
        return False
    # Colineal: falta comprobar que está entre los extremos y no en su prolongación.
    dentro = (px - ax) * dx + (py - ay) * dy
    return -TOLERANCIA <= dentro <= largo * largo + TOLERANCIA


def punto_en_poligono(punto, poligono):
    """¿El punto está dentro del polígono? Los bordes cuentan como dentro.

    Cuenta los cruces de un rayo horizontal hacia la derecha. Lo de incluir el
    borde es una decisión, no un detalle: alguien con los pies exactamente
    sobre la línea de la zona está dentro de ella, y esa persona no debe quedar
    sin reportar por un píxel de diferencia al dibujar el polígono.
    """
    if not poligono or len(poligono) < 3:
        return False

    if any(_sobre_segmento(punto, poligono[i], poligono[(i + 1) % len(poligono)])
           for i in range(len(poligono))):
        return True

    x, y = punto
    dentro = False
    for i in range(len(poligono)):
        x1, y1 = poligono[i]
        x2, y2 = poligono[(i + 1) % len(poligono)]
        if (y1 > y) != (y2 > y):
            cruce = (x2 - x1) * (y - y1) / (y2 - y1) + x1
            if x < cruce:
                dentro = not dentro
    return dentro


def _area(poligono):
    """Área por la fórmula del zapatero; sirve para descartar polígonos degenerados."""
    total = 0.0
    for i in range(len(poligono)):
        x1, y1 = poligono[i]
        x2, y2 = poligono[(i + 1) % len(poligono)]
        total += x1 * y2 - x2 * y1
    return abs(total) / 2.0


def zona_de(caja, zonas, ancho, alto):
    """Zona donde están los pies de la persona, o `None` si está fuera de toda zona.

    La caja viene en píxeles y el polígono en relativo, así que aquí se pasa de
    una a otra: `ancho` y `alto` son las dimensiones del frame.
    """
    if not zonas or caja is None:
        return None
    x1, y1, x2, y2 = caja
    pies = ((x1 + x2) / 2.0 / ancho, float(y2) / alto)
    for zona in zonas:
        if punto_en_poligono(pies, zona["poligono"]):
            return zona["id"]
    return None


def _validar_zona(camara, indice, zona, vistos):
    donde = f"la zona {indice} de '{camara}'"
    if not isinstance(zona, dict):
        raise ErrorZonas(f"{donde} debe ser un objeto, no {type(zona).__name__}.")

    identificador = zona.get("id")
    if not isinstance(identificador, str) or not identificador.strip():
        raise ErrorZonas(f"{donde} no tiene un 'id' de texto.")
    if identificador in vistos:
        raise ErrorZonas(f"'{camara}' usa el id '{identificador}' dos veces.")
    vistos.add(identificador)

    poligono = zona.get("poligono")
    if not isinstance(poligono, list) or len(poligono) < 3:
        raise ErrorZonas(
            f"'{identificador}' necesita al menos 3 vértices en 'poligono'.")

    normalizado = []
    for vertice in poligono:
        if (not isinstance(vertice, (list, tuple)) or len(vertice) != 2
                or not all(isinstance(v, (int, float)) and not isinstance(v, bool)
                           for v in vertice)):
            raise ErrorZonas(
                f"'{identificador}' tiene un vértice que no es un par de números.")
        x, y = float(vertice[0]), float(vertice[1])
        if not (0.0 <= x <= 1.0 and 0.0 <= y <= 1.0):
            raise ErrorZonas(
                f"'{identificador}' tiene el vértice [{x}, {y}] fuera del rango "
                f"0..1. Las coordenadas son relativas al frame.")
        normalizado.append((x, y))

    if _area(normalizado) <= TOLERANCIA:
        raise ErrorZonas(
            f"'{identificador}' no encierra área: sus vértices están todos alineados.")

    baliza = zona.get("baliza")
    if baliza is not None and not isinstance(baliza, str):
        raise ErrorZonas(f"'{identificador}' tiene una 'baliza' que no es texto.")

    return {"id": identificador, "poligono": normalizado, "baliza": baliza}


def cargar_zonas(ruta):
    """Lee y valida `config/zonas.json`. Devuelve `{camera_id: [zona, ...]}`.

    Falla con `ErrorZonas` ante cualquier problema: archivo ausente, JSON roto,
    vértices fuera de rango, ids repetidos. Nunca devuelve una lista vacía, que
    se confundiría con "esta cámara no vigila nada".
    """
    ruta = Path(ruta)
    if not ruta.is_file():
        raise ErrorZonas(
            f"No existe {ruta}. Copia 'zonas.json.example' y edita las zonas reales.")

    try:
        crudo = json.loads(ruta.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise ErrorZonas(f"{ruta} no es JSON válido: {error}") from error

    if not isinstance(crudo, dict) or not crudo:
        raise ErrorZonas(
            f"{ruta} debe ser un objeto con una entrada por cámara, por ejemplo "
            f'{{"camara-01": [ ... ]}}.')

    config = {}
    for camara, zonas in crudo.items():
        if not isinstance(camara, str) or not camara.strip():
            raise ErrorZonas("Hay una cámara sin nombre en la configuración.")
        if not isinstance(zonas, list) or not zonas:
            raise ErrorZonas(
                f"La cámara '{camara}' no tiene zonas. Cada cámara necesita al "
                f"menos una zona con su 'id' y su 'poligono'.")
        vistos = set()
        config[camara] = [_validar_zona(camara, i, z, vistos)
                          for i, z in enumerate(zonas)]
    return config


# ---------- avisos de dibujo ----------

def _orientacion(a, b, c):
    return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])


def _aristas_se_cruzan(a, b, c, d):
    """Cruce propio de dos segmentos. Compartir un extremo no cuenta."""
    o1, o2 = _orientacion(a, b, c), _orientacion(a, b, d)
    o3, o4 = _orientacion(c, d, a), _orientacion(c, d, b)
    return o1 * o2 < 0 and o3 * o4 < 0


def _sobre_poligono(punto, poligono):
    return any(_sobre_segmento(punto, poligono[i], poligono[(i + 1) % len(poligono)])
               for i in range(len(poligono)))


def _poligonos_solapan(a, b):
    """Un vértice estrictamente dentro del otro, o aristas que se cruzan."""
    if any(punto_en_poligono(p, b) and not _sobre_poligono(p, b) for p in a):
        return True
    if any(punto_en_poligono(p, a) and not _sobre_poligono(p, a) for p in b):
        return True
    return any(_aristas_se_cruzan(a[i], a[(i + 1) % len(a)], b[j], b[(j + 1) % len(b)])
               for i in range(len(a)) for j in range(len(b)))


def comprobar_solapes(zonas):
    """Avisos, sin cortar nada, de zonas que se pisan entre sí.

    Alguien parado en el solape siempre cae en la primera zona de la lista. Sin
    este aviso eso se convierte en un misterio cada vez que se pregunte por qué
    un incidente salió con la zona que salió.
    """
    avisos = []
    for i, a in enumerate(zonas):
        for b in zonas[i + 1:]:
            if _poligonos_solapan(a["poligono"], b["poligono"]):
                avisos.append(
                    f"las zonas '{a['id']}' y '{b['id']}' se solapan; gana "
                    f"'{a['id']}' por aparecer antes.")
    return avisos
