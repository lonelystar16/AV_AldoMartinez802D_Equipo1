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


class Camera(BaseModel):
    """Cámara IP registrada en el sistema."""

    id: str
    name: str
    rtsp_url: str
    location: str | None = None
    active: bool = True
    last_frame_at: datetime | None = None
    created_at: datetime | None = None


class Zone(BaseModel):
    """Zona de riesgo dentro de una cámara."""

    id: str
    camera_id: str
    name: str
    polygon: list[list[float]]
    suppression_s: int = 60
    active: bool = True


class Beacon(BaseModel):
    """Baliza zonal y su estado según el último heartbeat (RNF-14)."""

    id: str
    zone_id: str | None = None
    name: str
    ip: str
    duration_s: int = 10
    sound: str = "siren"
    message: str | None = None
    # Arranca en false: mientras no exista el firmware de la baliza (tarea 4.7)
    # el reporte muestra `skipped_offline`, que es lo que ocurre de verdad.
    online: bool = False
    battery_pct: int | None = None
    last_seen_at: datetime | None = None


class BeaconStatus(BaseModel):
    """Heartbeat que el agente Edge informa de su baliza (I-05)."""

    online: bool
    battery_pct: int | None = Field(default=None, ge=0, le=100)
    checked_at: datetime | None = None


class EdgeConfig(BaseModel):
    """Configuración que el agente Edge descarga al arrancar (I-04).

    La API no le dice al agente a qué URL llamar: la baliza se dirige por su
    IP, y el agente ya sabe dónde está la API porque él la llamó.
    """

    camera_id: str
    camera: Camera
    zone_id: str
    zone: Zone
    beacon: Beacon | None = None


class ReporteResumen(BaseModel):
    """Totales del periodo consultado, sobre toda la selección.

    `en_curso` y `terminados` hablan del **aviso**: si la persona dejó de
    infringir (tiene `ended_at`). `por_estado` habla de la **revisión**, que
    decide una persona y no el agente. No son la misma cosa, y por eso van
    por separado.
    """

    total: int
    en_curso: int
    terminados: int
    por_estado: dict[str, int]
    # None cuando ningún aviso del periodo llegó a cerrarse: sin cierre no hay
    # duración que promediar, y un 0.0 sugeriría lo contrario.
    duracion_media_s: float | None = None
    balizas: dict[str, int]


class ReporteIncidente(Incident):
    """Fila del reporte: el incidente con su duración calculada."""

    duration_s: float | None = None


class Reporte(BaseModel):
    total: int
    resumen: ReporteResumen
    incidentes: list[ReporteIncidente]


def _fila_reporte(datos: dict) -> ReporteIncidente:
    """Calcula la duración una vez que los campos ya son datetime.

    El almacenamiento JSON devuelve fechas como texto y PostgreSQL como
    datetime; pasar por `Incident` normaliza las dos rutas antes de restar.
    """
    incidente = Incident(**datos)
    duracion = None
    if incidente.started_at and incidente.ended_at:
        duracion = (incidente.ended_at - incidente.started_at).total_seconds()
    return ReporteIncidente(**incidente.model_dump(), duration_s=duracion)


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


# ==================== Recursos: cámaras, zonas y balizas ====================
#
# Son de lectura para el dashboard y de descarga para el agente Edge. Crearlos
# y editarlos no es trabajo de esta API: el catálogo lo carga el administrador
# con db/seed.sql o directamente en la base.


def _buscar(listado: list[dict], identificador: str) -> dict | None:
    return next((d for d in listado if d.get("id") == identificador), None)


@app.get("/cameras", response_model=list[Camera])
def list_cameras(store: almacen.Almacen = Depends(get_store)) -> list[Camera]:
    """Catálogo de cámaras IP del sistema, con su ubicación y si están activas."""

    return [Camera(**d) for d in _store_call(store.listar_camaras)]


@app.get("/cameras/{camera_id}", response_model=Camera)
def get_camera(
    camera_id: str,
    store: almacen.Almacen = Depends(get_store),
) -> Camera:
    """Consulta el detalle de una cámara por su identificador."""

    camara = _buscar(_store_call(store.listar_camaras), camera_id)
    if camara is None:
        raise HTTPException(status_code=404, detail="Camera not found")
    return Camera(**camara)


@app.get("/zones", response_model=list[Zone])
def list_zones(
    camera_id: str | None = None,
    store: almacen.Almacen = Depends(get_store),
) -> list[Zone]:
    """Zonas de riesgo, con su polígono en coordenadas relativas del cuadro.

    Con ``camera_id`` devuelve solo las de esa cámara, que es lo que necesita
    el dashboard para pintar el polígono sobre el video.
    """

    return [Zone(**d) for d in _store_call(store.listar_zonas, camera_id)]


@app.get("/beacons", response_model=list[Beacon])
def list_beacons(store: almacen.Almacen = Depends(get_store)) -> list[Beacon]:
    """Balizas zonales y su estado según el último heartbeat que informaron.

    ``online`` en false no es un error: es el estado real de una baliza que
    aún no tiene firmware (tarea 4.7) o que está apagada.
    """

    return [Beacon(**d) for d in _store_call(store.listar_beacons)]


