"""Pruebas de las reglas de negocio del motor de detección de EPP.

El motor decide si una persona lleva casco y chaleco a partir de las clases
que detecta el modelo. Con el detector de 5 clases, las infracciones se
declaran de forma positiva (`no_helmet`, `no_vest`), en vez de inferirse por la
ausencia de un casco.

Estas pruebas no cargan el modelo: ejercitan la lógica pura.
"""

import sys
from pathlib import Path

import pytest

MOTOR = Path(__file__).parents[1] / "Yolo" / "testing y modelamiento"
sys.path.insert(0, str(MOTOR))

from motor_cascovision import (  # noqa: E402
    ESTADOS_INFRACCION,
    POLITICA_SIN_DATOS,
    MonitorEPP,
    clave_violacion,
    confirmar_infracciones,
    evaluar_persona,
    solapamiento,
)


def epp(nombre, confianza=0.9, caja=(0, 0, 10, 10)):
    """Construye una deteccion de EPP como la produce `_detectar`."""
    return {"nombre": nombre, "conf": confianza, "caja": caja, "id": 1}


# ---------- regla de casco ----------

def test_helmet_detectado_cumple_casco() -> None:
    estado = evaluar_persona([epp("helmet")])
    assert "falta_casco" not in estado
    assert "sin_casco" not in estado


def test_no_helmet_detectado_es_infraccion() -> None:
    estado = evaluar_persona([epp("no_helmet")])
    assert "sin_casco" in estado
    assert "falta_casco" not in estado


def test_sin_deteccion_en_cabeza_queda_indeterminado() -> None:
    estado = evaluar_persona([epp("vest")])
    assert "falta_casco" in estado
    assert "sin_casco" not in estado


def test_choque_entre_helmet_y_no_helmet_lo_gana_el_mas_confiable() -> None:
    estado = evaluar_persona([epp("helmet", 0.9), epp("no_helmet", 0.4)])
    assert "falta_casco" not in estado
    assert "sin_casco" not in estado

    estado = evaluar_persona([epp("helmet", 0.4), epp("no_helmet", 0.9)])
    assert "sin_casco" in estado


# ---------- regla de chaleco ----------

def test_vest_detectado_cumple_chaleco() -> None:
    estado = evaluar_persona([epp("vest")])
    assert "falta_chaleco" not in estado
    assert "sin_chaleco" not in estado


def test_no_vest_detectado_es_infraccion() -> None:
    estado = evaluar_persona([epp("no_vest")])
    assert "sin_chaleco" in estado


def test_casco_y_chaleco_se_evaluan_independientemente() -> None:
    estado = evaluar_persona([epp("helmet"), epp("no_vest")])
    assert "falta_casco" not in estado
    assert "sin_chaleco" in estado

    estado = evaluar_persona([epp("no_helmet"), epp("vest")])
    assert "sin_casco" in estado
    assert "falta_chaleco" not in estado


def test_persona_completa_no_genera_infracciones() -> None:
    estado = evaluar_persona([epp("helmet"), epp("vest")])
    assert estado == frozenset()


# ---------- politica ante estados indeterminados ----------

def test_politica_por_defecto_es_conservadora() -> None:
    assert POLITICA_SIN_DATOS == "infraccion"


def test_politica_infraccion_notifica_los_indeterminados(monkeypatch) -> None:
    monkeypatch.setattr("motor_cascovision.POLITICA_SIN_DATOS", "infraccion")
    estado = evaluar_persona([])
    assert confirmar_infracciones(estado) == estado


def test_politica_cumple_solo_notifica_infracciones_confirmadas(monkeypatch) -> None:
    monkeypatch.setattr("motor_cascovision.POLITICA_SIN_DATOS", "cumple")
    estado = evaluar_persona([])
    assert confirmar_infracciones(estado) == frozenset()

    confirmado = evaluar_persona([epp("no_helmet"), epp("no_vest")])
    assert confirmar_infracciones(confirmado) == confirmado


# ---------- clave semantica ----------

def test_clave_violacion_agrupa_los_dos_estados_de_una_infraccion() -> None:
    """falta_casco y sin_casco son la misma falta: no deben duplicar avisos."""
    assert clave_violacion(frozenset({"falta_casco"})) == \
        clave_violacion(frozenset({"sin_casco"}))
    assert clave_violacion(frozenset({"falta_casco"})) == ("missing_helmet",)
    assert clave_violacion(frozenset({"sin_chaleco"})) == ("missing_reflective_vest",)


def test_clave_violacion_ordena_estados() -> None:
    a = clave_violacion(frozenset({"sin_casco", "sin_chaleco"}))
    b = clave_violacion(frozenset({"sin_chaleco", "sin_casco"}))
    assert a == b


# ---------- utilidades ----------

def test_solapamiento_mide_fraccion_contenida() -> None:
    # Caja totalmente dentro del contenedor.
    assert solapamiento((0, 0, 10, 10), (0, 0, 20, 20)) == pytest.approx(1.0)
    # Caja sin intersección.
    assert solapamiento((100, 100, 110, 110), (0, 0, 20, 20)) == 0.0


def test_estados_de_infraccion_estan_declarados() -> None:
    assert ESTADOS_INFRACCION == {"sin_casco", "sin_chaleco"}


# ---------- asociacion del EPP con la persona ----------

def test_solo_se_asocian_los_elementos_dentro_de_la_persona() -> None:
    """El EPP de otra persona no debe contarse como infraccion de esta."""
    persona = {"nombre": "Person", "conf": 0.9, "caja": (100, 100, 300, 400), "id": 1}
    epps = [
        epp("no_helmet", caja=(150, 110, 220, 160)),
        epp("no_vest", caja=(130, 200, 280, 330)),
        # Fuera de la persona: pertenece a otra.
        epp("helmet", caja=(500, 500, 600, 600)),
    ]
    partes = MonitorEPP._partes_de(epps, persona)
    assert sorted(p["nombre"] for p in partes) == ["no_helmet", "no_vest"]


def test_persona_con_casco_y_chaleco_cumple() -> None:
    persona = {"nombre": "Person", "conf": 0.9, "caja": (0, 0, 400, 500), "id": 2}
    epps = [
        epp("helmet", caja=(100, 20, 200, 80)),
        epp("vest", caja=(80, 150, 320, 400)),
    ]
    partes = MonitorEPP._partes_de(epps, persona)
    assert evaluar_persona(partes) == frozenset()
