"""Configuración de la API REST de CascoVision.

Centraliza la lectura de las variables de entorno y la validacion de arranque.

La API se levanta con `uv run uvicorn app.main:app --app-dir "Fase 2/Evidencias
Proyecto/src/api"`, opcionalmente con `--env-file`. Este modulo hace que el
archivo `.env` sea opcional: si esta, se carga; si no, se usan las variables
del entorno tal cual.

Las variables y su uso estan documentados en `docs/API.md`.
"""

import os
from pathlib import Path

# Raiz del repositorio: la carpeta que contiene "Fase 2".
RAIZ = next((p for p in Path(__file__).resolve().parents if (p / "Fase 2").is_dir()),
            Path(__file__).resolve().parents[4])

RUTA_ENV = RAIZ / "Fase 2" / "Evidencias Proyecto" / ".env"

# Variables que la API necesita para funcionar. `EDGE_API_TOKEN` es la unica
# imprescindible: sin ella, `POST /incidents` responde 503.
VARIABLES = {
    "EDGE_API_TOKEN": "Token compartido que el agente Edge envia como Bearer. Obligatorio para registrar incidentes",
    "CASCOVISION_STORAGE": "Almacenamiento de incidentes: 'json' (por defecto) o 'postgres'",
    "CASCOVISION_INCIDENTES": "Ruta del archivo JSON. Por defecto 'db/incidents.json'",
    "POSTGRES_DB": "Base de datos PostgreSQL. Obligatoria con CASCOVISION_STORAGE=postgres",
    "POSTGRES_USER": "Usuario de PostgreSQL. Obligatorio con CASCOVISION_STORAGE=postgres",
    "POSTGRES_PASSWORD": "Contrasena de PostgreSQL. Obligatoria con CASCOVISION_STORAGE=postgres",
    "POSTGRES_HOST": "Servidor de PostgreSQL. Por defecto 'localhost'",
    "POSTGRES_PORT": "Puerto de PostgreSQL. Por defecto '5432'",
}


def cargar_env(ruta: Path | None = None, sobrescribir: bool = False) -> Path | None:
    """Carga un archivo `.env` en el entorno, si existe.

    Formato soportado: `CLAVE=valor`, una por linea. Se ignoran las lineas
    vacias y las que empiezan con `#`. Los valores pueden ir entre comillas.

    Args:
        ruta: Archivo a cargar. Por defecto, el `.env` del proyecto.
        sobrescribir: Si es False (por defecto), las variables ya presentes en
            el entorno tienen prioridad sobre las del archivo.

    Returns:
        La ruta cargada, o None si no habia archivo.
    """
    ruta = RUTA_ENV if ruta is None else ruta
    if not ruta.is_file():
        return None
    for linea in ruta.read_text(encoding="utf-8").splitlines():
        linea = linea.strip()
        if not linea or linea.startswith("#") or "=" not in linea:
            continue
        clave, _, valor = linea.partition("=")
        clave = clave.strip()
        valor = valor.strip().strip("\"'")
        if not clave:
            continue
        if not sobrescribir and clave in os.environ:
            continue
        os.environ[clave] = valor
    return ruta


def estado_configuracion() -> dict:
    """Describe la configuracion actual, para diagnostico."""
    return {
        "archivo_env": str(RUTA_ENV) if RUTA_ENV.is_file() else None,
        "almacenamiento": os.getenv("CASCOVISION_STORAGE", "json"),
        "token_configurado": bool(os.getenv("EDGE_API_TOKEN")),
        "variables_desconocidas": sorted(
            clave for clave in os.environ
            if clave.startswith(("CASCOVISION_", "POSTGRES_", "EDGE_", "JWT_", "BALIZA_"))
            and clave not in VARIABLES
        ),
    }


def faltantes_obligatorias() -> list[str]:
    """Variables necesarias para el modo de almacenamiento configurado."""
    faltantes = []
    if not os.getenv("EDGE_API_TOKEN"):
        faltantes.append("EDGE_API_TOKEN")
    if os.getenv("CASCOVISION_STORAGE", "json").lower() == "postgres":
        for clave in ("POSTGRES_DB", "POSTGRES_USER", "POSTGRES_PASSWORD"):
            if not os.getenv(clave):
                faltantes.append(clave)
    return faltantes
