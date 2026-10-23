"""Punto de entrada de la API REST de CascoVision."""

import os
import secrets
from datetime import datetime, timezone
from pathlib import PurePosixPath
from typing import Literal
from uuid import UUID, uuid4

from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field, field_validator, model_validator

from . import almacen, config

# Carga el .env del proyecto si existe. Las variables ya presentes en el
# entorno tienen prioridad, de modo que se puede sobreescribir sin editar el
# archivo. Ver `config.cargar_env`.
config.cargar_env()

app = FastAPI(title="CascoVision API")
bearer = HTTPBearer(auto_error=False)

ViolationType = Literal["missing_helmet", "missing_reflective_vest"]
IncidentStatus = Literal["open", "reviewed", "closed", "false_positive"]
# Momento del ciclo de vida del aviso de una persona sin EPP. El agente no
# silencia los avisos repetidos: los mantiene vivos y la API registra cuando
# empezo y cuando termino el registro.
IncidentEvent = Literal["inicio", "ping", "fin"]


class BeaconAlert(BaseModel):
    """Resultado de la orden que el agente Edge envió a la baliza zonal."""

    status: Literal["alerted", "failed", "skipped_offline"]
    latency_ms: int | None = Field(ge=0)


class IncidentCreate(BaseModel):
    """Incidente informado por el agente Edge.

    El agente genera un ``episode_id`` al iniciar el registro y lo reenvía en
    cada ping y en el cierre. Así la API actualiza el mismo registro en lugar
    de abrir uno nuevo cada vez que la persona sigue sin EPP.
    """

    camera_id: str = Field(min_length=1)
    zone_id: str = Field(min_length=1)
    detected_at: datetime
    violation_type: ViolationType
    confidence: float = Field(ge=0, le=1)
    evidence_path: str = Field(min_length=1)
    beacon_alert: BeaconAlert
    person_track_id: int | None = Field(default=None, ge=0)
    violation_types: list[ViolationType] | None = None
    event: IncidentEvent = "inicio"
    episode_id: UUID | None = None
    occurred_at: datetime | None = None
    ping_count: int | None = Field(default=None, ge=0)

    @field_validator("camera_id", "zone_id")
    @classmethod
    def identifiers_are_not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("must not be blank")
        return value

    @field_validator("detected_at")
    @classmethod
    def detected_at_has_timezone(cls, value: datetime) -> datetime:
        if value.utcoffset() is None:
            raise ValueError("detected_at must include a timezone")
        return value

    @field_validator("occurred_at")
    @classmethod
    def occurred_at_has_timezone(cls, value: datetime | None) -> datetime | None:
        if value is not None and value.utcoffset() is None:
            raise ValueError("occurred_at must include a timezone")
        return value

    @field_validator("evidence_path")
    @classmethod
    def evidence_path_is_relative(cls, value: str) -> str:
        path = PurePosixPath(value)
        if (
            not value.strip()
            or "\\" in value
            or ":" in value
            or path.is_absolute()
            or ".." in path.parts
        ):
            raise ValueError("evidence_path must be an internal relative path")
        return value

    @model_validator(mode="after")
    def episode_is_tracked(self):
        """Un ping o un cierre sin episodio no podría actualizarse.

        Se valida sobre el modelo completo porque `episode_id` puede venir sin
        enviar, y en ese caso Pydantic no ejecuta los validadores de campo.
        """
        if self.event in ("ping", "fin") and self.episode_id is None:
            raise ValueError("episode_id is required for ping and fin events")
        return self


class IncidentCreated(BaseModel):
    id: UUID
    status: Literal["open"]
    created_at: datetime
    event: IncidentEvent = "inicio"
    episode_id: UUID | None = None


class Incident(BaseModel):
    """Incidente devuelto por las rutas de consulta."""

    id: UUID
    camera_id: str
    zone_id: str
    detected_at: datetime
    violation_type: ViolationType
    violation_types: list[ViolationType] | None = None
    confidence: float
    evidence_path: str
    beacon_alert: BeaconAlert
    person_track_id: int | None = None
    status: IncidentStatus
    created_at: datetime
    event: IncidentEvent = "inicio"
    episode_id: UUID | None = None
    # Registros anteriores al ciclo de aviso no traen estos campos, por eso el
    # valor por defecto y la tolerancia a None.
    ping_count: int = 0
    started_at: datetime | None = None
    last_ping_at: datetime | None = None
    ended_at: datetime | None = None

    @field_validator("ping_count", mode="before")
    @classmethod
    def ping_count_defaults_to_zero(cls, value) -> int:
        return 0 if value is None else value


