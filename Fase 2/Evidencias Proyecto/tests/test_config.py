"""Pruebas de la carga de configuracion y del diagnostico de la API.

El modulo `app.config` centraliza la lectura del `.env` y la comprobacion de
las variables obligatorias. Estas pruebas verifican que un `.env` mal formado
no rompe el arranque y que el entorno tiene prioridad sobre el archivo.
"""

import os
import sys
from pathlib import Path

import pytest

API_SOURCE = Path(__file__).parents[1] / "src" / "api"
sys.path.insert(0, str(API_SOURCE))

from app import config  # noqa: E402


def escribir_env(tmp_path: Path, contenido: str) -> Path:
    """Crea un archivo .env temporal y devuelve su ruta."""
    ruta = tmp_path / ".env"
    ruta.write_text(contenido, encoding="utf-8")
    return ruta


def test_carga_env_lee_las_variables(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.delenv("EDGE_API_TOKEN", raising=False)
    ruta = escribir_env(tmp_path, "EDGE_API_TOKEN=secreto\nCASCOVISION_STORAGE=postgres\n")

    config.cargar_env(ruta)

    assert os.environ["EDGE_API_TOKEN"] == "secreto"
    assert os.environ["CASCOVISION_STORAGE"] == "postgres"


def test_carga_env_ignora_comentarios_y_lineas_vacias(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.delenv("EDGE_API_TOKEN", raising=False)
    ruta = escribir_env(tmp_path, "# un comentario\n\nEDGE_API_TOKEN=valor\n")

    config.cargar_env(ruta)

    assert os.environ["EDGE_API_TOKEN"] == "valor"


def test_carga_env_quita_las_comillas(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.delenv("EDGE_API_TOKEN", raising=False)
    ruta = escribir_env(tmp_path, 'EDGE_API_TOKEN="con comillas"\n')

    config.cargar_env(ruta)

    assert os.environ["EDGE_API_TOKEN"] == "con comillas"


def test_el_entorno_tiene_prioridad_sobre_el_archivo(tmp_path: Path, monkeypatch) -> None:
    """Lo exportado en la consola gana sobre lo que dice el .env."""
    monkeypatch.setenv("EDGE_API_TOKEN", "del-entorno")
    ruta = escribir_env(tmp_path, "EDGE_API_TOKEN=del-archivo\n")

    config.cargar_env(ruta)

    assert os.environ["EDGE_API_TOKEN"] == "del-entorno"


def test_cargar_env_puede_sobrescribir(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("EDGE_API_TOKEN", "del-entorno")
    ruta = escribir_env(tmp_path, "EDGE_API_TOKEN=del-archivo\n")

    config.cargar_env(ruta, sobrescribir=True)

    assert os.environ["EDGE_API_TOKEN"] == "del-archivo"


def test_cargar_env_sin_archivo_devuelve_none(tmp_path: Path) -> None:
    assert config.cargar_env(tmp_path / "no-existe.env") is None


def test_cargar_env_tolera_lineas_sin_igual(tmp_path: Path, monkeypatch) -> None:
    """Una linea sin '=' no es una variable: se ignora en vez de romper."""
    monkeypatch.delenv("EDGE_API_TOKEN", raising=False)
    ruta = escribir_env(tmp_path, "SIN_IGUAL\nEDGE_API_TOKEN=ok\n=valor_sin_clave\n")

    config.cargar_env(ruta)

    assert os.environ["EDGE_API_TOKEN"] == "ok"


def test_faltantes_incluye_el_token(monkeypatch) -> None:
    monkeypatch.delenv("EDGE_API_TOKEN", raising=False)
    monkeypatch.setenv("CASCOVISION_STORAGE", "json")

    assert "EDGE_API_TOKEN" in config.faltantes_obligatorias()


def test_faltantes_exige_postgres_cuando_corresponde(monkeypatch) -> None:
    monkeypatch.setenv("EDGE_API_TOKEN", "secreto")
    monkeypatch.setenv("CASCOVISION_STORAGE", "postgres")
    for clave in ("POSTGRES_DB", "POSTGRES_USER", "POSTGRES_PASSWORD"):
        monkeypatch.delenv(clave, raising=False)

    faltantes = config.faltantes_obligatorias()

    assert "POSTGRES_DB" in faltantes
    assert "POSTGRES_USER" in faltantes
    assert "POSTGRES_PASSWORD" in faltantes


def test_sin_faltantes_con_json(monkeypatch) -> None:
    monkeypatch.setenv("EDGE_API_TOKEN", "secreto")
    monkeypatch.setenv("CASCOVISION_STORAGE", "json")

    assert config.faltantes_obligatorias() == []


def test_estado_no_expone_el_valor_del_token(monkeypatch) -> None:
    """El estado de configuracion informa si hay token, nunca su valor."""
    monkeypatch.setenv("EDGE_API_TOKEN", "secreto-muy-largo")

    estado = config.estado_configuracion()

    assert estado["token_configurado"] is True
    assert "secreto-muy-largo" not in str(estado)
