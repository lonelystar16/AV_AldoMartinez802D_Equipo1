# API REST de CascoVision

## Estado

API en construcción, basada en el SRS v0.3 (borrador, 09-10-2026). Están
implementadas, cubiertas por `tests/test_health.py`, `tests/test_incidents.py`,
`tests/test_recursos_reporte.py` y `tests/test_edge_config_api.py`:

| Rutas | Finalidad |
| --- | --- |
| `GET /health`, `POST /incidents`, `GET /incidents`, `GET /incidents/{incident_id}` | El registro de incidentes, que es historia y solo crece |
| `GET /cameras`, `GET /cameras/{id}`, `GET /zones`, `GET /beacons` | El catálogo de recursos, que administra el dashboard |
| `PUT /cameras/{id}`, `PUT /zones/{id}`, `PUT /beacons/{id}` | Alta y edición de esos recursos por el administrador (tarea 4.19, `tests/test_gestion_recursos.py`) |
| `GET /edge/config`, `PUT /edge/beacons/{id}/status` | El lado del agente Edge: qué descarga al arrancar y cómo informa a la API |
| `GET /reports` | El reporte de gestión para el prevencionista |
| `GET /reports/export` | El mismo reporte en PDF o Excel (tarea 4.12, `tests/test_exportar.py`) |
| `POST /auth/login`, `GET /auth/me`, `GET /users`, `POST /users`, `PATCH /users/{id}` | Sesión y usuarios del dashboard (tareas 4.16 y 4.19, `tests/test_auth.py`, `tests/test_usuarios.py`) |
| `PATCH /incidents/{id}`, `GET /incidents/{id}/evidence` | Revisión del incidente (RF-14) y su imagen difuminada (RF-19) |

## Sesión y roles (RF-16, RF-17)

Todas las rutas exigen sesión salvo `GET /health` (pública) y las del agente
Edge (`POST /incidents`, `GET /edge/config`, `PUT /edge/beacons/{id}/status`),
que usan su propio `EDGE_API_TOKEN`. El token del agente no abre las rutas del
dashboard ni al revés.

```http
POST /auth/login
Content-Type: application/json

{"email": "admin@cascovision.local", "password": "..."}
```

Responde `{"access_token": "...", "token_type": "bearer", "expires_at": "...", "user": {...}}`.
El token es un JWT HS256 firmado con `JWT_SECRET` (32+ caracteres; sin él el
login responde `503`) y dura 8 horas, un turno. Se envía como
`Authorization: Bearer <token>`. Correo o clave malos responden `401` con el
mismo mensaje. El tiempo de respuesta sí puede delatar un correo existente,
porque bcrypt solo corre cuando el correo coincide (ver *Pendiente*).

Con PostgreSQL la clave se compara en la base con `crypt()` de pgcrypto
(migración `008_autenticacion.sql`) contra el hash bcrypt de `users`. Con JSON
no hay tabla de usuarios: solo entra el administrador de
`CASCOVISION_ADMIN_EMAIL` / `CASCOVISION_ADMIN_PASSWORD`, pensado para
desarrollo.

| Rol | Consulta incidentes, recursos, reporte y evidencia | Revisa incidentes (`PATCH`) | Usuarios y `/config` |
| --- | --- | --- | --- |
| `supervisor` | Sí | No (`403`) | No (`403`) |
| `prevencionista` | Sí | Sí | No (`403`) |
| `admin` | Sí | Sí | Sí |

`POST /users` (solo admin y solo con PostgreSQL) recibe `email`, `full_name`,
`role`, `password` (12+ caracteres) y `phone` opcional en formato E.164; un
correo repetido responde `409`.

`PATCH /users/{id}` (solo admin y solo con PostgreSQL) cambia `full_name`,
`phone` (`null` lo borra), `role` y `active`; solo los campos enviados. El
correo y la contraseña no se editan. Un usuario desactivado no puede iniciar
sesión ni recibe avisos por correo. El administrador no puede desactivarse ni
quitarse el rol a sí mismo (`409`), así que siempre queda uno activo. Un id
desconocido responde `404`.

