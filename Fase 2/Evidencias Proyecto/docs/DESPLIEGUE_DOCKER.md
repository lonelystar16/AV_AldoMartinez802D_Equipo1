# Despliegue con Docker

Implementación de [`DISENO_DOCKER.md`](DISENO_DOCKER.md) (tarea 4.17). Todo vive en `Fase 2/Evidencias Proyecto/`: `compose.yaml`, `docker/` (un Dockerfile por servicio y su configuración) y `.env.example`.

## Requisitos

Docker con Compose v2 (Docker Desktop en Windows y macOS, Docker Engine en Linux). No hace falta instalar Python, uv ni PostgreSQL.

## Primer arranque

Desde `Fase 2/Evidencias Proyecto`:

```bash
cp .env.example .env        # en PowerShell: Copy-Item .env.example .env
# editar .env: cambiar todos los valores "cambiar_esto"
# perfil dev: copiar un video a docker/rtsp-sim/video_prueba.mp4 (ver docker/rtsp-sim/README.md)
docker compose --profile dev up -d --build
docker compose ps
```

La primera construcción descarga PyTorch para CPU y tarda varios minutos. `compose.yaml` se niega a arrancar si faltan `POSTGRES_PASSWORD`, `EDGE_API_TOKEN`, `BALIZA_TOKEN`, `JWT_SECRET` o `CASCOVISION_ADMIN_*`.

Cuando `docker compose ps` muestra todo arriba, el dashboard queda en `http://127.0.0.1:8080`: se entra con `CASCOVISION_ADMIN_EMAIL` y `CASCOVISION_ADMIN_PASSWORD` del `.env`, y desde **Usuarios** se crean los prevencionistas y supervisores.

| Perfil | Servicios | Para qué |
| --- | --- | --- |
| (ninguno) | `db`, `api`, `dashboard`, `edge` | Producción en la faena. Requiere `CAMARA_FUENTE` con la URL RTSP real y una baliza real en `docker/edge/config.json` |
| `dev` | además `rtsp-sim`, `receptor-sim`, `mailpit` | Demostración y pruebas: una cámara RTSP que repite `docker/rtsp-sim/video_prueba.mp4`, una baliza simulada y un buzón de correo de prueba |

## Qué se levanta

| Servicio | Imagen | Puerto en este equipo | Salud |
| --- | --- | --- | --- |
| `db` | `postgres:16.15-alpine` | ninguno | `pg_isready` |
| `api` | `cascovision/api` | `127.0.0.1:8000` (`/health`, `/docs`) | `GET /health` |
| `dashboard` | `cascovision/dashboard` (nginx) | `127.0.0.1:8080` (entrar con `CASCOVISION_ADMIN_*`) | |
| `edge` | `cascovision/edge` (CPU) | ninguno | `ultimo_cuadro.jpg` actualizado en el último minuto |
| `rtsp-sim` (dev) | `bluenviron/mediamtx:1.15.0-ffmpeg` | ninguno (`rtsp://rtsp-sim:8554/camara-01` en la red interna) | |
| `receptor-sim` (dev) | `cascovision/receptor-sim` | `127.0.0.1:8081` (`GET /health`: `"alerting": true` mientras suena) | |
| `mailpit` (dev) | `axllent/mailpit:v1.27.10` | `127.0.0.1:8025` (buzón web con los avisos por correo) | |

Los puertos solo se publican en `127.0.0.1`. En la faena se quita el de la API (AD-07).

## Base de datos

Al crear el volumen vacío, `docker/db/00-migrar.sh` aplica las migraciones en el orden de `db/seed/README.md` (001, 002, 003, 004 completo, 005 claves, 006 integridad y auditoría, 007 vistas de reportería). Con `CASCOVISION_SEED=1` carga además los catálogos y los 4 incidentes de demostración; en producción debe ir en `0`. Las migraciones **no se repiten** al reiniciar: para recrear la base hay que borrar el volumen.

```bash
docker compose down -v        # BORRA la base de datos y la evidencia
```

### Respaldo y restauración (tarea 4.13)

Sin instalar PostgreSQL en el equipo: el volcado se hace dentro del contenedor y se copia con `docker compose cp`, que funciona igual en Windows, macOS y Linux (redirigir con `>` en PowerShell 5 puede dañar un archivo binario). Con otro `POSTGRES_USER` o `POSTGRES_DB` en el `.env`, cambiar `cascovision` en los comandos.

