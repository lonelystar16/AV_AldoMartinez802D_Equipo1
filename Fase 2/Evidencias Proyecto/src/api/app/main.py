"""Punto de entrada de la API REST de CascoVision."""

from datetime import datetime, timezone
from typing import Literal
from uuid import uuid4

from fastapi import FastAPI, HTTPException, Query, status
from pydantic import BaseModel, Field

from . import almacen

app = FastAPI(title="CascoVision API")

TipoViolacion = Literal["missing_helmet", "missing_reflective_vest"]
EstadoBaliza = Literal["alerted", "failed", "skipped_offline"]


class AlertaBaliza(BaseModel):
    """Resultado de la orden enviada a la baliza zonal."""

    status: EstadoBaliza = "skipped_offline"
    latency_ms: int | None = Field(default=None, ge=0)


class Incidente(BaseModel):
    """Registro de una infraccion detectada por el agente Edge."""

    camera_id: str = Field(min_length=1)
    zone_id: str = Field(min_length=1)
    detected_at: str
    violation_type: TipoViolacion
    confidence: float = Field(ge=0.0, le=1.0)
    evidence_path: str = Field(min_length=1)
    beacon_alert: AlertaBaliza = Field(default_factory=AlertaBaliza)
    person_track_id: int | None = None
    violation_types: list[TipoViolacion] | None = None


class IncidenteRegistrado(BaseModel):
    """Respuesta de POST /incidents."""

    id: str
    status: Literal["open"] = "open"
    created_at: str


class ResumenIncidente(BaseModel):
    """Incidente devuelto por las rutas de consulta."""

    id: str
    camera_id: str
    zone_id: str
    detected_at: str
    violation_type: TipoViolacion
    confidence: float
    evidence_path: str
    beacon_alert: AlertaBaliza
    status: str = "open"
    person_track_id: int | None = None
    violation_types: list[TipoViolacion] | None = None


def _ahora() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


@app.get("/health")
def health_check() -> dict[str, str]:
    """Devuelve el estado básico de disponibilidad de la API."""

    return {"status": "ok", "service": "cascovision-api"}


@app.post("/incidents", response_model=IncidenteRegistrado,
          status_code=status.HTTP_201_CREATED)
def registrar_incidente(incidente: Incidente) -> IncidenteRegistrado:
    """Registra un incidente detectado por el agente Edge."""

    datos = almacen.cargar()
    registro = incidente.model_dump()
    registro["id"] = str(uuid4())
    registro["status"] = "open"
    registro["created_at"] = _ahora()
    datos.append(registro)
    almacen.guardar(datos)
    return IncidenteRegistrado(id=registro["id"], created_at=registro["created_at"])


@app.get("/incidents", response_model=list[ResumenIncidente])
def listar_incidentes(
    zone_id: str | None = None,
    camera_id: str | None = None,
    violation_type: TipoViolacion | None = None,
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=20, ge=1, le=100),
) -> list[ResumenIncidente]:
    """Consulta el historial de incidentes, del más reciente al más antiguo."""

    datos = almacen.cargar()
    if zone_id:
        datos = [d for d in datos if d.get("zone_id") == zone_id]
    if camera_id:
        datos = [d for d in datos if d.get("camera_id") == camera_id]
    if violation_type:
        datos = [d for d in datos if d.get("violation_type") == violation_type]
    datos.sort(key=lambda d: d.get("detected_at", ""), reverse=True)
    inicio = (page - 1) * limit
    return [ResumenIncidente(**d) for d in datos[inicio:inicio + limit]]


@app.get("/incidents/{incident_id}", response_model=ResumenIncidente)
def obtener_incidente(incident_id: str) -> ResumenIncidente:
    """Consulta el detalle de un incidente."""

    for datos in almacen.cargar():
        if datos.get("id") == incident_id:
            return ResumenIncidente(**datos)
    raise HTTPException(status_code=404, detail="Incidente no encontrado")
