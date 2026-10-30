# API REST de CascoVision

## Estado

API en construcción, basada en el SRS v0.3 (borrador, 09-10-2026). Están
implementadas `GET /health`, `POST /incidents`, `GET /incidents` y
`GET /incidents/{incident_id}`, cubiertas por `tests/test_health.py` y
`tests/test_incidents.py`.

Esta versión integra dos implementaciones que se hicieron en paralelo: el
registro con token y PostgreSQL de la rama `development_02.10.2026`, y las
consultas, las pruebas y el almacenamiento JSON de la rama `Yolo26`.

## Propósito

La API registra los incidentes que detecta el agente Edge, permite consultar su
historial y expone el estado del proceso HTTP. No procesa video ni activa la
baliza: el agente Edge envía la orden `POST /alert` directamente a la baliza y
después informa el resultado a la API.

## Configuración

| Variable | Uso |
| --- | --- |
| `EDGE_API_TOKEN` | Token compartido que el agente Edge envía como `Bearer` en `POST /incidents`. Obligatorio |
| `CASCOVISION_STORAGE` | `json` (por defecto) o `postgres` |
| `CASCOVISION_INCIDENTES` | Ruta del archivo JSON. Por defecto `db/incidents.json` |
| `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD` | Conexión a PostgreSQL, obligatorias con `postgres` |
| `POSTGRES_HOST`, `POSTGRES_PORT` | Por defecto `localhost` y `5432` |

`.env.example` contiene solo valores de ejemplo. Las variables deben estar en el
entorno del proceso; la API no lee el archivo `.env` por sí misma.

### Almacenamiento

- **`json`:** para desarrollo y pruebas sin base de datos. Guarda en un archivo
  con escritura atómica. No usar con varios procesos a la vez.
- **`postgres`:** el almacenamiento de la arquitectura. Antes de usarlo, seguir
  el [orden de migraciones D2 v1.0 y carga de catálogos](../db/seed/README.md):
  001 → 002 → 003 (episodios) → 004 (tablas) → catálogos → 005 (FK e índices).
  Los datos demo son opcionales y se cargan después de la 005. Para una base
  existente, registrar sus cámaras y zonas reales antes de activar las FK.

La capa `src/api/app/almacen.py` encapsula ambas opciones; la API no depende de
cuál se use.

## URL base

```text
http://localhost:8000
```

La documentación automática en `/docs` muestra las rutas implementadas.

## Rutas

### `GET /health`

Pública. Comprueba solo que el proceso HTTP responde; no verifica PostgreSQL,
el agente Edge, el dashboard ni la baliza.

```json
{"status": "ok", "service": "cascovision-api"}
```

### `POST /incidents`

```http
POST /incidents
Authorization: Bearer <EDGE_API_TOKEN>
```

El agente Edge registra un incidente después de intentar activar la baliza de
la zona. La API no recibe la imagen: guarda una ruta relativa interna como
referencia a la evidencia, que el agente ya guardó con los rostros difuminados.

```json
{
  "camera_id": "camara-01",
  "zone_id": "zona-norte",
  "detected_at": "2026-01-15T14:30:00Z",
  "violation_type": "missing_helmet",
  "confidence": 0.94,
  "evidence_path": "incidents/2026/01/15/incidente-143000-000000.jpg",
  "face_blurred": true,
  "beacon_alert": {"status": "alerted", "latency_ms": 820},
  "person_track_id": 7,
  "violation_types": ["missing_helmet", "missing_reflective_vest"]
}
```

| Campo | Validación |
| --- | --- |
| `camera_id`, `zone_id` | No vacíos; con PostgreSQL y la migración 005 deben existir en los catálogos |
| `detected_at` | ISO 8601 **con zona horaria** |
| `violation_type` | `missing_helmet` o `missing_reflective_vest` |
| `confidence` | Entre `0` y `1` |
| `evidence_path` | Relativa: sin `/` inicial, sin `..`, sin `\` y sin `:` (letra de unidad) |
| `face_blurred` | Booleano opcional; Edge lo envía `true` tras difuminar las personas y guardar la imagen. Por defecto `false` |
| `beacon_alert.status` | `alerted`, `failed` o `skipped_offline` |
| `beacon_alert.latency_ms` | Entero ≥ 0 o `null` |
| `person_track_id` | Opcional. Identificador de seguimiento de la persona (ByteTrack) |
| `violation_types` | Opcional. Todas las infracciones de la persona en el evento |

Respuesta `201 Created`:

```json
{
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "open",
  "created_at": "2026-01-15T14:30:02Z"
}
```

- `401 Unauthorized`: token ausente o incorrecto.
- `422 Unprocessable Entity`: cuerpo o campos inválidos, o cámara/zona no
  configurada en PostgreSQL.
- `503 Service Unavailable`: `EDGE_API_TOKEN` sin configurar, PostgreSQL sin
  configurar o caído, o migraciones pendientes.

La API persiste `face_blurred` como una afirmación del agente Edge; no recibe ni
inspecciona la imagen. El agente no reporta el incidente si falla el difuminado
del frame o la escritura de la evidencia.

### `GET /incidents`

Historial ordenado por `detected_at` descendente.

| Parámetro | Valor |
| --- | --- |
| `zone_id`, `camera_id` | Filtro exacto |
| `violation_type` | `missing_helmet` o `missing_reflective_vest` |
| `status` | `open`, `reviewed`, `closed` o `false_positive` |
| `page` | Desde `1` |
| `limit` | Por defecto `20`, máximo `100` |

Respuestas: `200 OK`, `422` si un parámetro es inválido y `503` si el
almacenamiento no está disponible.

### `GET /incidents/{incident_id}`

Detalle de un incidente. `200 OK`, o `404 Not Found` si no existe.

## Reglas comunes

- Las fechas de las respuestas se expresan en UTC con sufijo `Z`.
- Los errores de validación usan el formato estándar de FastAPI (`detail`).
- La API no guarda claves, contraseñas ni tokens en el código fuente.

## Pendiente

- **Autenticación de usuarios (RF-17, JWT) y permisos por rol (RNF-07).** Las
  rutas `GET` quedan abiertas hasta implementarla junto con el dashboard; hoy
  solo `POST /incidents` exige token. Es una de las decisiones abiertas del
  SRS v0.3 (§4.6).
- **Acceso a la evidencia.** `evidence_path` es solo una referencia; la API
  todavía no sirve el archivo.
- **Baliza.** El agente informa `beacon_alert.status = "skipped_offline"` hasta
  que exista la orden `POST /alert` hacia la baliza (firmware, tarea 4.4).
- **Cambio de estado de un incidente** (revisado, cerrado, falso positivo)
  desde el dashboard (CU-07).
