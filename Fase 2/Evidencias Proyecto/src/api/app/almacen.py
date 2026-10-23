"""Persistencia de incidentes de CascoVision.

La API trabaja contra esta capa y no sabe dónde se guardan los datos. Hay dos
implementaciones, elegidas con la variable de entorno CASCOVISION_STORAGE:

- ``json`` (por defecto): un archivo local, útil para desarrollo y pruebas sin
  levantar una base de datos.
- ``postgres``: PostgreSQL, el almacenamiento definido en la arquitectura. Usa
  las variables POSTGRES_* y el esquema de ``db/migrations/``.
"""

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Protocol
from uuid import UUID


class AlmacenNoDisponible(Exception):
    """El almacenamiento no está configurado o no responde."""


class ReferenciaIncidenteInvalida(Exception):
    """La cámara o zona del incidente no existe en los catálogos."""


class Almacen(Protocol):
    def crear_o_actualizar(self, registro: dict[str, Any]) -> None: ...

    def buscar_episodio(self, episode_id: str) -> dict[str, Any] | None: ...

    def listar(
        self, filtros: dict[str, str], pagina: int, limite: int
    ) -> list[dict[str, Any]]: ...

    def obtener(self, incident_id: str) -> dict[str, Any] | None: ...


# ==================== JSON ====================

ARCHIVO = Path(
    os.environ.get(
        "CASCOVISION_INCIDENTES",
        Path(__file__).resolve().parents[3] / "db" / "incidents.json",
    )
)


def _fecha(valor: str) -> datetime:
    return datetime.fromisoformat(valor.replace("Z", "+00:00"))