`PATCH /incidents/{id}` recibe `{"status": "reviewed" | "closed" | "false_positive" | "open", "comment": "..."}`.
Cerrar o marcar como falso positivo exige comentario (`422` sin él, misma
regla que la migración 006); repetir el estado actual responde `409`. Con
PostgreSQL cada cambio queda en `incident_events` con quién lo hizo.

`GET /incidents/{id}/evidence` devuelve el JPEG que guardó el agente, ya con
los rostros difuminados. Solo entrega archivos dentro de `incidents/`.

Esta versión integra dos implementaciones que se hicieron en paralelo: el
registro con token y PostgreSQL de la rama `development_02.10.2026`, y las
consultas, las pruebas y el almacenamiento JSON de la rama `Yolo26`.

## Propósito

La API registra los incidentes que detecta el agente Edge, permite consultar su
historial y expone el estado del proceso HTTP. No procesa video ni activa la
baliza: el agente Edge envía la orden `POST /alert` directamente a la baliza y
después informa el resultado a la API.

Sirve además de centro de la relación entre los tres procesos. El agente le
pide su configuración al arrancar y le informa el estado de la baliza cada 30
segundos; el dashboard le pide el catálogo de recursos y el reporte. En los
tres casos la API **lee y escribe lo que ya sabe**, nunca manda una orden al
hardware: la baliza recibe su `POST /alert` del agente y del simulador, y una
baliza apagada es una fila que se queda en `online = false`.

## Configuración

| Variable | Uso |
| --- | --- |
| `EDGE_API_TOKEN` | Token compartido que el agente Edge envía como `Bearer` en `POST /incidents`, `GET /edge/config` y `PUT /edge/beacons/{id}/status`. Obligatorio |
| `CASCOVISION_STORAGE` | `json` (por defecto) o `postgres` |
| `CASCOVISION_INCIDENTES` | Ruta del archivo JSON. Por defecto `db/incidents.json` |
| `CASCOVISION_RECURSOS` | Ruta del JSON de cámaras, zonas y balizas. Por defecto `db/recursos.json`. En `postgres`, se ignora |
| `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD` | Conexión a PostgreSQL, obligatorias con `postgres` |
| `POSTGRES_HOST`, `POSTGRES_PORT` | Por defecto `localhost` y `5432` |
| `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`, `SMTP_FROM` | Aviso por correo de cada incidente nuevo (RF-12). Sin `SMTP_HOST` no se envía nada. Puerto 587 con STARTTLS o 465 con TLS; con usuario, nunca entrega la clave sin TLS |

`.env.example` contiene solo valores de ejemplo. Las variables deben estar en el
entorno del proceso; la API no lee el archivo `.env` por sí misma.

### Almacenamiento

- **`json`:** para desarrollo y pruebas sin base de datos. Guarda en un archivo
  con escritura atómica. No usar con varios procesos a la vez.
- **`postgres`:** el almacenamiento de la arquitectura. Antes de usarlo, aplicar en orden las migraciones de `db/migrations/` y después cargar el catálogo inicial:

  ```bash
  psql -d cascovision -f db/migrations/001_create_incidents.sql
  psql -d cascovision -f db/migrations/002_add_tracking_fields.sql
  psql -d cascovision -f db/migrations/003_add_episode_lifecycle.sql
  psql -d cascovision -f db/migrations/004_modelo_recursos.sql
  psql -d cascovision -f db/migrations/005_indices_incidentes.sql
  psql -d cascovision -f db/seed.sql
  ```

  Para una base de datos existente, registrar sus cámaras y zonas reales antes de activar las claves foráneas. Los datos de demostración son opcionales y deben cargarse después de la migración 005.

  `db/seed.sql` carga las cámaras, zonas y balizas de ejemplo; es idempotente
  (`ON CONFLICT DO NOTHING`), así que se puede volver a ejecutar. Lo mismo hace
  `db/recursos.json` para el almacenamiento JSON.

  Las claves foráneas de `incidents` hacia `cameras` y `zones` **aún no se
  crean**, ni en 004 ni en 005: exigen que existan las cámaras y zonas de los
  incidentes ya registrados, y un arranque que falla por datos viejos es peor
  que un arranque sin integridad referencial. Mientras tanto la API valida
  ambos identificadores en su modelo y el reporte los une por igualdad de
  texto; van en una migración aparte cuando exista la semilla.

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
  "violation_types": ["missing_helmet", "missing_reflective_vest"],
  "event": "inicio",
  "episode_id": "0f9a1c2e-1111-4222-8333-444455556666",
  "occurred_at": "2026-01-15T14:30:00Z",
  "ping_count": 0
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
| `event` | Por defecto `inicio`. También `ping` y `fin` (ver ciclo de vida) |
| `episode_id` | Opcional en `inicio`, **obligatorio** en `ping` y `fin` |
| `occurred_at` | Opcional. ISO 8601 con zona horaria: cuándo ocurrió este aviso |
| `ping_count` | Opcional. Entero ≥ 0: pings enviados desde el inicio |