def require_edge_token(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
) -> None:
    expected = os.getenv("EDGE_API_TOKEN")
    if not expected:
        raise HTTPException(status_code=503, detail="Edge API token is not configured")
    if credentials is None or not secrets.compare_digest(
        credentials.credentials, expected
    ):
        raise HTTPException(
            status_code=401,
            detail="Invalid or missing bearer token",
            headers={"WWW-Authenticate": "Bearer"},
        )


def get_store() -> almacen.Almacen:
    try:
        return almacen.obtener_almacen()
    except almacen.AlmacenNoDisponible as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


def _store_call(funcion, *args):
    try:
        return funcion(*args)
    except almacen.ReferenciaIncidenteInvalida as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except almacen.AlmacenNoDisponible as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.get("/health")
def health_check() -> dict[str, str]:
    """Devuelve el estado básico de disponibilidad de la API."""

    return {"status": "ok", "service": "cascovision-api"}


@app.get("/config")
def config_check() -> dict:
    """Informa de la configuración efectiva, sin exponer valores secretos.

    Sirve para verificar desde el navegador que la API leyó el `.env` y que
    el token está configurado, sin revelar su valor.
    """

    estado = config.estado_configuracion()
    faltantes = config.faltantes_obligatorias()
    return {
        "status": "ok" if not faltantes else "incompleta",
        "almacenamiento": estado["almacenamiento"],
        "token_configurado": estado["token_configurado"],
        "archivo_env": estado["archivo_env"],
        "variables_obligatorias_faltantes": faltantes,
    }


@app.post("/incidents", status_code=201, response_model=IncidentCreated)
def create_incident(
    incident: IncidentCreate,
    _: None = Depends(require_edge_token),
    store: almacen.Almacen = Depends(get_store),
) -> IncidentCreated:
    """Persiste un aviso del agente Edge.

    Con ``event="inicio"`` se crea el registro. Con ``event="ping"`` o
    ``event="fin"`` el mismo registro se actualiza, usando el ``episode_id``
    como llave: así el aviso periódico no duplica incidentes y el cierre
    fija cuándo terminó la infracción.
    """

    record = incident.model_dump(mode="json")
    ahora = datetime.now(timezone.utc).isoformat()
    episodio = record.get("episode_id")

    if incident.event in ("ping", "fin"):
        existente = _store_call(store.buscar_episodio, episodio)
        if existente is None:
            # El episodio no está en la API: se crea con los datos del aviso,
            # para no perder el registro si el inicio quedó en la cola local.
            record["id"] = str(uuid4())
            record["status"] = "open"
            record["created_at"] = ahora
            record["started_at"] = incident.detected_at.isoformat()
        else:
            record["id"] = existente["id"]
            record["status"] = existente["status"]
            record["created_at"] = existente["created_at"]
            record["started_at"] = existente.get("started_at")
        record["last_ping_at"] = (incident.occurred_at or datetime.now(timezone.utc)).isoformat()
        record["ended_at"] = record["last_ping_at"] if incident.event == "fin" else None
        _store_call(store.crear_o_actualizar, record)
        return IncidentCreated(
            id=record["id"], status=record["status"], created_at=record["created_at"],
            event=incident.event, episode_id=episodio,
        )

    record["id"] = str(uuid4())
    record["status"] = "open"
    record["created_at"] = ahora
    record["started_at"] = incident.detected_at.isoformat()
    record["last_ping_at"] = None
    record["ended_at"] = None
    _store_call(store.crear_o_actualizar, record)
    return IncidentCreated(
        id=record["id"], status="open", created_at=record["created_at"],
        event=incident.event, episode_id=episodio,
    )


@app.get("/incidents", response_model=list[Incident])
def list_incidents(
    zone_id: str | None = None,
    camera_id: str | None = None,
    violation_type: ViolationType | None = None,
    status: IncidentStatus | None = None,
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=20, ge=1, le=100),
    store: almacen.Almacen = Depends(get_store),
) -> list[Incident]:
    """Consulta el historial de incidentes, del más reciente al más antiguo."""

    filtros = {
        campo: valor
        for campo, valor in {
            "zone_id": zone_id,
            "camera_id": camera_id,
            "violation_type": violation_type,
            "status": status,
        }.items()
        if valor
    }
    return [Incident(**d) for d in _store_call(store.listar, filtros, page, limit)]


@app.get("/incidents/{incident_id}", response_model=Incident)
def get_incident(
    incident_id: str,
    store: almacen.Almacen = Depends(get_store),
) -> Incident:
    """Consulta el detalle de un incidente."""

    datos = _store_call(store.obtener, incident_id)
    if datos is None:
        raise HTTPException(status_code=404, detail="Incident not found")
    return Incident(**datos)
