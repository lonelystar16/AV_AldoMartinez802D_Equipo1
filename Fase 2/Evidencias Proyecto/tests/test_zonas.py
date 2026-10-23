"""Pruebas de las zonas de riesgo: geometría, configuración y filtro del motor.

El filtro de zona decide qué parte del encuadre se vigila. Dos decisiones son
las que más pesan y las que este archivo se encarga de fijar:

- El lugar de una persona son sus pies, no el centro de su caja. Con el
  centro, la misma persona entra y sale de una zona según dónde encuadre la
  cámara, y una zona pegada al suelo no detectaría a nadie.
- Fuera de toda zona vigilada no se abre registro ninguno, pero el difuminado
  sigue aplicándose: el anonimato no depende de dónde esté la persona.

El episodio queda anclado a la zona donde nació. Salir de esa zona no cierra
el registro al instante: pasa a espera con la misma gracia que la pérdida de
detección, y si la persona vuelve a tiempo se retoma con el mismo episode_id.

El retomar exige además aparecer cerca de donde se fue, para que nadie se
apropie del episodio de otro. Por eso los cruces de frontera se ejercitan con
dos bandas contiguas y no con un salto de medio encuadre: un salto así el motor
lo rechaza, y con razón.
"""

import ast
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pytest

MOTOR = Path(__file__).parents[1] / "Yolo" / "modelamiento"
sys.path.insert(0, str(MOTOR))

import motor_cascovision as mc  # noqa: E402
import zonas as zn  # noqa: E402

# Marco de referencia de todas las pruebas de motor: 300 px de ancho por 400 de
# alto. Las zonas se escriben en relativo y las cajas en píxeles, así que hace
# falta saber las dos cosas para comprobar que la conversión es correcta.
ANCHO, ALTO = 300, 400


def _frame():
    return np.random.default_rng(7).integers(0, 255, (ALTO, ANCHO, 3), dtype=np.uint8)


# ---------- punto dentro del polígono ----------

def test_un_punto_interior_esta_dentro() -> None:
    cuadrado = [[0.0, 0.0], [1.0, 0.0], [1.0, 1.0], [0.0, 1.0]]
    assert zn.punto_en_poligono((0.5, 0.5), cuadrado)


def test_un_punto_exterior_no_esta_dentro() -> None:
    cuadrado = [[0.2, 0.2], [0.8, 0.2], [0.8, 0.8], [0.2, 0.8]]
    assert not zn.punto_en_poligono((0.1, 0.5), cuadrado)


def test_un_vertice_cuenta_como_dentro() -> None:
    cuadrado = [[0.2, 0.2], [0.8, 0.2], [0.8, 0.8], [0.2, 0.8]]
    assert zn.punto_en_poligono((0.2, 0.2), cuadrado)


def test_un_punto_sobre_el_borde_cuenta_como_dentro() -> None:
    """Quien pisa la línea de la zona está en la zona.

    Incluir el borde es una decisión: sin ella, un píxel de diferencia al
    dibujar el polígono bastaría para dejar a alguien sin reportar.
    """
    cuadrado = [[0.2, 0.2], [0.8, 0.2], [0.8, 0.8], [0.2, 0.8]]
    assert zn.punto_en_poligono((0.5, 0.8), cuadrado)
    assert zn.punto_en_poligono((0.2, 0.5), cuadrado)


def test_el_hueco_de_un_poligono_concavo_no_cuenta_como_dentro() -> None:
    """Una U no debe dar por dentro lo que queda en su hueco."""
    u = [[0.0, 0.0], [1.0, 0.0], [1.0, 1.0], [0.7, 1.0], [0.7, 0.3],
         [0.3, 0.3], [0.3, 1.0], [0.0, 1.0]]
    assert zn.punto_en_poligono((0.15, 0.7), u)     # en la pata izquierda
    assert not zn.punto_en_poligono((0.5, 0.7), u)  # en el hueco