Respuesta `201 Created`:

```json
{
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "open",
  "created_at": "2026-01-15T14:30:02Z",
  "event": "inicio",
  "episode_id": "0f9a1c2e-1111-4222-8333-444455556666"
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

#### Ciclo de vida del aviso (`event`)

El agente Edge no silencia los avisos repetidos de una persona sin EPP: los
mantiene vivos y la API registra cuándo empezó y cuándo terminó el registro.
Cada aviso informa su momento del ciclo:

| `event` | Qué hace la API |
| --- | --- |
| `inicio` | Crea el registro. `started_at` queda fijado en `detected_at` |
| `ping` | **Actualiza** el registro del `episode_id`: sube `ping_count` y `last_ping_at`. No crea un incidente nuevo ni toca la evidencia original |
| `fin` | Actualiza el registro y fija `ended_at`, el momento en que la persona dejó de estar sin EPP |

El `episode_id` lo genera el agente al abrir el registro y lo reenvía en cada
ping y en el cierre. Por eso:

- un ping que llega sin que el `inicio` haya sido posible (por ejemplo, porque
  quedó en la cola local) crea el registro, para no perder el aviso;
- dos personas sin EPP abren dos registros distintos, y la segunda se avisa de
  inmediato aunque la primera esté a mitad de su ventana de ping.

**Aviso por correo (RF-12, CU-05, tarea 4.20).** Cada registro nuevo (un
`inicio`, o un `ping`/`fin` cuyo episodio no existía) envía, después de
responder al agente, un correo a cada usuario **prevencionista activo** con la
zona, la cámara, el EPP faltante, la hora de Santiago y cómo terminó la alerta
de la baliza (si falló o estaba fuera de línea, lo destaca: CU-04 1a y 2a). Si
`face_blurred` es `true` adjunta la evidencia; si no, solo texto (RNF-08). Cada
envío queda en `notifications` como `sent` o `failed`, con hasta 2 intentos de
8 s y el motivo del fallo; el índice único evita avisar dos veces el mismo
incidente. Un fallo del correo nunca cambia la respuesta al agente. Solo con
PostgreSQL. El SMS (RF-11) quedó fuera por decisión del equipo (05-11-2026).

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

### Recursos: `GET /cameras`, `GET /zones`, `GET /beacons`

Catálogo de lectura para el dashboard, con cualquier rol. El administrador los
crea y edita con `PUT` (ver más abajo).

| Ruta | Qué devuelve |
| --- | --- |
| `GET /cameras` | Cámaras IP con `name`, `rtsp_url`, `location`, `active` y `last_frame_at` |
| `GET /cameras/{camera_id}` | Una sola cámara. `404` si no existe |
| `GET /zones` | Todas las zonas, con su `polygon` en coordenadas relativas del cuadro (0..1) y su `suppression_s` |
| `GET /zones?camera_id=` | Solo las zonas de esa cámara. Lista vacía si no tiene |
| `GET /beacons` | Balizas con su `ip`, `duration_s`, `sound`, `message`, `online`, `battery_pct` y `last_seen_at` |

`online` en `false` no es un error: es el estado real de una baliza que aún no
tiene firmware (tarea 4.7) o que está apagada.

### Alta y edición: `PUT /cameras/{id}`, `PUT /zones/{id}`, `PUT /beacons/{id}`

Solo el administrador (`403` para los demás roles). `PUT` crea el recurso si el
`id` no existe y lo reemplaza si existe, y responde `200` con el recurso
guardado. Requiere PostgreSQL: con almacenamiento JSON responde `503`.

```http
PUT /zones/zona-patio
Authorization: Bearer <token de admin>
Content-Type: application/json

