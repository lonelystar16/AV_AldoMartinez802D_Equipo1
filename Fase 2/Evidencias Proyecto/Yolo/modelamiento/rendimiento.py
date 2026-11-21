"""Meta de rendimiento de los scripts de monitoreo.

El motor ya dibuja su propia linea con el FPS instantaneo del cuadro, que salta
mucho de un frame a otro. Este modulo aporta lo que a los scripts les falta: una
media movil estable, la meta de 30 FPS pintada en cada cuadro y un resumen al
terminar.

Va aparte del motor a proposito: `motor_cascovision.py` lo comparten los cuatro
scripts de monitoreo y sus pruebas no deben depender de esta metrica. Se mide
unicamente el tiempo de `MonitorEPP.procesar()`, no el de `imshow` ni el de
`waitKey`, porque lo que interesa es cuanto tarda el modelo, no la ventana.

Tambien resuelve que modelo cargar (`resolver_modelo`), porque de eso depende si
la meta se alcanza o no: el motor, por su cuenta, prefiere el `.onnx`, que en
una maquina sin el provider CUDA de ONNX Runtime corre en CPU y se queda lejos
de los 30 FPS.

    from rendimiento import MedidorFPS, dibujar_hud, resolver_modelo

    medidor = MedidorFPS(meta=30.0)
    monitor = MonitorEPP(ruta_modelo=resolver_modelo("auto"), ...)
    ...
    t0 = time.perf_counter()
    monitor.procesar(frame)
    medidor.registrar(time.perf_counter() - t0)
    ...
    dibujar_hud(frame, medidor)
"""

from __future__ import annotations

import time
from collections import deque
from pathlib import Path

import cv2

# Meta por defecto del proyecto y ventana de la media movil. Treinta cuadros es
# un segundo de margen: suficiente para que la cifra no baile, poco como para
# reaccionar tarde si el modelo cae.
FPS_OBJETIVO = 30.0
VENTANA_MEDIA = 30

# Cuadros de arranque que quedan fuera de las estadisticas. La primera
# inferencia arrastra la carga del modelo y la inicializacion de la GPU, que no
# se repite en los cuadros siguientes: contarla hundiria el promedio de una
# corrida que si sostiene la meta, y el resumen terminaria diciendo que no se
# llega aunque todos los cuadros la cumplan.
CALENTAMIENTO = 10

# El motor pinta su linea en (10, 25); esta va debajo para no encimarse.
POSICION_HUD = (10, 50)
ESCALA_HUD = 0.6
GROSOR_HUD = 2

FONT = cv2.FONT_HERSHEY_SIMPLEX
COLOR_CONTORNO = (0, 0, 0)
COLOR_OK = (80, 220, 80)        # verde
COLOR_BAJO = (0, 165, 255)      # ambar
COLOR_CRITICO = (60, 60, 230)   # rojo

# Fraccion de la meta que se acepta como sano. Por debajo de 90% se marca BAJO
# y por debajo de 70% CRITICO, para que el aviso distinga una caida leve de un
# modelo que ya no da abasto.
UMBRAL_OK = 0.90
UMBRAL_CRITICO = 0.70