def test_un_poligono_muy_corto_no_contiene_nada() -> None:
    assert not zn.punto_en_poligono((0.5, 0.5), [])


# ---------- los pies, no el centro ----------

ZONAS_PRUEBA = [
    {"id": "zona-arriba", "poligono": [[0.0, 0.0], [1.0, 0.0], [1.0, 0.3], [0.0, 0.3]]},
    {"id": "zona-abajo", "poligono": [[0.0, 0.6], [1.0, 0.6], [1.0, 1.0], [0.0, 1.0]]},
]

# Dos bandas contiguas, para ejercitar el cruzar el borde. Entre 0.3 y 0.6 no
# hay zona en ZONAS_PRUEBA, pero cruzar esa franja son 280 px, y el motor solo
# retoma a quien reaparece cerca de donde se fue.
ZONAS_PEGADAS = [
    {"id": "zona-alta", "poligono": [[0.0, 0.3], [1.0, 0.3], [1.0, 0.5], [0.0, 0.5]]},
    {"id": "zona-baja", "poligono": [[0.0, 0.5], [1.0, 0.5], [1.0, 1.0], [0.0, 1.0]]},
]

DENTRO = (100, 200, 200, 380)  # pies en rel 0.95: dentro de 'zona-abajo'
FUERA = (100, 100, 200, 180)   # pies en rel 0.45: entre las dos bandas
ALTA = (100, 70, 200, 170)     # pies en rel 0.425: dentro de 'zona-alta'
BAJA = (100, 130, 200, 230)    # pies en rel 0.575: dentro de 'zona-baja'
SALIDA = (100, 20, 200, 100)   # pies en rel 0.25: fuera de las pegadas


def test_una_zona_pegada_al_suelo_detecta_a_quien_pisa_en_ella() -> None:
    """Los pies caen en la zona y el centro del torso no; se debe reportar.

    Con el centro de la caja en lugar de los pies, esta zona dejaría de ver a
    todo el mundo: nadie tiene el torso en el suelo.
    """
    assert zn.zona_de(DENTRO, ZONAS_PRUEBA, ANCHO, ALTO) == "zona-abajo"


def test_alguien_con_la_cabeza_en_zona_y_los_pies_fuera_no_reporta() -> None:
    """Encuadra la cámara más abajo y la cabeza pasa a la zona de arriba."""
    caja = (100, 20, 200, 130)  # pies en y=130 -> rel 0.325, ya fuera

    assert zn.zona_de(caja, ZONAS_PRUEBA, ANCHO, ALTO) is None


def test_fuera_de_toda_zona_devuelve_none() -> None:
    assert zn.zona_de(FUERA, ZONAS_PRUEBA, ANCHO, ALTO) is None


def test_sin_zonas_configuradas_devuelve_none() -> None:
    """`zonas=None` es el motor de siempre: él solo decide qué vigilar."""
    assert zn.zona_de(DENTRO, None, ANCHO, ALTO) is None
    assert zn.zona_de(DENTRO, [], ANCHO, ALTO) is None


def test_sin_caja_tambien_devuelve_none() -> None:
    assert zn.zona_de(None, ZONAS_PRUEBA, ANCHO, ALTO) is None


def test_dos_zonas_solapadas_gana_la_primera() -> None:
    """Quien pisa las dos cae siempre en la que aparece antes en la lista."""
    solapadas = [
        {"id": "primera", "poligono": [[0.0, 0.0], [1.0, 0.0], [1.0, 1.0], [0.0, 1.0]]},
        {"id": "segunda", "poligono": [[0.0, 0.0], [1.0, 0.0], [1.0, 1.0], [0.0, 1.0]]},
    ]
    assert zn.zona_de(DENTRO, solapadas, ANCHO, ALTO) == "primera"


# ---------- configuración ----------