{"camera_id": "camara-01", "name": "Patio", "polygon": [[0.1, 0.1], [0.9, 0.1], [0.9, 0.9]],
 "suppression_s": 60, "active": true}
```

| Recurso | Campos | Reglas (`422` si no se cumplen) |
| --- | --- | --- |
| Cámara | `name`, `rtsp_url`, `location`, `active` | URL `rtsp://` o `rtsps://` **sin usuario ni clave** (las credenciales van en `CAMARA_FUENTE` del agente) |
| Zona | `camera_id`, `name`, `polygon`, `suppression_s`, `active` | 3 a 50 puntos con `x` e `y` entre 0 y 1 (relativos al cuadro, como los usa el agente); supresión de 10 a 600 s; la cámara debe existir |
| Baliza | `name`, `ip`, `zone_id`, `duration_s`, `sound`, `message` | IP válida; duración de 1 a 30 s; `sound` es `siren`, `voice` o `beep`; mensaje de hasta 40 caracteres; la zona debe existir |

El `id` va en la ruta: minúsculas, dígitos y guiones, hasta 40 caracteres. Una
IP o una zona que ya usa otra baliza responden `409` (`Beacon IP is already in
use`, `Zone already has a beacon`). No hay `DELETE`: los incidentes apuntan a
cámaras y zonas, así que se desactivan con `active: false`. Ese campo queda
guardado, pero el agente todavía no lo consulta.

El agente Edge vuelve a pedir `GET /edge/config` en cada latido (30 s) y aplica
sin reiniciarse los cambios de **la zona que ya vigila** (polígono y nombre).
Vigila una zona por cámara, la primera por `id`, elegida al arrancar: una zona
nueva de la misma cámara y la URL de la baliza se toman al reiniciar el agente.

En una base con los roles de `db/roles.sql`, el rol de la API necesita los
permisos de escritura de la 4.19: vuelva a ejecutar `roles.sql` después de
actualizar.

### `GET /edge/config`

```http
GET /edge/config?camera_id=camara-01
Authorization: Bearer <EDGE_API_TOKEN>
```

Ruta del lado del agente Edge (I-04). Devuelve la relación **cámara → zona →
baliza** que el agente necesita para trabajar sin repetir lo que el dashboard ya
sabe. Exige el token del agente porque revela direcciones de red: un navegador
que solo pone `GET /edge/config` se queda en `401`, aunque tenga sesión del
dashboard.

```json
{
  "camera_id": "camara-01",
  "camera": {"id": "camara-01", "name": "Camara 01 - Entrada norte", "...": "..."},
  "zone_id": "zona-norte",
  "zone": {"id": "zona-norte", "name": "Zona Norte", "polygon": [[0, 0], [1, 0], [1, 1]], "...": "..."},
  "beacon": {"id": "baliza-01", "ip": "127.0.0.1", "duration_s": 10, "...": "..."}
}
```

- `404`: la cámara no existe, o no tiene zonas configuradas.
- `beacon` puede ser `null` si la zona no tiene baliza.

**El agente no depende de esta ruta para arrancar.** La descarga una sola vez
al empezar, con el mismo timeout corto que usa la baliza, y si algo falla —
API caída, cámara desconocida — sigue con su `config.json`. Además, cuando ese
archivo trae `baliza.url`, la URL local **manda**: es el ajuste fino del sitio
(el puerto del simulador, un túnel) y no la reemplaza lo que diga la API. Lo que
sí sale de la API es la cámara, la zona y el polígono, porque los administra el
dashboard.

### `PUT /edge/beacons/{beacon_id}/status`