class MedidorFPS:
    """Acumula el tiempo de procesamiento de cada cuadro y lo resume.

    Solo cuenta el trabajo del modelo. El pintado de la ventana y la espera de
    `waitKey` quedan fuera a proposito: inflarian la cifra sin decir nada sobre
    el detector.
    """

    def __init__(self, meta: float = FPS_OBJETIVO, ventana: int = VENTANA_MEDIA,
                 calentamiento: int = CALENTAMIENTO):
        if meta <= 0:
            raise ValueError("La meta de FPS debe ser mayor que cero")
        self.meta = float(meta)
        self.ventana = max(1, int(ventana))
        self._calentamiento = max(0, int(calentamiento))
        self._duraciones: deque[float] = deque(maxlen=self.ventana)
        self._acumulado = 0.0
        self._cuadros = 0
        self._cumplen = 0
        self._minimo = float("inf")
        self._maximo = 0.0
        # Tiempo y cuadros del arranque, apartados de todo lo demas.
        self._arranque_cuadros = 0
        self._arranque_s = 0.0
        self._inicio = time.perf_counter()

    def registrar(self, duracion: float) -> None:
        """Anota el tiempo en segundos que tardo procesar un cuadro.

        Los primeros `calentamiento` cuadros se apartan: la primera inferencia
        arrastra la carga del modelo y la inicializacion de la GPU, que no se
        repite despues. Contarlos hundiria el promedio de una corrida que si
        sostiene la meta.
        """
        if duracion <= 0:
            return
        if self._arranque_cuadros < self._calentamiento:
            self._arranque_cuadros += 1
            self._arranque_s += duracion
            return
        self._duraciones.append(duracion)
        self._acumulado += duracion
        self._cuadros += 1
        fps = 1.0 / duracion
        if fps < self._minimo:
            self._minimo = fps
        if fps > self._maximo:
            self._maximo = fps
        if fps >= self.meta:
            self._cumplen += 1

    @property
    def actual(self) -> float:
        """FPS suavizados de los ultimos cuadros de la ventana."""
        if not self._duraciones:
            return 0.0
        media = sum(self._duraciones) / len(self._duraciones)
        return 1.0 / media if media > 0 else 0.0

    @property
    def promedio(self) -> float:
        """FPS promedio de toda la corrida, no solo de la ventana."""
        if not self._cuadros or self._acumulado <= 0:
            return 0.0
        return self._cuadros / self._acumulado

    @property
    def porcentaje_cumplen(self) -> float:
        """Porcentaje de cuadros que alcanzaron la meta."""
        if not self._cuadros:
            return 0.0
        return 100.0 * self._cumplen / self._cuadros

    @property
    def cuadros(self) -> int:
        return self._cuadros

    def estado(self) -> tuple[str, tuple[int, int, int]]:
        """Etiqueta y color del HUD segun lo lejos que se este de la meta."""
        actual = self.actual
        if actual <= 0 or not self._cuadros:
            return "SIN DATOS", COLOR_BAJO
        razon = actual / self.meta
        if razon >= UMBRAL_OK:
            return "OK", COLOR_OK
        if razon >= UMBRAL_CRITICO:
            return "BAJO", COLOR_BAJO
        return "CRITICO", COLOR_CRITICO

    def resumen(self) -> dict:
        """Cifras de cierre, por si el caller quiere guardarlas o imprimirlas."""
        minimo = 0.0 if self._minimo == float("inf") else self._minimo
        return {
            "meta": self.meta,
            "cuadros": self._cuadros,
            "promedio": self.promedio,
            "ventana": self.actual,
            "minimo": minimo,
            "maximo": self._maximo,
            "porcentaje_cumplen": self.porcentaje_cumplen,
            "arranque_cuadros": self._arranque_cuadros,
            "arranque_s": self._arranque_s,
            "duracion_s": time.perf_counter() - self._inicio,
            "cumple": self.promedio >= self.meta,
        }

    def linea_resumen(self) -> str:
        """Resumen en una linea para la consola al terminar."""
        if not self._cuadros:
            if self._arranque_cuadros:
                unidad_arranque = ("cuadro" if self._arranque_cuadros == 1
                                   else "cuadros")
                return (f"Rendimiento: solo {self._arranque_cuadros} "
                        f"{unidad_arranque} de arranque "
                        f"({self._arranque_s:.1f} s); sin datos sostenidos.")
            return "Rendimiento: sin cuadros procesados."

        cifras = self.resumen()
        unidad = "cuadro" if self._cuadros == 1 else "cuadros"
        arranque = ""
        if self._arranque_cuadros:
            arranque = (f" | arranque {self._arranque_s:.1f} s en "
                        f"{self._arranque_cuadros} "
                        f"{'cuadro' if self._arranque_cuadros == 1 else 'cuadros'} "
                        "apartados")
        linea = (
            f"Rendimiento: {cifras['promedio']:.1f} FPS promedio "
            f"(min {cifras['minimo']:.1f}, max {cifras['maximo']:.1f}) | "
            f"meta {self.meta:.0f} | "
            f"{cifras['porcentaje_cumplen']:.0f}% de {self._cuadros} {unidad} "
            f"la alcanzan{arranque}"
        )
        if cifras["cumple"]:
            return linea + " | CUMPLE"
        return linea + " | NO CUMPLE"


def dibujar_hud(frame, medidor: MedidorFPS) -> None:
    """Pinta la meta de FPS sobre el cuadro, debajo de la linea del motor."""
    etiqueta, color = medidor.estado()
    cadena = f"FPS {medidor.actual:5.1f} | meta {medidor.meta:.0f} | {etiqueta}"
    x, y = POSICION_HUD
    # Doble pasada: primero el contorno negro y encima el color, para que se lea
    # igual de bien sobre un fondo claro que sobre uno oscuro.
    cv2.putText(frame, cadena, (x, y), FONT, ESCALA_HUD, COLOR_CONTORNO,
                GROSOR_HUD + 2, cv2.LINE_AA)
    cv2.putText(frame, cadena, (x, y), FONT, ESCALA_HUD, color,
                GROSOR_HUD, cv2.LINE_AA)


# ---------- modelo ----------

OPCIONES_MODELO = ("auto", "onnx", "pt")
CARPETA_MODELO = Path(__file__).resolve().parents[2] / "models"
RUTA_MODELO_ONNX = CARPETA_MODELO / "cascovision_yolo26s.onnx"
RUTA_MODELO_PT = CARPETA_MODELO / "cascovision_yolo26s.pt"


def resolver_modelo(opcion: str) -> Path | None:
    """Traduce la opcion `--modelo` en la ruta que `MonitorEPP` debe cargar.

    `auto` devuelve `None`, que el motor interpreta como "elige tu": primero el
    `.onnx` si existe, si no el `.pt`. Es exactamente el comportamiento de
    siempre, sin ninguna diferencia.

    `onnx` y `pt` fuerzan un modelo concreto. Conviene poder forzarlo porque de
    ahi depende la meta de 30 FPS: si el provider CUDA de ONNX Runtime no esta
    disponible, el `.onnx` corre en CPU y no llega, mientras que el `.pt` usa la
    GPU de PyTorch.
    """
    if opcion == "auto":
        return None
    ruta = RUTA_MODELO_ONNX if opcion == "onnx" else RUTA_MODELO_PT
    if not ruta.is_file():
        raise SystemExit(f"Modelo: no existe {ruta}.")
    return ruta