CONFIG_VALIDA = {
    "camara-01": [
        {"id": "zona-norte",
         "poligono": [[0.05, 0.6], [0.95, 0.6], [0.95, 1.0], [0.05, 1.0]],
         "baliza": "http://192.168.1.50:8000"},
    ],
}


def _ruta_config(tmp_path, contenido):
    ruta = tmp_path / "zonas.json"
    if isinstance(contenido, str):
        ruta.write_text(contenido, encoding="utf-8")
    else:
        ruta.write_text(json.dumps(contenido), encoding="utf-8")
    return ruta


def test_cargar_zonas_validas_devuelve_las_zonas_de_cada_camara(tmp_path) -> None:
    ruta = _ruta_config(tmp_path, CONFIG_VALIDA)

    config = zn.cargar_zonas(ruta)

    assert list(config) == ["camara-01"]
    assert config["camara-01"][0]["id"] == "zona-norte"
    # Los vértices se normalizan a flotante: más abajo se dividen entre el
    # tamaño del frame, y un entero ahí sería frágil.
    assert config["camara-01"][0]["poligono"][0] == (0.05, 0.6)


def test_un_config_de_prueba_sigue_siendo_valida(tmp_path) -> None:
    """La plantilla versionada no puede dejar de cargarse por una reforma."""
    ruta = MOTOR.parents[1] / "config" / "zonas.json.example"

    config = zn.cargar_zonas(ruta)

    assert "camara-01" in config and "camara-02" in config
    assert [z["id"] for z in config["camara-01"]] == ["zona-norte", "zona-sur"]
    assert zn.comprobar_solapes(config["camara-01"]) == []


def test_un_archivo_inexistente_no_se_arranca_en_vacio(tmp_path) -> None:
    """Peor que no arrancar sería arrancar sin zonas y no avisar a nadie."""
    with pytest.raises(zn.ErrorZonas, match="No existe"):
        zn.cargar_zonas(tmp_path / "no-existe.json")


def test_un_json_roto_se_explica(tmp_path) -> None:
    ruta = _ruta_config(tmp_path, "{no es json")

    with pytest.raises(zn.ErrorZonas, match="no es JSON"):
        zn.cargar_zonas(ruta)


def test_una_configuracion_vacia_se_rechaza(tmp_path) -> None:
    ruta = _ruta_config(tmp_path, {})

    with pytest.raises(zn.ErrorZonas, match="una entrada por cámara"):
        zn.cargar_zonas(ruta)


def test_una_camara_sin_zonas_se_rechaza(tmp_path) -> None:
    ruta = _ruta_config(tmp_path, {"camara-01": []})

    with pytest.raises(zn.ErrorZonas, match="no tiene zonas"):
        zn.cargar_zonas(ruta)


def test_un_poligono_con_dos_vertices_se_rechaza(tmp_path) -> None:
    config = {"camara-01": [{"id": "a", "poligono": [[0.0, 0.0], [1.0, 1.0]]}]}
    ruta = _ruta_config(tmp_path, config)

    with pytest.raises(zn.ErrorZonas, match="al menos 3"):
        zn.cargar_zonas(ruta)


def test_una_coordenada_fuera_del_frame_se_rechaza(tmp_path) -> None:
    config = {"camara-01": [{"id": "a",
                             "poligono": [[0.0, 0.0], [1.5, 0.0], [1.0, 1.0]]}]}
    ruta = _ruta_config(tmp_path, config)

    with pytest.raises(zn.ErrorZonas, match="fuera del rango"):
        zn.cargar_zonas(ruta)


def test_un_vertice_que_no_es_numero_se_rechaza(tmp_path) -> None:
    config = {"camara-01": [{"id": "a",
                             "poligono": [[0.0, 0.0], ["x", 0.0], [1.0, 1.0]]}]}
    ruta = _ruta_config(tmp_path, config)

    with pytest.raises(zn.ErrorZonas, match="par de números"):
        zn.cargar_zonas(ruta)