class AlmacenJSON:
    """Guarda los incidentes en un archivo JSON con escritura atómica."""

    def __init__(self, archivo: Path) -> None:
        self.archivo = archivo

    def _cargar(self) -> list[dict[str, Any]]:
        if not self.archivo.is_file():
            return []
        try:
            datos = json.loads(self.archivo.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return []
        return datos if isinstance(datos, list) else []

    def _guardar(self, incidentes: list[dict[str, Any]]) -> None:
        self.archivo.parent.mkdir(parents=True, exist_ok=True)
        temporal = self.archivo.with_suffix(".tmp")
        temporal.write_text(
            json.dumps(incidentes, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        temporal.replace(self.archivo)

    def crear_o_actualizar(self, registro: dict[str, Any]) -> None:
        """Guarda el registro, reutilizando el del episodio si ya existe.

        Un ping o un cierre no abren un incidente nuevo: actualizan el que se
        creó con el mismo ``episode_id``, para que la historia de la persona sin
        EPP quede en una sola fila.
        """
        datos = self._cargar()
        episodio = registro.get("episode_id")
        if episodio:
            indice = next(
                (i for i, d in enumerate(datos) if d.get("episode_id") == episodio),
                None,
            )
        else:
            indice = next(
                (i for i, d in enumerate(datos) if d.get("id") == registro["id"]), None
            )
        if indice is None:
            datos.append(registro)
        else:
            # Solo se actualiza el ciclo de vida; los datos del aviso original
            # (evidencia, confianza, tipos) se conservan.
            datos[indice] = {**datos[indice], **{
                campo: registro.get(campo)
                for campo in ("event", "ping_count", "last_ping_at", "ended_at")
                if registro.get(campo) is not None or campo == "ended_at"
            }}
        self._guardar(datos)

    def buscar_episodio(self, episode_id: str) -> dict[str, Any] | None:
        if not episode_id:
            return None
        return next(
            (d for d in self._cargar() if d.get("episode_id") == episode_id), None
        )

    def listar(
        self, filtros: dict[str, str], pagina: int, limite: int
    ) -> list[dict[str, Any]]:
        datos = [
            d
            for d in self._cargar()
            if all(d.get(campo) == valor for campo, valor in filtros.items())
        ]
        datos.sort(key=lambda d: _fecha(d["detected_at"]), reverse=True)
        inicio = (pagina - 1) * limite
        return datos[inicio : inicio + limite]

    def obtener(self, incident_id: str) -> dict[str, Any] | None:
        return next((d for d in self._cargar() if d.get("id") == incident_id), None)


# ==================== PostgreSQL ====================

COLUMNAS = (
    "id, camera_id, zone_id, detected_at, violation_type, violation_types, "
    "confidence, evidence_path, beacon_alert_status, beacon_alert_latency_ms, "
    "person_track_id, status, created_at, event, episode_id, ping_count, "
    "started_at, last_ping_at, ended_at"
)
FILTROS_PERMITIDOS = ("zone_id", "camera_id", "violation_type", "status")


def postgres_config() -> dict[str, str | int]:
    requeridas = ("POSTGRES_DB", "POSTGRES_USER", "POSTGRES_PASSWORD")
    if any(not os.getenv(nombre) for nombre in requeridas):
        raise AlmacenNoDisponible("PostgreSQL is not configured")
    try:
        puerto = int(os.getenv("POSTGRES_PORT", "5432"))
    except ValueError as exc:
        raise AlmacenNoDisponible("PostgreSQL port is invalid") from exc
    if not 1 <= puerto <= 65535:
        raise AlmacenNoDisponible("PostgreSQL port is invalid")
    return {
        "host": os.getenv("POSTGRES_HOST", "localhost"),
        "port": puerto,
        "dbname": os.environ["POSTGRES_DB"],
        "user": os.environ["POSTGRES_USER"],
        "password": os.environ["POSTGRES_PASSWORD"],
    }


def _desde_fila(fila: tuple) -> dict[str, Any]:
    """Convierte una fila en el diccionario de la API, con fechas en UTC.

    PostgreSQL devuelve TIMESTAMPTZ en la zona horaria de la sesión; la API
    responde siempre en UTC.
    """
    (
        incident_id, camera_id, zone_id, detected_at, violation_type,
        violation_types, confidence, evidence_path, beacon_status,
        beacon_latency, person_track_id, status, created_at, event,
        episode_id, ping_count, started_at, last_ping_at, ended_at,
    ) = fila
    return {
        "id": str(incident_id),
        "camera_id": camera_id,
        "zone_id": zone_id,
        "detected_at": detected_at.astimezone(timezone.utc),
        "violation_type": violation_type,
        "violation_types": violation_types,
        "confidence": confidence,
        "evidence_path": evidence_path,
        "beacon_alert": {"status": beacon_status, "latency_ms": beacon_latency},
        "person_track_id": person_track_id,
        "status": status,
        "created_at": created_at.astimezone(timezone.utc),
        "event": event,
        "episode_id": str(episode_id) if episode_id else None,
        "ping_count": ping_count,
        "started_at": started_at.astimezone(timezone.utc) if started_at else None,
        "last_ping_at": last_ping_at.astimezone(timezone.utc) if last_ping_at else None,
        "ended_at": ended_at.astimezone(timezone.utc) if ended_at else None,
    }


class AlmacenPostgres:
    """Guarda los incidentes en la tabla ``incidents`` de PostgreSQL."""

    def _conectar(self):
        import psycopg

        try:
            return psycopg.connect(**postgres_config())
        except psycopg.OperationalError as exc:
            raise AlmacenNoDisponible("PostgreSQL is unavailable") from exc

    def _ejecutar(self, sql: str, parametros: tuple) -> list[tuple]:
        import psycopg

        try:
            with self._conectar() as conexion:
                cursor = conexion.execute(sql, parametros)
                return cursor.fetchall() if cursor.description else []
        except psycopg.errors.UndefinedTable as exc:
            raise AlmacenNoDisponible("Incident schema is not initialized") from exc
        except psycopg.errors.UndefinedColumn as exc:
            raise AlmacenNoDisponible("Incident schema is outdated") from exc
        except psycopg.errors.ForeignKeyViolation as exc:
            raise ReferenciaIncidenteInvalida("Camera or zone is not configured") from exc
        except psycopg.OperationalError as exc:
            raise AlmacenNoDisponible("PostgreSQL is unavailable") from exc

    def crear_o_actualizar(self, registro: dict[str, Any]) -> None:
        """Inserta el registro o actualiza el del mismo episodio si existe.

        El ``ON CONFLICT`` sobre ``episode_id`` hace que un ping o un cierre
        actualicen la fila del episodio en vez de duplicar el incidente. Si
        trae un ``id`` que ya existe, también se actualiza, para tolerar
        reintentos del agente Edge.
        """
        self._ejecutar(
            "INSERT INTO incidents ("
            "id, camera_id, zone_id, detected_at, violation_type, violation_types, "
            "confidence, evidence_path, beacon_alert_status, beacon_alert_latency_ms, "
            "person_track_id, status, created_at, event, episode_id, ping_count, "
            "started_at, last_ping_at, ended_at"
            ") VALUES ("
            "%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s"
            ") ON CONFLICT (id) DO UPDATE SET "
            "event = EXCLUDED.event, ping_count = EXCLUDED.ping_count, "
            "last_ping_at = EXCLUDED.last_ping_at, ended_at = EXCLUDED.ended_at, "
            "started_at = incidents.started_at, created_at = incidents.created_at",
            (
                registro["id"], registro["camera_id"], registro["zone_id"],
                registro["detected_at"], registro["violation_type"],
                registro["violation_types"], registro["confidence"],
                registro["evidence_path"], registro["beacon_alert"]["status"],
                registro["beacon_alert"]["latency_ms"],
                registro["person_track_id"], registro["status"],
                registro["created_at"], registro["event"],
                registro.get("episode_id"), registro.get("ping_count", 0),
                registro.get("started_at"), registro.get("last_ping_at"),
                registro.get("ended_at"),
            ),
        )

    def buscar_episodio(self, episode_id: str) -> dict[str, Any] | None:
        try:
            UUID(episode_id)
        except (ValueError, TypeError):
            return None
        filas = self._ejecutar(
            f"SELECT {COLUMNAS} FROM incidents WHERE episode_id = %s", (episode_id,)
        )
        return _desde_fila(filas[0]) if filas else None

    def listar(
        self, filtros: dict[str, str], pagina: int, limite: int
    ) -> list[dict[str, Any]]:
        condiciones, parametros = [], []
        for campo, valor in filtros.items():
            if campo not in FILTROS_PERMITIDOS:
                raise ValueError(f"filtro no permitido: {campo}")
            condiciones.append(f"{campo} = %s")
            parametros.append(valor)
        where = f"WHERE {' AND '.join(condiciones)} " if condiciones else ""
        filas = self._ejecutar(
            f"SELECT {COLUMNAS} FROM incidents {where}"
            "ORDER BY detected_at DESC LIMIT %s OFFSET %s",
            (*parametros, limite, (pagina - 1) * limite),
        )
        return [_desde_fila(fila) for fila in filas]

    def obtener(self, incident_id: str) -> dict[str, Any] | None:
        try:
            UUID(incident_id)
        except ValueError:
            return None
        filas = self._ejecutar(
            f"SELECT {COLUMNAS} FROM incidents WHERE id = %s", (incident_id,)
        )
        return _desde_fila(filas[0]) if filas else None


def obtener_almacen() -> Almacen:
    """Devuelve el almacenamiento configurado en CASCOVISION_STORAGE."""

    tipo = os.getenv("CASCOVISION_STORAGE", "json").lower()
    if tipo == "postgres":
        return AlmacenPostgres()
    if tipo == "json":
        return AlmacenJSON(ARCHIVO)
    raise AlmacenNoDisponible(f"Unknown storage: {tipo}")