```http
PUT /edge/beacons/baliza-01/status
Authorization: Bearer <EDGE_API_TOKEN>
Content-Type: application/json

{"online": true, "battery_pct": 87, "checked_at": "2026-10-28T14:00:00Z"}
```

Ruta del lado del agente Edge (I-05, RNF-14). Cada 30 segundos el agente avisa
si su baliza sigue en línea y con cuánta batería; `checked_at` es opcional y,
si falta, lo pone la API para que el reloj no dependa del del borde. Devuelve la
baliza actualizada.

**Es un parte, no una orden.** Si la API no responde, el agente sigue
analizando: lo único que ocurre es que `GET /beacons` muestra un estado viejo.
También puede no enviarse, cuando la zona no tiene baliza.

- `401`: token ausente o incorrecto.
- `404`: la baliza no existe.
- `422`: `battery_pct` fuera de `0..100`.

### `GET /reports`

Reporte de gestión para el prevencionista (tarea 4.15). Devuelve `total`, un
`resumen` con los totales del período y la página de `incidentes`.

| Parámetro | Valor |
| --- | --- |
| `desde`, `hasta` | ISO 8601 **con zona horaria**. `422` si `desde` viene sin una, o si `desde > hasta` |
| `camera_id`, `zone_id` | Filtro exacto |
| `violation_type` | `missing_helmet` o `missing_reflective_vest`. Coincide con cualquiera de `violation_types`, no solo con el principal |
| `status` | `open`, `reviewed`, `closed` o `false_positive` — el estado de la **revisión** |
| `beacon_status` | `alerted`, `failed` o `skipped_offline` |
| `page` | Desde `1` |
| `limit` | Por defecto `20`, máximo `100` |

#### El rango solapa el período, no filtra por el momento de la detección

`desde`/`hasta` responden a la pregunta *"qué estaba pasando en este turno"* y
no *"qué empezó en este turno"*. Por eso el criterio es:

```sql
detected_at <= :hasta AND (ended_at IS NULL OR ended_at >= :desde)
```

Una infracción que empezó antes de `desde` y seguía abierta **cuenta**, porque
era lo que estaba pasando mientras tanto. Una que terminó antes de `desde` no
cuenta. Un aviso todavía sin `ended_at` no se puede descartar por el rango:
nunca se le puede negar un turno en el que estaba ocurriendo.

#### Cada fila indica cuándo empezó y terminó, y dónde

```json
{
  "id": "550e8400-...", "episode_id": "0f9a1c2e-...",
  "started_at": "2026-10-28T08:00:00Z", "ended_at": "2026-10-28T08:04:30Z",
  "duration_s": 270.0,
  "camera_id": "camara-01", "zone_id": "zona-norte",
  "violation_types": ["missing_helmet"], "status": "open",
  "beacon_alert": {"status": "skipped_offline", "latency_ms": null}
}
```

`duration_s` es la diferencia entre `started_at` y `ended_at`, y es `null`
mientras el aviso siga en curso: a algo abierto todavía no se le puede pedir
duración.

#### El resumen distingue dos cosas que no son lo mismo

```json
{
  "total": 42,
  "en_curso": 3,
  "terminados": 39,
  "por_estado": {"open": 40, "reviewed": 1, "closed": 1, "false_positive": 0},
  "duracion_media_s": 842.5,
  "balizas": {"alerted": 12, "failed": 2, "skipped_offline": 28},
  "por_zona": [{"zone_id": "zona-norte", "zone_name": "Zona norte", "total_incidentes": 12, "alertas_activas": 3}],
  "por_turno": [{"shift_id": 1, "shift_name": "Mañana", "total_incidentes": 18, "alertas_activas": 2}],
  "por_hora": [{"fecha_local": "2026-10-28", "hora_local": 10, "total_incidentes": 4, "alertas_activas": 1}]
}
```

- `en_curso` / `terminados`: hablan del **aviso**. Cuentan si la persona dejó de
  infringir, es decir, si el registro tiene `ended_at`.
- `por_estado`: habla de la **revisión**, que decide una persona y no el agente.
  Un aviso terminado sigue en `open` hasta que alguien lo clasifique, así que
  las dos cuentas no tienen por qué cuadrar y no deberían confundirse.
