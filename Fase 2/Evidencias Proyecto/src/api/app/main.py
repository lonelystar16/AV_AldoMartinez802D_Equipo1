"""Punto de entrada de la API REST de CascoVision."""

import os
import secrets
from datetime import datetime, timezone
from pathlib import PurePosixPath
from typing import Literal
from uuid import UUID, uuid4

import psycopg
from fastapi import Depends, FastAPI, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field, field_validator


app = FastAPI(title="CascoVision API")
bearer = HTTPBearer(auto_error=False)


class BeaconAlert(BaseModel):
    status: Literal["alerted", "failed", "skipped_offline"]
    latency_ms: int | None = Field(ge=0)


class IncidentCreate(BaseModel):
    camera_id: str = Field(min_length=1)
    zone_id: str = Field(min_length=1)
    detected_at: datetime
    violation_type: Literal["missing_helmet", "missing_reflective_vest"]
    confidence: float = Field(ge=0, le=1)
    evidence_path: str = Field(min_length=1)
    beacon_alert: BeaconAlert

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


def postgres_config() -> dict[str, str | int]:
    required = ("POSTGRES_DB", "POSTGRES_USER", "POSTGRES_PASSWORD")
    if any(not os.getenv(name) for name in required):
        raise HTTPException(status_code=503, detail="PostgreSQL is not configured")
    try:
        port = int(os.getenv("POSTGRES_PORT", "5432"))
    except ValueError as exc:
        raise HTTPException(status_code=503, detail="PostgreSQL port is invalid") from exc
    if not 1 <= port <= 65535:
        raise HTTPException(status_code=503, detail="PostgreSQL port is invalid")
    return {
        "host": os.getenv("POSTGRES_HOST", "localhost"),
        "port": port,
        "dbname": os.environ["POSTGRES_DB"],
        "user": os.environ["POSTGRES_USER"],
        "password": os.environ["POSTGRES_PASSWORD"],
    }


@app.get("/health")
def health_check() -> dict[str, str]:
    """Devuelve el estado básico de disponibilidad de la API."""

    return {"status": "ok", "service": "cascovision-api"}


@app.post("/incidents", status_code=201, response_model=IncidentCreated)
def create_incident(
    incident: IncidentCreate,
    _: None = Depends(require_edge_token),
) -> IncidentCreated:
    """Persiste un incidente informado por el agente Edge."""

    incident_id = uuid4()
    created_at = datetime.now(timezone.utc)
    try:
        with psycopg.connect(**postgres_config()) as connection:
            connection.execute(
                """
                INSERT INTO incidents (
                    id, camera_id, zone_id, detected_at, violation_type,
                    confidence, evidence_path, beacon_alert_status,
                    beacon_alert_latency_ms, status, created_at
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    incident_id,
                    incident.camera_id,
                    incident.zone_id,
                    incident.detected_at,
                    incident.violation_type,
                    incident.confidence,
                    incident.evidence_path,
                    incident.beacon_alert.status,
                    incident.beacon_alert.latency_ms,
                    "open",
                    created_at,
                ),
            )
    except psycopg.OperationalError as exc:
        raise HTTPException(status_code=503, detail="PostgreSQL is unavailable") from exc
    except psycopg.errors.UndefinedTable as exc:
        raise HTTPException(
            status_code=503, detail="Incident schema is not initialized"
        ) from exc

    return IncidentCreated(id=incident_id, status="open", created_at=created_at)
