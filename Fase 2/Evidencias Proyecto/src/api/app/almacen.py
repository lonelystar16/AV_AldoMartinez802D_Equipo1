"""Persistencia de incidentes y recursos de CascoVision.

La API trabaja contra esta capa y no sabe dónde se guardan los datos. Hay dos
implementaciones, elegidas con la variable de entorno CASCOVISION_STORAGE:

- ``json`` (por defecto): un archivo local, útil para desarrollo y pruebas sin
  levantar una base de datos.
- ``postgres``: PostgreSQL, el almacenamiento definido en la arquitectura. Usa
  las variables POSTGRES_* y el esquema de ``db/migrations/``.

Guarda dos cosas con distinto carácter: los **incidentes**, que son historia y
solo crecen, y los **recursos** (cámaras, zonas y balizas), que son catálogo y
se editan desde el dashboard. En JSON van en archivos separados; en PostgreSQL,
en tablas distintas. El reporte (`reportar`) se calcula en la implementación
que corresponda: en SQL si hay base, en Python si no, para que las pruebas no
necesiten un servidor.
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
    # --- incidentes ---
    def crear_o_actualizar(self, registro: dict[str, Any]) -> None: ...

    def buscar_episodio(self, episode_id: str) -> dict[str, Any] | None: ...

    def listar(
        self, filtros: dict[str, str], pagina: int, limite: int
    ) -> list[dict[str, Any]]: ...

    def obtener(self, incident_id: str) -> dict[str, Any] | None: ...

    # --- recursos ---
    def listar_camaras(self) -> list[dict[str, Any]]: ...

    def listar_zonas(self, camera_id: str | None = None) -> list[dict[str, Any]]: ...

    def listar_beacons(self) -> list[dict[str, Any]]: ...

    def actualizar_beacon(
        self, beacon_id: str, estado: dict[str, Any]
    ) -> dict[str, Any] | None: ...

    # --- reporte ---
    def reportar(
        self, filtros: dict[str, Any], pagina: int, limite: int
    ) -> dict[str, Any]: ...


# ==================== JSON ====================

ARCHIVO = Path(
    os.environ.get(
        "CASCOVISION_INCIDENTES",
        Path(__file__).resolve().parents[3] / "db" / "incidents.json",
    )
)

# Cámara, zonas y balizas van aparte: son catálogo que se edita desde el
# dashboard, no historia que solo crece.
ARCHIVO_RECURSOS = Path(
    os.environ.get(
        "CASCOVISION_RECURSOS",
        Path(__file__).resolve().parents[3] / "db" / "recursos.json",
    )
)


def _instante(valor: str | datetime) -> datetime:
    """Normaliza un instante ISO o un datetime a datetime con zona horaria."""
    if isinstance(valor, str):
        return datetime.fromisoformat(valor.replace("Z", "+00:00"))
    return valor


class AlmacenJSON:
    """Guarda los incidentes en un archivo JSON con escritura atómica."""

    def __init__(self, archivo: Path, recursos: Path | None = None) -> None:
        self.archivo = archivo
        # Se resuelve al construir, no en la firma, para que las pruebas puedan
        # reemplazar `ARCHIVO_RECURSOS` antes de que se pida la ruta.
        self.recursos = ARCHIVO_RECURSOS if recursos is None else recursos

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
        datos.sort(key=lambda d: _instante(d["detected_at"]), reverse=True)
        inicio = (pagina - 1) * limite
        return datos[inicio : inicio + limite]

    def obtener(self, incident_id: str) -> dict[str, Any] | None:
        return next((d for d in self._cargar() if d.get("id") == incident_id), None)

    # --- recursos ---
    def _cargar_recursos(self) -> dict[str, Any]:
        if not self.recursos.is_file():
            return {}
        try:
            datos = json.loads(self.recursos.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {}
        return datos if isinstance(datos, dict) else {}

    def _guardar_recursos(self, datos: dict[str, Any]) -> None:
        self.recursos.parent.mkdir(parents=True, exist_ok=True)
        temporal = self.recursos.with_suffix(".tmp")
        temporal.write_text(
            json.dumps(datos, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        temporal.replace(self.recursos)

    def listar_camaras(self) -> list[dict[str, Any]]:
        return [c for c in self._cargar_recursos().get("cameras", []) if c.get("id")]

    def listar_zonas(self, camera_id: str | None = None) -> list[dict[str, Any]]:
        zonas = [z for z in self._cargar_recursos().get("zones", []) if z.get("id")]
        if camera_id is None:
            return zonas
        return [z for z in zonas if z.get("camera_id") == camera_id]

    def listar_beacons(self) -> list[dict[str, Any]]:
        return [b for b in self._cargar_recursos().get("beacons", []) if b.get("id")]

    def actualizar_beacon(
        self, beacon_id: str, estado: dict[str, Any]
    ) -> dict[str, Any] | None:
        """Registra el heartbeat de la baliza (RNF-14) y devuelve su estado.

        El agente llama `checked_at` al instante del chequeo y el modelo de
        datos lo llama `last_seen_at`; se renombra aquí para que las dos
        implementaciones guarden exactamente lo mismo.
        """
        datos = self._cargar_recursos()
        beacons = datos.get("beacons", [])
        indice = next(
            (i for i, b in enumerate(beacons) if b.get("id") == beacon_id), None
        )
        if indice is None:
            return None
        actualizada = {
            **beacons[indice],
            "online": estado["online"],
            "battery_pct": estado.get("battery_pct"),
            "last_seen_at": estado.get("checked_at"),
        }
        beacons[indice] = actualizada
        datos["beacons"] = beacons
        self._guardar_recursos(datos)
        return actualizada

    # --- reporte ---
    def reportar(
        self, filtros: dict[str, Any], pagina: int, limite: int
    ) -> dict[str, Any]:
        seleccion = [
            d for d in self._cargar() if _solapa(d, filtros) and _coincide(d, filtros)
        ]
        seleccion.sort(key=lambda d: _instante(d["detected_at"]), reverse=True)
        inicio = (pagina - 1) * limite
        return {
            # El total y el resumen se calculan sobre toda la selección, no
            # sobre la página: el prevencionista pide totales del período.
            "total": len(seleccion),
            "resumen": _resumen(seleccion),
            "incidentes": seleccion[inicio : inicio + limite],
        }


# ==================== Reporte ====================

# Estado del aviso a la baliza, y estado del ciclo de vida de un incidente.
# Se repiten aquí porque la API no los puede pedir a PostgreSQL si no hay base.
ESTADOS_BALIZA = ("alerted", "failed", "skipped_offline")
ESTADOS_INCIDENTE = ("open", "reviewed", "closed", "false_positive")


def _solapa(dato: dict[str, Any], filtros: dict[str, Any]) -> bool:
    """¿El episodio toca el periodo pedido?

    El rango no filtra por el momento de la detección sino por si el episodio
    **solapa** el periodo: una infracción que empezó antes de `desde` y sigue
    abierta cuenta, porque para saber qué pasó en un turno, lo que estaba
    pasando mientras tanto importa tanto como lo que empezó ahí.
    """
    desde, hasta = filtros.get("desde"), filtros.get("hasta")
    if desde is None and hasta is None:
        return True
    inicio = _instante(dato["detected_at"])
    if hasta is not None and inicio > hasta:
        return False
    fin = _instante(dato["ended_at"]) if dato.get("ended_at") else None
    return not (desde is not None and fin is not None and fin < desde)


def _coincide(dato: dict[str, Any], filtros: dict[str, Any]) -> bool:
    """Cumple los filtros de igualdad: cámara, zona, tipo, estado y baliza."""
    for campo in ("camera_id", "zone_id", "status"):
        valor = filtros.get(campo)
        if valor is not None and dato.get(campo) != valor:
            return False
    tipo = filtros.get("violation_type")
    if tipo is not None:
        # El incidente guarda el tipo principal (`violation_type`) y la lista
        # completa (`violation_types`); el filtro sirve con cualquiera de los dos.
        tipos = dato.get("violation_types") or []
        if dato.get("violation_type") != tipo and tipo not in tipos:
            return False
    baliza = filtros.get("beacon_status")
    if baliza is not None and (dato.get("beacon_alert") or {}).get("status") != baliza:
        return False
    return True


def _resumen(incidentes: list[dict[str, Any]]) -> dict[str, Any]:
    """Totales del periodo, sobre toda la selección y no sobre la página.

    Distingue dos cosas que no son lo mismo: si el **aviso terminó** (tiene
    `ended_at`, es decir, la persona dejó de infringir) y si la **revisión
    terminó** (`status`, que lo decide una persona, no el agente). Por eso el
    resumen cuenta `en_curso`/`terminados` por el cierre del aviso y deja el
    estado de revisión en `por_estado`.
    """
    duraciones = [
        (_instante(d["ended_at"]) - _instante(d["started_at"])).total_seconds()
        for d in incidentes
        # Solo cuenta lo que empezó y terminó: a un aviso en curso todavía no
        # se le puede pedir duración.
        if d.get("started_at") and d.get("ended_at")
    ]
    balizas = dict.fromkeys(ESTADOS_BALIZA, 0)
    estados = dict.fromkeys(ESTADOS_INCIDENTE, 0)
    terminados = 0
    for d in incidentes:
        terminados += bool(d.get("ended_at"))
        alerta = (d.get("beacon_alert") or {}).get("status")
        if alerta in balizas:
            balizas[alerta] += 1
        if d.get("status") in estados:
            estados[d["status"]] += 1
    return {
        "total": len(incidentes),
        "en_curso": len(incidentes) - terminados,
        "terminados": terminados,
        "por_estado": estados,
        "duracion_media_s": (
            round(sum(duraciones) / len(duraciones), 1) if duraciones else None
        ),
        "balizas": balizas,
    }


def _condiciones_reporte(filtros: dict[str, Any]) -> tuple[str, list[Any]]:
    """Traduce los filtros del reporte a la cláusula WHERE de PostgreSQL.

    El rango compara con la detección (que está indexada) y con el cierre,
    aplicando el mismo criterio de solape que `_solapa`: lo que seguía
    ocurriendo dentro del periodo cuenta aunque haya empezado antes.
    """
    condiciones: list[str] = []
    parametros: list[Any] = []
    if filtros.get("hasta") is not None:
        condiciones.append("detected_at <= %s")
        parametros.append(filtros["hasta"])
    if filtros.get("desde") is not None:
        condiciones.append("(ended_at IS NULL OR ended_at >= %s)")
        parametros.append(filtros["desde"])
    for campo in ("camera_id", "zone_id", "status"):
        if filtros.get(campo) is not None:
            condiciones.append(f"{campo} = %s")
            parametros.append(filtros[campo])
    tipo = filtros.get("violation_type")
    if tipo is not None:
        condiciones.append("(%s = ANY(violation_types) OR violation_type = %s)")
        parametros.extend([tipo, tipo])
    baliza = filtros.get("beacon_status")
    if baliza is not None:
        condiciones.append("beacon_alert_status = %s")
        parametros.append(baliza)
    where = f"WHERE {' AND '.join(condiciones)} " if condiciones else ""
    return where, parametros


# ==================== PostgreSQL ====================

COLUMNAS = (
    "id, camera_id, zone_id, detected_at, violation_type, violation_types, "
    "confidence, evidence_path, beacon_alert_status, beacon_alert_latency_ms, "
    "person_track_id, status, created_at, event, episode_id, ping_count, "
    "started_at, last_ping_at, ended_at"
)
FILTROS_PERMITIDOS = ("zone_id", "camera_id", "violation_type", "status")

COLUMNAS_CAMARA = "id, name, rtsp_url, location, active, last_frame_at, created_at"
COLUMNAS_ZONA = "id, camera_id, name, polygon, suppression_s, active"
# `ip` es INET; se castea a texto para que la respuesta sea la misma que da el
# almacenamiento JSON, que guarda la dirección como cadena.
COLUMNAS_BALIZA = (
    "id, zone_id, name, ip::text, duration_s, sound, message, "
    "online, battery_pct, last_seen_at"
)


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


def _camara_desde_fila(fila: tuple) -> dict[str, Any]:
    (camera_id, name, rtsp_url, location, active, last_frame_at, created_at) = fila
    return {
        "id": camera_id,
        "name": name,
        "rtsp_url": rtsp_url,
        "location": location,
        "active": active,
        "last_frame_at": (
            last_frame_at.astimezone(timezone.utc) if last_frame_at else None
        ),
        "created_at": created_at.astimezone(timezone.utc),
    }


def _zona_desde_fila(fila: tuple) -> dict[str, Any]:
    (zona_id, camera_id, name, polygon, suppression_s, active) = fila
    return {
        "id": zona_id,
        "camera_id": camera_id,
        "name": name,
        "polygon": polygon,
        "suppression_s": suppression_s,
        "active": active,
    }


def _baliza_desde_fila(fila: tuple) -> dict[str, Any]:
    (
        baliza_id, zone_id, name, ip, duration_s, sound, message,
        online, battery_pct, last_seen_at,
    ) = fila
    return {
        "id": baliza_id,
        "zone_id": zone_id,
        "name": name,
        "ip": ip,
        "duration_s": duration_s,
        "sound": sound,
        "message": message,
        "online": online,
        "battery_pct": battery_pct,
        "last_seen_at": (
            last_seen_at.astimezone(timezone.utc) if last_seen_at else None
        ),
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
            raise AlmacenNoDisponible("Database schema is not initialized") from exc
        except psycopg.errors.UndefinedColumn as exc:
            raise AlmacenNoDisponible("Database schema is outdated") from exc
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

    # --- recursos ---
    def listar_camaras(self) -> list[dict[str, Any]]:
        filas = self._ejecutar(
            f"SELECT {COLUMNAS_CAMARA} FROM cameras ORDER BY id", ()
        )
        return [_camara_desde_fila(fila) for fila in filas]

    def listar_zonas(self, camera_id: str | None = None) -> list[dict[str, Any]]:
        if camera_id is None:
            filas = self._ejecutar(
                f"SELECT {COLUMNAS_ZONA} FROM zones ORDER BY id", ()
            )
        else:
            filas = self._ejecutar(
                f"SELECT {COLUMNAS_ZONA} FROM zones WHERE camera_id = %s ORDER BY id",
                (camera_id,),
            )
        return [_zona_desde_fila(fila) for fila in filas]

    def listar_beacons(self) -> list[dict[str, Any]]:
        filas = self._ejecutar(
            f"SELECT {COLUMNAS_BALIZA} FROM beacons ORDER BY id", ()
        )
        return [_baliza_desde_fila(fila) for fila in filas]

    def actualizar_beacon(
        self, beacon_id: str, estado: dict[str, Any]
    ) -> dict[str, Any] | None:
        """Registra el heartbeat de la baliza (RNF-14) y devuelve su estado.

        El `RETURNING` evita una segunda consulta, y además solo la baliza
        existente devuelve fila: una inexistente no inventa un registro.
        """
        filas = self._ejecutar(
            "UPDATE beacons SET online = %s, battery_pct = %s, last_seen_at = %s "
            f"WHERE id = %s RETURNING {COLUMNAS_BALIZA}",
            (
                estado["online"],
                estado.get("battery_pct"),
                estado.get("checked_at"),
                beacon_id,
            ),
        )
        return _baliza_desde_fila(filas[0]) if filas else None

    # --- reporte ---
    def reportar(
        self, filtros: dict[str, Any], pagina: int, limite: int
    ) -> dict[str, Any]:
        """Reporte con totales del periodo y la página de incidentes.

        El resumen se calcula en SQL sobre toda la selección, no sobre la
        página: el prevencionista pide totales del período.
        """
        where, parametros = _condiciones_reporte(filtros)
        filas = self._ejecutar(
            "SELECT count(*) AS total, "
            "count(*) FILTER (WHERE ended_at IS NULL) AS en_curso, "
            "count(*) FILTER (WHERE ended_at IS NOT NULL) AS terminados, "
            "count(*) FILTER (WHERE status = 'open') AS abiertos, "
            "count(*) FILTER (WHERE status = 'reviewed') AS en_revision, "
            "count(*) FILTER (WHERE status = 'closed') AS cerrados, "
            "count(*) FILTER (WHERE status = 'false_positive') AS falsos_positivos, "
            "count(*) FILTER (WHERE beacon_alert_status = 'alerted') AS alertadas, "
            "count(*) FILTER (WHERE beacon_alert_status = 'failed') AS fallidas, "
            "count(*) FILTER (WHERE beacon_alert_status = 'skipped_offline') AS sin_baliza, "
            "avg(EXTRACT(EPOCH FROM (ended_at - started_at))) AS duracion_media "
            f"FROM incidents {where}",
            tuple(parametros),
        )
        (total, en_curso, terminados, abiertos, en_revision, cerrados,
         falsos_positivos, alertadas, fallidas, sin_baliza,
         duracion_media) = filas[0]

        pagina_filas = self._ejecutar(
            f"SELECT {COLUMNAS} FROM incidents {where}"
            "ORDER BY detected_at DESC LIMIT %s OFFSET %s",
            (*parametros, limite, (pagina - 1) * limite),
        )
        return {
            "total": total,
            "resumen": {
                "total": total,
                "en_curso": en_curso,
                "terminados": terminados,
                "por_estado": {
                    "open": abiertos,
                    "reviewed": en_revision,
                    "closed": cerrados,
                    "false_positive": falsos_positivos,
                },
                "duracion_media_s": (
                    round(float(duracion_media), 1)
                    if duracion_media is not None
                    else None
                ),
                "balizas": {
                    "alerted": alertadas,
                    "failed": fallidas,
                    "skipped_offline": sin_baliza,
                },
            },
            "incidentes": [_desde_fila(fila) for fila in pagina_filas],
        }


def obtener_almacen() -> Almacen:
    """Devuelve el almacenamiento configurado en CASCOVISION_STORAGE."""

    tipo = os.getenv("CASCOVISION_STORAGE", "json").lower()
    if tipo == "postgres":
        return AlmacenPostgres()
    if tipo == "json":
        return AlmacenJSON(ARCHIVO)
    raise AlmacenNoDisponible(f"Unknown storage: {tipo}")
