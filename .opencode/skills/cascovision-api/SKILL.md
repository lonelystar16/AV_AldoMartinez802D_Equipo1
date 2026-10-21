---
name: API REST de CascoVision
description: API FastAPI de CascoVision - rutas de incidentes, almacenamiento dual JSON/PostgreSQL, migraciones SQL, autenticación por token y reglas de validación. Úsalo al trabajar en src/api, db/migrations, tests/ de la API o docs/API.md.
---

# API REST de CascoVision

## Rutas implementadas

| Método | Ruta | Auth | Qué hace |
| --- | --- | --- | --- |
| GET | `/health` | pública | Estado del proceso HTTP. No comprueba PostgreSQL, el agente Edge ni la baliza |
| POST | `/incidents` | `Bearer EDGE_API_TOKEN` | Registra un incidente informado por el agente Edge |
| GET | `/incidents` | abierta | Historial, del más reciente al más antiguo, con filtros y paginación |
| GET | `/incidents/{incident_id}` | abierta | Detalle de un incidente |

La documentación interactiva vive en `/docs`.

## Estructura

- `src/api/app/main.py` — rutas, modelos Pydantic y validación.
- `src/api/app/almacen.py` — persistencia. Define el protocolo `Almacen` y dos
  implementaciones: `AlmacenJSON` y `AlmacenPostgres`.
- `db/migrations/` — esquema SQL, se aplican en orden.

## Almacenamiento

Se elige con la variable `CASCOVISION_STORAGE`:

- `json` (por defecto): un archivo local con escritura atómica. Pensado para
  desarrollo y pruebas. **No usar con varios procesos a la vez** (no hay
  bloqueo de archivo).
- `postgres`: el almacenamiento de la arquitectura.

Variables:

| Variable | Uso |
| --- | --- |
| `CASCOVISION_STORAGE` | `json` o `postgres` |
| `CASCOVISION_INCIDENTES` | Ruta del archivo JSON. Por defecto `db/incidents.json` |
| `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD` | Obligatorias con `postgres` |
| `POSTGRES_HOST`, `POSTGRES_PORT` | Por defecto `localhost` y `5432` |
| `EDGE_API_TOKEN` | Token compartido con el agente Edge. Obligatorio para `POST /incidents` |

La API **no lee `.env`**: las variables tienen que estar en el entorno del
proceso.

### Migraciones

```bash
psql -d cascovision -f "Fase 2/Evidencias Proyecto/db/migrations/001_create_incidents.sql"
psql -d cascovision -f "Fase 2/Evidencias Proyecto/db/migrations/002_add_tracking_fields.sql"
```

Cada migración se aplica una vez y en orden. Si falta una, la capa de
persistencia responde `503` con un mensaje que lo dice
("Incident schema is outdated" / "not initialized"), no un error genérico.

## Modelo de incidente

Campos que envía el agente Edge:

| Campo | Validación |
| --- | --- |
| `camera_id`, `zone_id` | No vacíos ni solo espacios |
| `detected_at` | ISO 8601 **con zona horaria** |
| `violation_type` | `missing_helmet` o `missing_reflective_vest` |
| `violation_types` | Lista opcional de las dos anteriores |
| `confidence` | Entre 0 y 1 |
| `evidence_path` | Relativa: sin `/` inicial, sin `..`, sin `\` y sin `:` |
| `beacon_alert.status` | `alerted`, `failed` o `skipped_offline` |
| `beacon_alert.latency_ms` | Entero ≥ 0 o `null` |
| `person_track_id` | Opcional. Identificador de seguimiento de ByteTrack |

La validación de `evidence_path` existe para que una ruta manipulada no escape
del directorio de evidencias. No la relajes sin revisar el consumidor.

Códigos de error de `POST /incidents`:
- `401` — token ausente o incorrecto.
- `422` — cuerpo o campos inválidos.
- `503` — token sin configurar, PostgreSQL no disponible o migraciones pendientes.

El token se compara con `secrets.compare_digest`, sin fugas por temporización.

## Pruebas

```bash
uv run pytest
```

`tests/test_health.py` y `tests/test_incidents.py`. Por defecto corren contra
el almacenamiento JSON en un archivo temporal. Con `CASCOVISION_TEST_POSTGRES=1`
y las variables `POSTGRES_*` corren contra PostgreSQL, vaciando la tabla antes
de cada prueba.

Al agregar una ruta: agrega su prueba en el mismo commit. La cobertura actual
de `POST /incidents` incluye 401 por token ausente/incorrecto, 503 por token no
configurado, 422 por confianza y tipo de violación inválidos, 422 por fecha sin
zona horaria, 422 por rutas de evidencia no relativas, orden por fecha,
filtros, paginación y 404.

## Pendiente (del SRS v0.3)

- Autenticación de usuarios (RF-17, JWT) y permisos por rol (RNF-07). Hoy las
  rutas `GET` están abiertas. Ver `docs/API.md`.
- Servir el archivo de evidencia: `evidence_path` es solo una referencia.
- Cambio de estado de un incidente (revisado, cerrado, falso positivo) desde el
  dashboard (CU-07).

## Referencias

- `references/almacenamiento.md` — cómo añadir un campo o un backend nuevo.
