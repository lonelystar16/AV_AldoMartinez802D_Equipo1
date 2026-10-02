"""Pruebas del endpoint de disponibilidad de la API."""

import asyncio
import sys
from pathlib import Path

import httpx


API_SOURCE = Path(__file__).parents[1] / "src" / "api"
sys.path.insert(0, str(API_SOURCE))

from app.main import app  # noqa: E402


def test_health_returns_expected_response() -> None:
    """GET /health responde con el estado básico de la API."""

    async def request() -> httpx.Response:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://test"
        ) as client:
            return await client.get("/health")

    response = asyncio.run(request())

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "service": "cascovision-api",
    }
