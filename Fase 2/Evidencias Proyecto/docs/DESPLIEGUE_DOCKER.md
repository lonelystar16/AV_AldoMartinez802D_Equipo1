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

La primera construcción descarga PyTorch para CPU y tarda varios minutos. `compose.yaml` se niega a arrancar si faltan `POSTGRES_PASSWORD`, `EDGE_API_TOKEN` o `BALIZA_TOKEN`.

| Perfil | Servicios | Para qué |
| --- | --- | --- |
| (ninguno) | `db`, `api`, `edge` | Producción en la faena. Requiere `CAMARA_FUENTE` con la URL RTSP real y una baliza real en `docker/edge/config.json` |
| `dev` | además `rtsp-sim`, `receptor-sim` | Demostración y pruebas: una cámara RTSP que repite `docker/rtsp-sim/video_prueba.mp4` y una baliza simulada |

## Qué se levanta

| Servicio | Imagen | Puerto en este equipo | Salud |
| --- | --- | --- | --- |
| `db` | `postgres:16.15-alpine` | ninguno | `pg_isready` |
| `api` | `cascovision/api` | `127.0.0.1:8000` (`/health`, `/docs`) | `GET /health` |
| `edge` | `cascovision/edge` (CPU) | ninguno | `ultimo_cuadro.jpg` actualizado en el último minuto |
| `rtsp-sim` (dev) | `bluenviron/mediamtx:1.15.0-ffmpeg` | ninguno (`rtsp://rtsp-sim:8554/camara-01` en la red interna) | |
| `receptor-sim` (dev) | `cascovision/receptor-sim` | `127.0.0.1:8081` (la «pantalla» de la baliza) | |

Los puertos solo se publican en `127.0.0.1`. En la faena se quita el de la API (AD-07).

## Base de datos

Al crear el volumen vacío, `docker/db/00-migrar.sh` aplica las migraciones en el orden de `db/seed/README.md` (001, 002, 003, 004 completo, 005 claves). Con `CASCOVISION_SEED=1` carga además los catálogos y los 4 incidentes de demostración; en producción debe ir en `0`. Las migraciones **no se repiten** al reiniciar: para recrear la base hay que borrar el volumen.

```bash
docker compose down -v        # BORRA la base de datos y la evidencia
```

Respaldo: `docker compose exec db pg_dump -U cascovision cascovision > respaldo.sql`

## Comandos útiles

| Objetivo | Comando |
| --- | --- |
| Ver registros del agente | `docker compose logs -f edge` |
| Detener sin borrar datos | `docker compose down` |
| Reconstruir tras cambiar código | `docker compose --profile dev up -d --build` |
| Panel de terminal con registros, reinicio y estadísticas | `lazydocker` (opcional, no es dependencia del proyecto) |

## Decisiones y diferencias con el diseño

- **El video de `rtsp-sim` no se versiona** (`.gitignore` excluye `*.mp4`): hay que copiarlo a mano.
- **No hay servicio `dashboard`:** `src/dashboard/` está vacío (tarea 4.18). Se agrega cuando exista código.
- **El agente no espera a la API.** Si la API aún no responde al arrancar, usa `docker/edge/config.json` (AD-04); por eso en un arranque en frío el registro dice «la API no respondió GET /edge/config». Para que lea la configuración de la API, basta `docker compose restart edge` cuando la API ya está sana.
- **Si la cámara no está lista al arrancar, el agente termina y `restart: unless-stopped` lo reintenta.**
- **PyTorch de CPU.** En Linux `uv.lock` resuelve PyTorch contra el índice CUDA (~3 GB de paquetes `nvidia-*`); el Dockerfile los excluye e instala `torch` y `torchvision` del índice CPU, con las versiones del lock. Se agrega `onnxruntime` (no está en el lock) porque el agente carga primero el `.onnx`.
- **El modelo no va en la imagen:** se monta `./models` en solo lectura. Cambiar el modelo no exige reconstruir.
- **El layout `Fase 2/Evidencias Proyecto/` se conserva dentro de las imágenes** porque el código ubica su raíz buscando la carpeta `Fase 2`.
- **`receptor-sim` necesita `src/receptor_sim/`** (tarea 4.6, de Fernando). Hasta que ese commit esté en `qa`, el servicio no se puede construir.
- **Las variables `JWT_SECRET`, Twilio y SMTP del `.env.example` no se pasan a ningún contenedor:** ningún código las lee todavía.
- **El entrenamiento del modelo no corre en Docker:** en macOS y Windows un contenedor no ve la GPU. Ver `Yolo/README.md`, sección Entrenamiento.