- `duracion_media_s`: promedia **solo** los avisos que llegaron a terminar.
  Cuando ninguno terminó, es `null` y no `0.0`, que sugeriría lo contrario.
- `balizas`: cómo terminó el aviso a la baliza en cada caso.
- Los totales se calculan sobre **toda** la selección, no sobre la página.

#### Durante la ventana de verificación, `last_ping_at` se congela

El motor espera `GRACIA_VERIFICACION_SEGUNDOS = 30` antes de dar por buena la
mejora de quien se pone el casco o el chaleco, para que un parpadeo del
detector no parta el caso en dos. Dentro de esa ventana no se emite ni `ping`
ni `fin` — un ping diría *"sigue sin EPP"* a quien acaba de ponerse el EPP —,
así que el incidente aparece con un `last_ping_at` de hasta 30 segundos atrás y
con `status = open`. **Es correcto, no es un fallo del agente.** Igual vale para
`ping` y `fin` que llegan con hasta 30 segundos de retardo tras perder de vista
a la persona: es el mismo `GRACIA_CIERRE_SEGUNDOS` que evita abrir un segundo
registro cuando ByteTrack reparte otro id.

Las agrupaciones `por_zona`, `por_turno` y `por_hora` se calculan sobre la
seleccion completa que dejan los filtros, no sobre la pagina. Agrupan por
`detected_at` en hora local `America/Santiago`; `por_hora` incluye fecha y hora,
y `por_turno` respeta los horarios de `shifts`, incluido el turno que cruza
medianoche. Cada grupo informa `total_incidentes` y `alertas_activas` (estado
de revision `open`).

### `GET /reports/export`

```http
GET /reports/export?formato=pdf&desde=2026-10-01T00:00:00-03:00&zone_id=zona-norte
Authorization: Bearer <token>
```

Descarga el reporte como archivo, con cualquier rol (CU-08). `formato` es `pdf`
o `xlsx`, y acepta los mismos filtros que `GET /reports` (`desde`, `hasta`,
`camera_id`, `zone_id`, `violation_type`, `status`, `beacon_status`) con las
mismas validaciones. No pagina: trae toda la selección hasta 5.000 incidentes, y
si hay más el archivo lo advierte.

El archivo dice qué filtros se aplicaron e incluye los totales, las agrupaciones
por zona, turno y hora, y una fila por incidente: inicio, fin, duración, cámara,
zona, infracciones, confianza, resultado de la baliza y estado de la revisión.
Las horas van en hora de Santiago. El Excel trae dos hojas (*Resumen* e
*Incidentes*, con filtros de columna), y un nombre que empiece con `=` queda
como texto, no como fórmula. El PDF usa las fuentes base, que solo tienen
Latin-1: un emoji en un nombre se ve como `?`.

## Reglas comunes

- Las fechas de las respuestas se expresan en UTC con sufijo `Z`.
- Los errores de validación usan el formato estándar de FastAPI (`detail`).
- La API no guarda claves, contraseñas ni tokens en el código fuente.

## Pendiente

- **Sesiones.** Desactivar un usuario no corta un token ya emitido: sigue
  válido hasta que vence (8 h). Tampoco hay límite de intentos de login, y el
  tiempo de respuesta del login distingue un correo existente de uno que no.
- **Contraseñas:** el administrador no puede cambiar ni restablecer la clave de
  otro usuario; hoy se hace en la base.
- **Baliza sin firmware (tarea 4.7).** Hasta que exista, toda baliza se queda
  en `online = false`, `battery_pct = null` y los incidentes terminan en
  `beacon_alert.status = "skipped_offline"`, que es exactamente lo que ocurre.
  El agente ya **está** listo para cambiarlo: envía `PUT /edge/beacons/{id}/status`
  cada 30 segundos y el reporte ya sabe leerlo.

Cerrado en esta entrega: la tarea **4.15** — `GET /edge/config`,
`PUT /edge/beacons/{id}/status` y `GET /reports`, con el reporte en los dos
almacenes y pruebas sin base de datos.
