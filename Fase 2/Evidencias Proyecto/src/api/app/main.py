"""Punto de entrada de la API REST de CascoVision."""

from fastapi import FastAPI


app = FastAPI(title="CascoVision API")


@app.get("/health")
def health_check() -> dict[str, str]:
    """Devuelve el estado básico de disponibilidad de la API."""

    return {"status": "ok", "service": "cascovision-api"}
