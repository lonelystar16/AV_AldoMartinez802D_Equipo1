"""Pruebas del endpoint de diagnostico `/config`.

El endpoint informa de la configuracion efectiva de la API sin exponer valores
secretos, para poder verificar desde el navegador que el `.env` se leyo.
"""

import sys
from pathlib import Path

import httpx
import pytest

API_SOURCE = Path(__file__).parents[1] / "src" / "api"
sys.path.insert(0, str(API_SOURCE))

from app.main import app  # noqa: E402


def peticion(metodo: str, ruta: str, **kwargs) -> httpx.Response:
    async def request() -> httpx.Response:
        transporte = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transporte,
                                     base_url="http://test") as cliente:
            return await cliente.request(metodo, ruta, **kwargs)

    return __import__("asyncio").run(request())


def test_config_responde_200() -> None:
    respuesta = peticion("GET", "/config")

    assert respuesta.status_code == 200


def test_config_informa_el_almacenamiento() -> None:
    cuerpo = peticion("GET", "/config").json()

    assert cuerpo["almacenamiento"] in ("json", "postgres")


def test_config_no_expone_el_valor_del_token(monkeypatch) -> None:
    """Aunque haya token, el endpoint no debe devolver su valor."""
    monkeypatch.setenv("EDGE_API_TOKEN", "token-que-no-debe-aparecer")

    cuerpo = peticion("GET", "/config").json()

    assert "token-que-no-debe-aparecer" not in str(cuerpo)
    assert cuerpo["token_configurado"] is True


def test_config_lista_las_variables_faltantes(monkeypatch) -> None:
    monkeypatch.delenv("EDGE_API_TOKEN", raising=False)
    monkeypatch.setenv("CASCOVISION_STORAGE", "json")

    cuerpo = peticion("GET", "/config").json()

    assert "EDGE_API_TOKEN" in cuerpo["variables_obligatorias_faltantes"]


def test_health_sigue_disponible() -> None:
    """El diagnostico no debe romper el endpoint de salud."""
    respuesta = peticion("GET", "/health")

    assert respuesta.status_code == 200
    assert respuesta.json() == {"status": "ok", "service": "cascovision-api"}
