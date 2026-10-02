# API REST de CascoVision

## Estado

Propuesta de contrato para revisión del equipo, basada en el SRS v0.2. Solo
`GET /health` está implementado; las rutas de incidentes siguientes aún no lo
están. Los valores propuestos que requieren acuerdo están listados al final.

## Propósito

La API REST permite registrar incidentes de seguridad detectados por el agente
Edge, consultar su historial y verificar el estado general del sistema.

La API no procesa directamente el video. El agente Edge realiza la detección
local y envía únicamente los eventos necesarios.

## URL base

Durante el desarrollo local:

```text
http://localhost:8000
```

La documentación automática estará disponible en:

```text
http://localhost:8000/docs
```

## Autenticación propuesta

El SRS (RF-17 y RNF-06) requiere autenticación para la API mediante inicio de
sesión y tokens JWT con expiración. El contrato propuesto para las rutas
protegidas usa:

```http
Authorization: Bearer <token>
```

Los tokens y credenciales reales deben configurarse mediante variables de
entorno. No deben incluirse directamente en el código ni en este documento.

## Propuesta de endpoints de incidentes

### Activar la baliza (interfaz externa)

```http
POST /alert
```

Esta ruta pertenece a la interfaz de la baliza, no a la API REST. El agente Edge
envía la orden directamente a la baliza, sin pasar por la API (SRS §4.1 y
RF-07).

### Registrar un incidente

```http
POST /incidents
```

Registra un incidente detectado por el agente Edge (RF-05). La API debe
almacenar la evidencia con los rostros difuminados automáticamente (RF-06).

Solicitud de ejemplo:

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

Campos y validaciones propuestos:

| Campo | Requerido | Validación propuesta |
| --- | --- | --- |
| `camera_id` | Sí | Identificador no vacío de la cámara registrada. |
| `zone_id` | Sí | Identificador no vacío de la zona asociada a la detección. |
| `detected_at` | Sí | Fecha ISO 8601 con zona horaria. |
| `violation_type` | Sí | `missing_helmet` o `missing_reflective_vest` (RF-02, RF-03). |
| `confidence` | Sí | Número entre `0` y `1`, inclusive. |
| `evidence_path` | Sí | Referencia no vacía a la imagen; la API debe guardar y entregar la evidencia difuminada. |
| `beacon_alert.status` | Sí | `alerted`, `failed` o `skipped_offline`, según CU-04. |
| `beacon_alert.latency_ms` | Sí | Entero no negativo si se intentó alertar; `null` si estaba fuera de línea. |

La API asigna un identificador y `created_at`, y crea el incidente en estado
`open` (traducción propuesta de “abierto” en RF-14).

Respuesta propuesta `201 Created`:

```json
{
  "id": "incident-001",
  "status": "open",
  "created_at": "2026-01-15T14:30:02Z"
}
```

Códigos propuestos:

- `201 Created`: incidente registrado.
- `401 Unauthorized`: token ausente, inválido o vencido.
- `403 Forbidden`: token válido sin permiso para registrar incidentes.
- `422 Unprocessable Entity`: cuerpo o campos inválidos (validación de FastAPI).
- `500 Internal Server Error`: error interno.

### Consultar incidentes

```http
GET /incidents
```

Obtiene el historial de incidentes para el dashboard. El orden propuesto es
`detected_at` descendente.

Parámetros opcionales:

| Parámetro | Tipo | Descripción |
| --- | --- | --- |
| `from` | fecha/hora | Fecha inicial del período |
| `to` | fecha/hora | Fecha final del período |
| `zone_id` | texto | Filtra por zona |
| `status` | texto | `open`, `reviewed`, `closed` o `false_positive` (RF-14) |
| `camera_id` | texto | Filtra por cámara |
| `violation_type` | texto | `missing_helmet` o `missing_reflective_vest` |
| `page` | entero | Página desde `1`; valor predeterminado propuesto: `1` |
| `limit` | entero | Elementos por página; valor predeterminado propuesto: `20`, máximo propuesto: `100` |

Las fechas deben incluir zona horaria; `from` y `to` son límites inclusivos.
Se propone responder `422` si una fecha no es válida, `from > to`, o la
paginación queda fuera de rango.

Respuesta propuesta `200 OK`:

```json
{
  "items": [
    {
      "id": "incident-001",
      "camera_id": "camara-01",
      "zone_id": "zona-norte",
      "detected_at": "2026-01-15T14:30:00Z",
      "violation_type": "missing_helmet",
      "confidence": 0.94,
      "evidence_path": "incidents/2026/01/15/incident-001.jpg",
      "beacon_alert": {
        "status": "alerted",
        "latency_ms": 820
      },
      "status": "open",
      "created_at": "2026-01-15T14:30:02Z"
    }
  ],
  "page": 1,
  "limit": 20,
  "total": 1
}
```

Códigos propuestos:

- `200 OK`: consulta realizada correctamente; `items` puede estar vacío.
- `401 Unauthorized`: token ausente, inválido o vencido.
- `403 Forbidden`: token válido sin permiso para consultar incidentes.
- `422 Unprocessable Entity`: filtros o paginación inválidos.
- `500 Internal Server Error`: error interno.

### Consultar un incidente

```http
GET /incidents/{incident_id}
```

Obtiene el detalle de un incidente específico. La respuesta propuesta contiene
los mismos campos que cada elemento de `GET /incidents`.

Códigos propuestos:

- `200 OK`: incidente encontrado.
- `401 Unauthorized`: token ausente, inválido o vencido.
- `403 Forbidden`: token válido sin permiso para consultar incidentes.
- `404 Not Found`: incidente inexistente.
- `422 Unprocessable Entity`: formato inválido de `incident_id`.
- `500 Internal Server Error`: error interno.

### Consultar el estado del sistema

```http
GET /health
```

Verifica si la API está disponible.

Respuesta esperada:

```json
{
  "status": "ok",
  "service": "cascovision-api"
}
```

Este endpoint podrá utilizarse para monitoreo y comprobaciones básicas de
disponibilidad.

## Reglas propuestas comunes

- Las fechas de solicitud deben usar ISO 8601 con zona horaria; las respuestas
  se expresan en UTC con sufijo `Z`.
- Las respuestas deben utilizar formato JSON.
- Los errores de validación usan el formato estándar de FastAPI (`detail`); los
  demás errores entregan un mensaje descriptivo sin detalles sensibles.
- Las imágenes de evidencia se almacenan y muestran con los rostros difuminados
  automáticamente, según RF-06.
- La API no debe almacenar claves, contraseñas ni tokens en el código fuente.

## Decisiones que requieren acuerdo del equipo

- Confirmar los nombres de los campos y los valores de `violation_type` y
  `beacon_alert.status`.
- Confirmar si el identificador del incidente será opaco (`incident-001`) o
  tendrá un formato específico, como UUID.
- Confirmar el almacenamiento de evidencia y qué componente aplica el difuminado
  antes de persistir y servir la imagen (RF-06).
- Definir qué roles pueden registrar, consultar y gestionar incidentes (RF-16,
  RF-17 y RNF-07).
- Confirmar los límites de paginación propuestos y el orden de resultados.
- Implementar los endpoints y pruebas unitarias y de integración después de
  aprobar el contrato.
