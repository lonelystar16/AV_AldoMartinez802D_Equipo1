# API REST de CascoVision

## Estado

Documento preliminar. Los endpoints descritos aún no están implementados y
podrán ajustarse durante la etapa de construcción.

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

## Autenticación

Los endpoints protegidos utilizarán un token enviado en la cabecera:

```http
Authorization: Bearer <token>
```

Los tokens y credenciales reales deben configurarse mediante variables de
entorno. No deben incluirse directamente en el código ni en este documento.

## Endpoints preliminares

### Activar la baliza

```http
POST /alert
```

Envía una orden directa desde el agente Edge hacia la baliza zonal. Esta
comunicación no pasa por la API, para reducir la latencia y permitir que la
alerta funcione aunque la API no esté disponible.

### Registrar un incidente

```http
POST /incidents
```

Registra en la API un incidente detectado por el agente Edge.

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
    "requested": true,
    "success": true
  }
}
```

Respuesta esperada:

```json
{
  "id": "incident-001",
  "status": "registered",
  "created_at": "2026-01-15T14:30:02Z"
}
```

Códigos principales:

- `201 Created`: incidente registrado correctamente.
- `400 Bad Request`: datos inválidos.
- `401 Unauthorized`: token ausente o inválido.
- `500 Internal Server Error`: error interno.

### Consultar incidentes

```http
GET /incidents
```

Obtiene el historial de incidentes registrados para el dashboard.

Parámetros opcionales:

| Parámetro | Tipo | Descripción |
| --- | --- | --- |
| `from` | fecha/hora | Fecha inicial del período |
| `to` | fecha/hora | Fecha final del período |
| `zone_id` | texto | Filtra por zona |
| `violation_type` | texto | Filtra por tipo de infracción |
| `page` | entero | Número de página |
| `limit` | entero | Cantidad máxima de resultados |

Respuesta esperada:

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
      "beacon_alert": {
        "requested": true,
        "success": true
      }
    }
  ],
  "page": 1,
  "limit": 20,
  "total": 1
}
```

Códigos principales:

- `200 OK`: consulta realizada correctamente.
- `401 Unauthorized`: token ausente o inválido.
- `500 Internal Server Error`: error interno.

### Consultar un incidente

```http
GET /incidents/{incident_id}
```

Obtiene el detalle de un incidente específico.

Códigos principales:

- `200 OK`: incidente encontrado.
- `401 Unauthorized`: token ausente o inválido.
- `404 Not Found`: incidente inexistente.
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

## Reglas generales

- Las fechas deben utilizar el formato ISO 8601.
- Las respuestas deben utilizar formato JSON.
- Los errores deben informar un código y un mensaje descriptivo.
- Las evidencias fotográficas deben conservar los rostros difuminados.
- La API no debe almacenar claves, contraseñas ni tokens en el código fuente.
- Los nombres definitivos de endpoints y campos deben validarse antes de la
  implementación.

## Pendientes

- Confirmar los nombres definitivos de los endpoints.
- Definir el esquema final de la base de datos.
- Definir los roles y permisos de usuarios.
- Definir el formato definitivo de las evidencias fotográficas.
- Implementar pruebas unitarias y de integración.