def test_un_id_repetido_se_rechaza(tmp_path) -> None:
    misma = {"id": "a", "poligono": [[0.0, 0.0], [0.4, 0.0], [0.4, 0.4], [0.0, 0.4]]}
    otra = {"id": "a", "poligono": [[0.5, 0.5], [1.0, 0.5], [1.0, 1.0], [0.5, 1.0]]}
    ruta = _ruta_config(tmp_path, {"camara-01": [misma, otra]})

    with pytest.raises(zn.ErrorZonas, match="dos veces"):
        zn.cargar_zonas(ruta)


def test_una_zona_sin_id_se_rechaza(tmp_path) -> None:
    config = {"camara-01": [{"poligono": [[0.0, 0.0], [1.0, 0.0], [1.0, 1.0]]}]}
    ruta = _ruta_config(tmp_path, config)

    with pytest.raises(zn.ErrorZonas, match="id"):
        zn.cargar_zonas(ruta)


def test_una_zona_alineada_no_encierra_area(tmp_path) -> None:
    config = {"camara-01": [{"id": "a", "poligono": [[0.0, 0.0], [0.5, 0.5], [1.0, 1.0]]}]}
    ruta = _ruta_config(tmp_path, config)

    with pytest.raises(zn.ErrorZonas, match="no encierra área"):
        zn.cargar_zonas(ruta)


def test_una_baliza_que_no_es_texto_se_rechaza(tmp_path) -> None:
    config = {"camara-01": [{"id": "a", "baliza": 8000,
                             "poligono": [[0.0, 0.0], [1.0, 0.0], [1.0, 1.0]]}]}
    ruta = _ruta_config(tmp_path, config)

    with pytest.raises(zn.ErrorZonas, match="baliza"):
        zn.cargar_zonas(ruta)


# ---------- avisos de dibujo ----------

def test_dos_zonas_que_no_se_pisan_no_avisan() -> None:
    a = {"id": "a", "poligono": [[0.0, 0.0], [0.5, 0.0], [0.5, 0.5], [0.0, 0.5]]}
    b = {"id": "b", "poligono": [[0.5, 0.0], [1.0, 0.0], [1.0, 0.5], [0.5, 0.5]]}

    assert zn.comprobar_solapes([a, b]) == []


def test_dos_zonas_solapadas_avisan_sin_cortar_el_arranque() -> None:
    """Sin el aviso, "gana la primera" se convierte en un misterio permanente."""
    a = {"id": "a", "poligono": [[0.0, 0.0], [0.6, 0.0], [0.6, 0.6], [0.0, 0.6]]}
    b = {"id": "b", "poligono": [[0.4, 0.4], [1.0, 0.4], [1.0, 1.0], [0.4, 1.0]]}

    avisos = zn.comprobar_solapes([a, b])

    assert len(avisos) == 1
    assert "'a'" in avisos[0] and "'b'" in avisos[0]


def test_una_zona_entera_dentro_de_otra_tambien_avisa() -> None:
    """No se cruzan aristas, pero alguien pisaría las dos a la vez."""
    exterior = {"id": "exterior",
                "poligono": [[0.0, 0.0], [1.0, 0.0], [1.0, 1.0], [0.0, 1.0]]}
    interior = {"id": "interior",
                "poligono": [[0.4, 0.4], [0.6, 0.4], [0.6, 0.6], [0.4, 0.6]]}

    assert len(zn.comprobar_solapes([exterior, interior])) == 1


# ---------- el filtro del motor ----------