# ==================== Configuración del agente Edge ====================


@app.get("/edge/config", response_model=EdgeConfig)
def get_edge_config(
    camera_id: str = Query(min_length=1),
    _: None = Depends(require_edge_token),
    store: almacen.Almacen = Depends(get_store),
) -> EdgeConfig:
    """Configuración que el agente Edge descarga una vez al arrancar (I-04).

    Entrega la relación zona → baliza → IP que el agente mantiene en memoria
    para llamar a la baliza por su cuenta. Exige el token del agente porque
    revela direcciones de red; un navegador no llega hasta aquí.

    El agente conserva su ``config.json`` como respaldo: un borde no puede
    depender de la API para arrancar. Si la zona no tiene baliza, el campo
    ``beacon`` viene en null y el agente avisa solo a la API.
    """

    camara = _buscar(_store_call(store.listar_camaras), camera_id)
    if camara is None:
        raise HTTPException(status_code=404, detail="Camera not found")

    zonas = _store_call(store.listar_zonas, camera_id)
    if not zonas:
        raise HTTPException(status_code=404, detail="No zones for this camera")
    # Una zona por cámara en la práctica; si hubiera más, el agente vigila la
    # primera, que es la que informa en su configuración local.
    zona = zonas[0]

    baliza = next(
        (b for b in _store_call(store.listar_beacons) if b.get("zone_id") == zona["id"]),
        None,
    )

    return EdgeConfig(
        camera_id=camera_id,
        camera=Camera(**camara),
        zone_id=zona["id"],
        zone=Zone(**zona),
        beacon=Beacon(**baliza) if baliza else None,
    )


@app.put("/edge/beacons/{beacon_id}/status", response_model=Beacon)
def put_beacon_status(
    beacon_id: str,
    estado: BeaconStatus,
    _: None = Depends(require_edge_token),
    store: almacen.Almacen = Depends(get_store),
) -> Beacon:
    """Registra el heartbeat de la baliza zonal y devuelve su estado (I-05).

    Cada 30 segundos el agente avisa si su baliza sigue en línea y con cuánta
    batería. ``checked_at`` lo pone la API cuando el agente no lo envía, para
    que el reloj del servidor no dependa del de un borde.
    """

    visto = _store_call(
        store.actualizar_beacon,
        beacon_id,
        {
            "online": estado.online,
            "battery_pct": estado.battery_pct,
            "checked_at": (
                estado.checked_at or datetime.now(timezone.utc)
            ).isoformat(),
        },
    )
    if visto is None:
        raise HTTPException(status_code=404, detail="Beacon not found")
    return Beacon(**visto)


# ==================== Reporte ====================


def _zona_horaria_requerida(nombre: str, valor: datetime | None) -> None:
    if valor is not None and valor.utcoffset() is None:
        raise HTTPException(
            status_code=422,
            detail=f"{nombre} must include a timezone",
        )


@app.get("/reports", response_model=Reporte)
def get_report(
    desde: datetime | None = None,
    hasta: datetime | None = None,
    camera_id: str | None = None,
    zone_id: str | None = None,
    violation_type: ViolationType | None = None,
    status: IncidentStatus | None = None,
    beacon_status: Literal["alerted", "failed", "skipped_offline"] | None = None,
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=20, ge=1, le=100),
    store: almacen.Almacen = Depends(get_store),
) -> Reporte:
    """Reporte de incidentes para un periodo, con totales y duraciones.

    Cada fila indica cuándo empezó y cuándo terminó el aviso, en qué cámara y
    en qué zona ocurrió, qué infracciones se le imputan y qué pasó con la
    baliza. El rango ``desde``/``hasta`` no filtra por el momento de la
    detección sino por si el episodio **solapa** el periodo: una infracción que
    empezó antes y seguía abierta cuenta, porque era lo que estaba pasando
    durante ese turno.

    ``duracion_media_s`` solo promedia los incidentes que llegaron a cerrarse.
    Durante la ventana de verificación que el motor aplica antes de cerrar,
    ``last_ping_at`` se congela y el incidente aparece como abierto: es
    correcto, no es un fallo del agente.
    """

    _zona_horaria_requerida("desde", desde)
    _zona_horaria_requerida("hasta", hasta)
    if desde is not None and hasta is not None and desde > hasta:
        raise HTTPException(
            status_code=422, detail="'desde' must not be after 'hasta'"
        )

    filtros = {
        campo: valor
        for campo, valor in {
            "desde": desde,
            "hasta": hasta,
            "camera_id": camera_id,
            "zone_id": zone_id,
            "violation_type": violation_type,
            "status": status,
            "beacon_status": beacon_status,
        }.items()
        if valor is not None
    }
    datos = _store_call(store.reportar, filtros, page, limit)
    return Reporte(
        total=datos["total"],
        resumen=ReporteResumen(**datos["resumen"]),
        incidentes=[_fila_reporte(d) for d in datos["incidentes"]],
    )
