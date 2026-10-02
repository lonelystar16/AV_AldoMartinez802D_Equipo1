# API REST de CascoVision

## Estado

API inicial y propuesta de contrato para revisión del equipo, basada en el SRS
v0.2 (borrador, 24-09-2026). Solo `GET /health` está implementado; las rutas
de incidentes descritas más abajo son propuestas futuras.

## Propósito

La API REST permitirá registrar incidentes de seguridad detectados por el agente
Edge, consultar su historial y verificar la disponibilidad del proceso HTTP.
La API no procesa directamente el video.

## URL base

Durante el desarrollo local:

```text
http://localhost:8000
```

La documentación automática en `/docs` muestra únicamente las rutas
implementadas actualmente.

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

### Registrar un incidente

```http
POST /incidents
```

Registra un incidente detectado por el agente Edge (RF-05). El difuminado facial
de las evidencias es un requisito futuro (RF-06); el componente responsable, el
mecanismo de acceso y el almacenamiento de las evidencias están pendientes de
definición.

Solicitud propuesta:

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

Validaciones propuestas:

| Campo | Validación |
| --- | --- |
| `camera_id`, `zone_id` | Identificador no vacío. |
| `detected_at` | Fecha ISO 8601 con zona horaria. |
| `violation_type` | `missing_helmet` o `missing_reflective_vest`. |
| `confidence` | Número entre `0` y `1`, inclusive. |
| `evidence_path` | Referencia no vacía; almacenamiento y acceso pendientes. |
| `beacon_alert.status` | `alerted`, `failed` o `skipped_offline`. |
| `beacon_alert.latency_ms` | Entero no negativo, o `null` si estaba fuera de línea. |

Respuesta y códigos propuestos:

```json
{
  "id": "incident-001",
  "status": "open",
  "created_at": "2026-01-15T14:30:02Z"
}
```

- `201 Created`: incidente registrado.
- `401 Unauthorized`: token ausente, inválido o vencido.
- `403 Forbidden`: token válido sin permiso.
- `422 Unprocessable Entity`: cuerpo o campos inválidos.
- `500 Internal Server Error`: error interno.

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
- Confirmar si el identificador será opaco (`incident-001`) o UUID.
- Confirmar el almacenamiento de evidencia y el mecanismo de acceso.
- Definir los roles que podrán registrar, consultar y gestionar incidentes.
- Confirmar los límites de paginación y el orden de resultados.
- Implementar las rutas y pruebas después de aprobar este contrato.