class MotorPrueba(mc.MonitorEPP):
    """Motor entero con detecciones programadas, sin cargar YOLO ni YuNet."""

    def __init__(self, escenas, zonas, camera_id="camara-01", ping_segundos=60):
        self.escenas = iter(escenas)
        self.ping_segundos = ping_segundos
        self.historial = {}
        self.ultimo_estado = {}
        self.estado_confirmado = {}
        self.violacion_confirmada = {}
        self.ultimo_visto = {}
        self.caja_vista = {}
        self.episodio = {}
        self.en_espera = []
        self.n_frames = 0
        self.t_prev = time.time()
        self.fps = 0.0
        self.camera_id = camera_id
        self.zonas = zonas
        self.difuminados = []
        self.avisos = []
        self.al_registrar = self.avisos.append

    def _detectar(self, frame):
        return next(self.escenas)

    def guardar_evidencia(self, frame):
        return "incidents/2026/01/01/prueba.jpg", datetime.now(timezone.utc)

    def difumar_rostros(self, frame, persona, cabezas):
        """Sustituye el difuminado: aquí solo se cuenta quién pasó por él."""
        self.difuminados.append(persona)
        return 1

    @staticmethod
    def _consola(pid, estado, evento="inicio"):
        pass


def _dentro_de(caja, nombre, parte):
    """Una detección de EPP colocada dentro de la propia caja de la persona."""
    x1, y1, x2, y2 = caja
    alto = y2 - y1
    if parte == "cabeza":
        return {"id": 80, "conf": 0.8, "nombre": nombre,
                "caja": (x1 + 40, y1, x2 - 40, y1 + int(alto * 0.25))}
    return {"id": 81, "conf": 0.8, "nombre": nombre,
            "caja": (x1 + 10, y1 + int(alto * 0.4), x2 - 10, y2 - 10)}


def _sin_epp(caja):
    """Las dos faltas: casco y chaleco declarados ausentes por el detector."""
    return [_dentro_de(caja, "no_helmet", "cabeza"),
            _dentro_de(caja, "no_vest", "torso")]


def _cumpliendo(caja):
    """Casco y chaleco puestos: no hay nada que notificar."""
    return [_dentro_de(caja, "helmet", "cabeza"),
            _dentro_de(caja, "vest", "torso")]


def _escena(pid, caja, epps=None):
    """Una persona, sin seguimiento entre frames."""
    personas = [{"id": pid, "caja": caja, "conf": 0.9, "nombre": "Person"}]
    return personas, _sin_epp(caja) if epps is None else epps(caja), False


def _monitor(escenas, zonas=ZONAS_PRUEBA, **kwargs):
    return MotorPrueba(escenas, zonas, **kwargs)


def test_infraccion_dentro_de_zona_se_reporta_con_su_zona() -> None:
    monitor = _monitor([_escena(7, DENTRO)])

    incidentes = monitor.procesar(_frame())

    assert len(incidentes) == 1
    assert incidentes[0]["event"] == "inicio"
    assert incidentes[0]["camera_id"] == "camara-01"
    assert incidentes[0]["zone_id"] == "zona-abajo"


def test_infraccion_fuera_de_zona_no_se_reporta_nada() -> None:
    """La idea es vigilar donde hay riesgo, no estar mirando todo el encuadre."""
    monitor = _monitor([_escena(7, FUERA)])

    incidentes = monitor.procesar(_frame())

    assert incidentes == []
    assert monitor.avisos == []
    assert monitor.episodio == {}


def test_fuera_de_zona_ni_se_guarda_estado() -> None:
    """Ni historial ni confirmación: no hay nada que retomar ni que cerrar."""
    monitor = _monitor([_escena(7, FUERA)])

    monitor.procesar(_frame())

    assert monitor.historial == {}
    assert monitor.violacion_confirmada == {}
    # La persona sí se sigue viendo, para no disparar la depuración de invisibles.
    assert monitor.ultimo_visto == {7: 1}


def test_el_difuminado_no_depende_de_la_zona() -> None:
    """Fuera de zona no se reporta, pero el rostro se difumina igual."""
    monitor = _monitor([_escena(7, FUERA)])

    monitor.procesar(_frame())

    assert monitor.difuminados == [FUERA]
    assert monitor.avisos == []