```bash
# Respaldo de la base (formato custom de pg_dump)
docker compose exec db pg_dump -Fc -U cascovision -d cascovision -f /tmp/respaldo.dump
docker compose cp db:/tmp/respaldo.dump ./respaldo.dump

# Respaldo de la evidencia (volumen cascovision_evidencia)
docker run --rm -v cascovision_evidencia:/evidencia:ro -v "$PWD":/destino alpine:3.20 \
    tar czf /destino/evidencia.tgz -C /evidencia .

# Restauración: REEMPLAZA los datos actuales de la base
docker compose cp ./respaldo.dump db:/tmp/respaldo.dump
docker compose exec db pg_restore --clean --if-exists --no-owner -U cascovision -d cascovision /tmp/respaldo.dump
```

Probado el 05-11-2026: un respaldo restaurado en una base aparte conserva los mismos conteos de `incidents`, `users`, `incident_events`, `beacons`, `cameras` y `zones`. Para una base fuera de Docker siguen sirviendo `db/backup.ps1` y `db/restore.ps1`, que usan el `pg_dump` del equipo.

## Comandos útiles

| Objetivo | Comando |
| --- | --- |
| Ver registros del agente | `docker compose logs -f edge` |
| Detener sin borrar datos | `docker compose down` |
| Reconstruir tras cambiar código | `docker compose --profile dev up -d --build` |
| Panel de terminal con registros, reinicio y estadísticas | `lazydocker` (opcional, no es dependencia del proyecto) |

## Decisiones y diferencias con el diseño

- **El video de `rtsp-sim` no se versiona** (`.gitignore` excluye `*.mp4`): hay que copiarlo a mano.
- **El dashboard llega a la API por nginx** (`docker/dashboard/nginx.conf`): el navegador solo ve `127.0.0.1:8080` y `/api/` se reenvía al servicio `api` por la red interna, así que la API no necesita CORS.
- **El agente no espera a la API.** Si la API aún no responde al arrancar, usa `docker/edge/config.json` (AD-04); por eso en un arranque en frío el registro dice «la API no respondió GET /edge/config». El agente reintenta en cada latido de 30 s y, cuando la API responde, empieza a informar el estado de la baliza; la zona y el polígono de la base se toman al reiniciarlo (`docker compose restart edge`).
- **Si la cámara no está lista al arrancar, el agente termina y `restart: unless-stopped` lo reintenta.**
- **PyTorch de CPU.** En Linux `uv.lock` resuelve PyTorch contra el índice CUDA (~3 GB de paquetes `nvidia-*`); el Dockerfile los excluye e instala `torch` y `torchvision` del índice CPU, con las versiones del lock. Se agrega `onnxruntime` (no está en el lock) porque el agente carga primero el `.onnx`.
- **El modelo no va en la imagen:** se monta `./models` en solo lectura. Cambiar el modelo no exige reconstruir.
- **El layout `Fase 2/Evidencias Proyecto/` se conserva dentro de las imágenes** porque el código ubica su raíz buscando la carpeta `Fase 2`.
- **`receptor-sim` corre `src/firmware/receptor-sim/server.py`** (tarea 4.6), que solo usa la biblioteca estándar. Exige un `BALIZA_TOKEN` de al menos 32 caracteres y deja cada orden recibida en `/data/alerts.jsonl`: `docker compose exec receptor-sim cat /data/alerts.jsonl`.
- **`JWT_SECRET` va a la API y `CASCOVISION_ADMIN_*` a la base**, que crea ese administrador al iniciarse por primera vez. Cambiar la clave después no recrea el usuario: se hace desde la base o con `POST /users`.
- **Aviso por correo (tarea 4.20):** con `SMTP_HOST` en `.env`, cada incidente nuevo envía un correo a los prevencionistas activos, con la imagen difuminada adjunta, y queda en la tabla `notifications` como `sent` o `failed`. Para la demo: `SMTP_HOST=mailpit` y `SMTP_PORT=1025`, y los correos se ven en http://127.0.0.1:8025.
- **La API monta el volumen `evidencia` en solo lectura** para entregar la imagen difuminada en `GET /incidents/{id}/evidence`.
- **El entrenamiento del modelo no corre en Docker:** en macOS y Windows un contenedor no ve la GPU. Ver `Yolo/README.md`, sección Entrenamiento.
