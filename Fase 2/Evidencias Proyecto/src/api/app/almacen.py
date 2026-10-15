"""preparacion de los datos ante un futuro ingreso de incidentes a través
    De PostgreSQL.

De forma momentanea se agrega la respuesta a través de un json. 
esto se logra a través de una capa la cual se encuentra encapsulada 
para el futuro cambio a PostgreSQL.
"""

import json
import os
from pathlib import Path
from typing import Any

ARCHIVO = Path(
    os.environ.get(
        "CASCOVISION_INCIDENTES",
        Path(__file__).resolve().parents[3] / "db" / "incidents.json",
    )
)


def cargar() -> list[dict[str, Any]]:
    """Devuelve los incidentes guardados, o una lista vacía si no hay archivo."""
    if not ARCHIVO.is_file():
        return []
    try:
        datos = json.loads(ARCHIVO.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return []
    return datos if isinstance(datos, list) else []


def guardar(incidentes: list[dict[str, Any]]) -> None:
    """Vuelca la lista completa a disco, creando la carpeta si hace falta."""
    ARCHIVO.parent.mkdir(parents=True, exist_ok=True)
    temporal = ARCHIVO.with_suffix(".tmp")
    temporal.write_text(json.dumps(incidentes, ensure_ascii=False, indent=2),
                        encoding="utf-8")
    temporal.replace(ARCHIVO)