def test_alguien_cumpliendo_no_abre_registro_dentro_de_zona() -> None:
    """Cumplir no es noticia, ni dentro de la zona ni fuera de ella."""
    monitor = _monitor([_escena(7, DENTRO, _cumpliendo)])

    assert monitor.procesar(_frame()) == []
    assert monitor.episodio == {}


def test_entrar_en_zona_sigue_sin_abrir_registro_si_cumple() -> None:
    """Pasa por la zona con el EPP puesto: la zona no convierte lo legal en aviso."""
    monitor = _monitor([_escena(7, FUERA, _cumpliendo),
                        _escena(7, DENTRO, _cumpliendo)])

    monitor.procesar(_frame())
    assert monitor.procesar(_frame()) == []
    assert monitor.episodio == {}


# ---------- salir y volver de la zona ----------

def test_salir_de_zona_no_cierra_el_registro() -> None:
    """Cruzar el borde no debe arrastrar un FIN y un INICIO segundos después."""
    monitor = _monitor([_escena(7, BAJA), _escena(7, SALIDA)], zonas=ZONAS_PEGADAS)
    frame = _frame()

    monitor.procesar(frame)
    cierres = monitor.procesar(frame)

    assert cierres == []
    assert monitor.episodio == {}
    assert len(monitor.en_espera) == 1
    assert monitor.en_espera[0]["zona"] == "zona-baja"
    assert monitor.en_espera[0]["clave"] == (
        "missing_helmet", "missing_reflective_vest")


def test_volver_a_su_zona_retoma_el_mismo_registro() -> None:
    """Menos de 15 s fuera y se retoma: mismo episodio, sin un INICIO nuevo."""
    monitor = _monitor([_escena(7, BAJA), _escena(7, SALIDA),
                        _escena(7, BAJA)], zonas=ZONAS_PEGADAS)
    frame = _frame()

    primer_aviso = monitor.procesar(frame)[0]
    monitor.procesar(frame)
    tras_volver = monitor.procesar(frame)

    assert primer_aviso["episode_id"]
    assert tras_volver == []
    assert monitor.en_espera == []
    assert monitor.episodio[7]["incidente"]["episode_id"] == primer_aviso["episode_id"]


def test_al_vencer_la_gracia_de_zona_el_registro_se_cierra() -> None:
    """Si no vuelve en 15 s, ya no puede afirmarse que siga sin EPP."""
    monitor = _monitor([_escena(7, BAJA), _escena(7, SALIDA),
                        _escena(7, SALIDA)], zonas=ZONAS_PEGADAS)
    frame = _frame()

    aviso = monitor.procesar(frame)[0]
    monitor.procesar(frame)
    monitor.en_espera[0]["perdido"] -= mc.GRACIA_CIERRE_SEGUNDOS + 1
    cierres = monitor.procesar(frame)

    assert len(cierres) == 1
    assert cierres[0]["event"] == "fin"
    assert cierres[0]["episode_id"] == aviso["episode_id"]


def test_cambiar_de_zona_abre_un_registro_nuevo() -> None:
    """El episodio queda anclado a su zona: en la otra empieza otro."""
    monitor = _monitor([_escena(7, BAJA), _escena(7, ALTA)], zonas=ZONAS_PEGADAS)
    frame = _frame()

    primero = monitor.procesar(frame)[0]
    segundo = monitor.procesar(frame)[0]

    assert primero["zone_id"] == "zona-baja"
    assert segundo["zone_id"] == "zona-alta"
    assert segundo["event"] == "inicio"
    assert segundo["episode_id"] != primero["episode_id"]
    # El de la zona anterior queda en espera, esperando su cierre por gracia.
    assert len(monitor.en_espera) == 1
    assert monitor.en_espera[0]["zona"] == "zona-baja"


