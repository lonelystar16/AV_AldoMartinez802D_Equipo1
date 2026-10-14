# API REST de CascoVision

## Estado

API inicial basada en el SRS v0.3 (borrador, 09-10-2026). Están implementados
`GET /health` y `POST /incidents`; las demás rutas descritas más abajo son
propuestas futuras.

## Propósito

La API REST permitirá registrar incidentes de seguridad detectados por el agente
Edge, consultar su historial y verificar la disponibilidad del proceso HTTP.
La API no procesa directamente el video.

## URL base

Durante el desarrollo local:

```text
http://localhost:8000
```

La documentación automática en `/docs` muestra las rutas implementadas.

## Endpoint implementado

### Consultar el estado del proceso HTTP

```http
GET /health
```

Esta ruta es pública y no requiere autenticación. Comprueba únicamente que el
proceso HTTP de la API está disponible; no verifica PostgreSQL, el agente Edge,
el dashboard ni la baliza zonal.

Respuesta implementada:

```json
{
  "status": "ok",
  "service": "cascovision-api"
}
```

- `200 OK`: proceso HTTP disponible.

## Registrar un incidente (implementado)

```http
POST /incidents
Authorization: Bearer <EDGE_API_TOKEN>
```

El agente Edge registra un incidente después de intentar activar directamente
la baliza asociada a la zona. La API guarda los datos en PostgreSQL; no recibe
ni procesa la imagen, solo conserva una ruta relativa interna como referencia.

Solicitud:

```json
{
  "camera_id": "camara-01",
  "zone_id": "zona-norte",
  "detected_at": "2026-01-15T14:30:00Z",
  "violation_type": "missing_helmet",
  "confidence": 0.94,
  "evidence_path": "incidents/2026/01/15/incident-001.jpg",
  "beacon_alert": {
    "status": "alerted",
    "latency_ms": 820
  }
}
```

Validaciones: `camera_id` y `zone_id` no vacíos; `detected_at` con zona
horaria; `violation_type` igual a `missing_helmet` o
`missing_reflective_vest`; `confidence` entre `0` y `1`; `evidence_path`
relativa, sin `..`, barras invertidas ni prefijo de unidad; y estado de baliza
igual a `alerted`, `failed` o `skipped_offline`. `latency_ms` es un entero no
negativo o `null`.

Respuesta `201 Created`:

```json
{
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "open",
  "created_at": "2026-01-15T14:30:02Z"
}
```

- `401 Unauthorized`: token ausente o incorrecto.
- `503 Service Unavailable`: token o configuración de PostgreSQL ausentes,
  PostgreSQL no disponible o migración pendiente.
- `422 Unprocessable Entity`: cuerpo o campos inválidos.

Para preparar PostgreSQL, aplicar una vez la migración
`db/migrations/001_create_incidents.sql`. La API usa `POSTGRES_DB`,
`POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_HOST` (predeterminado
`localhost`) y `POSTGRES_PORT` (predeterminado `5432`). El token compartido del
agente se configura en `EDGE_API_TOKEN`. `.env.example` contiene solo valores
de ejemplo; las variables deben estar disponibles en el entorno del proceso.

La ruta de evidencia es solo una referencia: la API todavía no guarda ni sirve
el archivo y esta implementación no aplica difuminado facial.

## Contrato propuesto, no implementado

Las siguientes secciones describen el contrato futuro y no representan rutas
disponibles en la API actual.

### Autenticación futura (JWT)

El SRS (RF-17 y RNF-06) requiere autenticación mediante inicio de sesión y
tokens JWT con expiración. El contrato propuesto para las rutas protegidas usa:

```http
Authorization: Bearer <token>
```

Los tokens y credenciales reales deben configurarse mediante variables de
entorno. No deben incluirse directamente en el código ni en este documento.

### Activar la baliza (interfaz externa)

```http
POST /alert
```

Esta es una interfaz externa de la baliza, no una ruta de la API REST. El agente
Edge enviará la orden directamente a la baliza, sin pasar por la API.

### Consultar incidentes

```http
GET /incidents
```

Consulta propuesta para el historial del dashboard, ordenado por
`detected_at` descendente.

Parámetros propuestos: `from`, `to`, `zone_id`, `status`, `camera_id`,
`violation_type`, `page` y `limit`. La página inicial propuesta es `1`, el
límite predeterminado `20` y el máximo `100`.

Códigos propuestos: `200 OK`, `401 Unauthorized`, `403 Forbidden`,
`422 Unprocessable Entity` y `500 Internal Server Error`.

### Consultar un incidente

```http
GET /incidents/{incident_id}
```

Consulta propuesta del detalle de un incidente.

Códigos propuestos: `200 OK`, `401 Unauthorized`, `403 Forbidden`,
`404 Not Found`, `422 Unprocessable Entity` y `500 Internal Server Error`.

## Reglas propuestas comunes

- Las fechas de solicitud usarán ISO 8601 con zona horaria; las respuestas se
  expresarán en UTC con sufijo `Z`.
- Las respuestas usarán formato JSON.
- Los errores de validación usarán el formato estándar de FastAPI (`detail`).
- El difuminado facial de las evidencias es un requisito futuro; el componente
  responsable y el mecanismo de acceso deben definirse antes de implementarlo.
- La API no almacenará claves, contraseñas ni tokens en el código fuente.

## Decisiones que requieren acuerdo del equipo

- Confirmar los campos y valores de `violation_type` y `beacon_alert.status`.
- Definir el almacenamiento de evidencia y el mecanismo de acceso; `evidence_path`
  actualmente solo conserva una ruta relativa interna.
- Definir autenticación de usuarios y permisos por rol para las futuras rutas del
  dashboard. `POST /incidents` usa el token compartido acordado para el agente Edge.
- Definir los roles que podrán registrar, consultar y gestionar incidentes.
- Confirmar los límites de paginación y el orden de resultados.
- Implementar las rutas futuras y sus pruebas después de aprobar ese contrato.
