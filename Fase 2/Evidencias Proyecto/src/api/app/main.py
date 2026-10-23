"""Punto de entrada de la API REST de CascoVision."""

import os
import secrets
from datetime import datetime, timezone
from pathlib import PurePosixPath
from typing import Literal
from uuid import UUID, uuid4

from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field, field_validator

from . import almacen


app = FastAPI(title="CascoVision API")
bearer = HTTPBearer(auto_error=False)

ViolationType = Literal["missing_helmet", "missing_reflective_vest"]
IncidentStatus = Literal["open", "reviewed", "closed", "false_positive"]


class BeaconAlert(BaseModel):
    """Resultado de la orden que el agente Edge envió a la baliza zonal."""

    status: Literal["alerted", "failed", "skipped_offline"]
    latency_ms: int | None = Field(ge=0)


class IncidentCreate(BaseModel):
    """Incidente informado por el agente Edge."""

    camera_id: str = Field(min_length=1)
    zone_id: str = Field(min_length=1)
    detected_at: datetime
    violation_type: ViolationType
    confidence: float = Field(ge=0, le=1)
    evidence_path: str = Field(min_length=1)
    beacon_alert: BeaconAlert
    person_track_id: int | None = Field(default=None, ge=0)
    violation_types: list[ViolationType] | None = None

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


class IncidentCreated(BaseModel):
    id: UUID
    status: Literal["open"]
    created_at: datetime


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


@app.post("/incidents", status_code=201, response_model=IncidentCreated)
def create_incident(
    incident: IncidentCreate,
    _: None = Depends(require_edge_token),
    store: almacen.Almacen = Depends(get_store),
) -> IncidentCreated:
    """Persiste un incidente informado por el agente Edge."""

    record = incident.model_dump(mode="json")
    record["id"] = str(uuid4())
    record["status"] = "open"
    record["created_at"] = datetime.now(timezone.utc).isoformat()
    _store_call(store.crear, record)
    return IncidentCreated(id=record["id"], status="open", created_at=record["created_at"])


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