def test_volver_a_su_zona_retoma_el_suyo_y_no_el_de_la_otra() -> None:
    """Al volver a la baja se retoma el de la baja; el de la alta queda en espera."""
    monitor = _monitor([_escena(7, BAJA), _escena(7, ALTA),
                        _escena(7, BAJA)], zonas=ZONAS_PEGADAS)
    frame = _frame()

    primero = monitor.procesar(frame)[0]   # INICIO en zona-baja
    monitor.procesar(frame)                # pasa a zona-alta
    monitor.procesar(frame)                # vuelve a zona-baja

    assert len(monitor.en_espera) == 1
    assert monitor.en_espera[0]["zona"] == "zona-alta"
    assert len(monitor.episodio) == 1
    assert monitor.episodio[7]["incidente"]["episode_id"] == primero["episode_id"]


def test_alguien_que_nunca_entro_no_genera_ni_estado_ni_espera() -> None:
    """Sin zona no hay episodio que apartar, y la espera no se debe hinchar."""
    monitor = _monitor([_escena(7, FUERA)] * 3)
    frame = _frame()

    for _ in range(3):
        monitor.procesar(frame)

    assert monitor.en_espera == []
    assert monitor.avisos == []


# ---------- compatibilidad ----------

def test_sin_zonas_el_motor_sigue_reportando_a_todo_el_mundo() -> None:
    """`zonas=None` es el comportamiento anterior, sin cambios."""
    monitor = _monitor([_escena(7, FUERA)], zonas=None)

    incidentes = monitor.procesar(_frame())

    assert len(incidentes) == 1
    # Sin zonas configuradas queda el zone_id de siempre, que la API exige.
    assert incidentes[0]["zone_id"] == "zona-norte"
    assert incidentes[0]["camera_id"] == "camara-01"


def test_el_camera_id_del_motor_va_al_incidente() -> None:
    monitor = _monitor([_escena(7, DENTRO)], camera_id="camara-07")

    incidentes = monitor.procesar(_frame())

    assert incidentes[0]["camera_id"] == "camara-07"


def test_sin_zonas_queda_el_comportamiento_del_ciclo_de_aviso() -> None:
    """El ciclo no se toca: se avisa una sola vez por cambio de infracción."""
    monitor = _monitor([_escena(7, DENTRO)] * 3, zonas=None)
    frame = _frame()

    primero = monitor.procesar(frame)
    repetidos = monitor.procesar(frame) + monitor.procesar(frame)

    assert len(primero) == 1
    assert repetidos == []


# ---------- el script ----------

def test_monitoreo_sector_existe_y_filtra_por_zona() -> None:
    """El script carga las zonas y se las entrega al motor."""
    ruta = MOTOR / "monitoreo_sector.py"
    arbol = ast.parse(ruta.read_text(encoding="utf-8"))

    llamadas = {n.func.id for n in ast.walk(arbol)
                if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)}
    assert {"cargar_zonas", "ReporteAPI", "MonitorEPP", "comprobar_solapes"} <= llamadas

    motor = [n for n in ast.walk(arbol)
             if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
             and n.func.id == "MonitorEPP"][0]
    palabras = {kw.arg for kw in motor.keywords}
    assert {"camera_id", "zonas", "al_registrar"} <= palabras


def test_monitoreo_sector_no_arranca_con_una_camara_sin_zonas() -> None:
    """Una cámara sin entrada en el JSON no puede quedar vigilando nada en silencio."""
    ruta = MOTOR / "monitoreo_sector.py"
    arbol = ast.parse(ruta.read_text(encoding="utf-8"))

    fuentes = {n.func.id for n in ast.walk(arbol)
               if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)}
    assert "SystemExit" in fuentes


def test_el_modulo_de_zonas_no_depende_del_motor() -> None:
    """La geometría debe poder usarse sin cargar YOLO ni OpenCV."""
    arbol = ast.parse((MOTOR / "zonas.py").read_text(encoding="utf-8"))

    nombres = [n.names[0].name for n in ast.walk(arbol) if isinstance(n, ast.Import)]
    nombres += [n.module for n in ast.walk(arbol) if isinstance(n, ast.ImportFrom)]

    assert set(nombres) == {"json", "math", "pathlib"}
