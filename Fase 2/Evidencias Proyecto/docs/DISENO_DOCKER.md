# Diseño Docker: contenedores, redes y volúmenes

Diseño de la tarea 3.6, basado en el capítulo de arquitectura y despliegue del D2 (§6). Los Dockerfiles y el `docker-compose.yml` reales se construyen en la tarea 4.17.

## 1. Objetivo

Que todo el software de CascoVision se levante con **un solo comando** (`docker compose up -d`) en Linux o Windows con Docker, sin instalar dependencias a mano (RNF-15), y que se reinicie solo ante una falla (RNF-13).

## 2. Servicios

| Servicio | Imagen | Construcción | Puertos | Perfil |
| --- | --- | --- | --- | --- |
| `db` | `postgres:16-alpine` | Imagen oficial | 5432, solo red interna | Siempre |
| `api` | `cascovision/api` | `src/api/Dockerfile` sobre `python:3.12-slim` | 8000, solo red interna (publicado en `dev`) | Siempre |
| `dashboard` | `cascovision/dashboard` | `src/dashboard/Dockerfile`, en dos etapas: `node:20-alpine` compila React y `nginx:1.27-alpine` lo sirve | **443** y 80 publicados | Siempre |
| `edge` | `cascovision/edge` | `src/edge/Dockerfile` sobre `python:3.12-slim` con Ultralytics (CPU) y `opencv-python-headless` | Ninguno | Siempre |
| `rtsp-sim` | `bluenviron/mediamtx` + `ffmpeg` | Imagen oficial y un video pregrabado | 8554, solo red interna | `dev` |
| `receptor-sim` | `cascovision/receptor-sim` | `src/firmware/receptor_sim/Dockerfile` sobre `python:3.12-slim` | 80, solo red interna | `dev` |

**Notas de las imágenes:**
- Ninguna imagen copia el `.env` ni secretos; todo entra por variables de entorno.
- `api` y `edge` corren con un usuario sin privilegios (`USER app`).
- `edge` usa PyTorch de CPU para no arrastrar los ~2 GB de CUDA (la inferencia en el servidor es en CPU, AD-08). Si la tarea 4.3 exporta a ONNX, la imagen cambia `torch` por `onnxruntime`.

## 3. Redes

| Red | Tipo | Servicios | Para qué |
| --- | --- | --- | --- |
| `cascovision` | `bridge` interna del proyecto | Todos | Comunicación por nombre de servicio (`api:8000`, `db:5432`) |

- Solo `dashboard` publica puertos hacia la LAN. `api` y `db` no son alcanzables desde fuera del servidor (AD-07).
- `edge` sale hacia las cámaras (RTSP 554) y las balizas (HTTP 80) de la LAN por el NAT de Docker; no necesita `network_mode: host`.

## 4. Volúmenes

| Volumen | Montado en | Modo | Contenido | Respaldo |
| --- | --- | --- | --- | --- |
| `pgdata` | `db:/var/lib/postgresql/data` | Lectura y escritura | Base de datos | Diario con `pg_dump` (tarea 4.13) |
| `evidencia` | `edge:/data/incidents` y `api:/data/incidents` | `edge` escribe, `api` solo lee (`:ro`) | Imágenes difuminadas | Diario |
| `edge-datos` | `edge:/data/edge` | Lectura y escritura | Cola de incidentes y caché de configuración | No requiere |
| `modelos` | `edge:/models` | Solo lectura | `cascovision_yolo26s.pt` y `face_detection_yunet_2023mar.onnx` | Ya versionados en `models/` |
| `certificados` | `dashboard:/etc/nginx/certs` | Solo lectura | Certificado HTTPS de la faena | Manual |

`modelos` puede ser un *bind mount* de la carpeta `models/` del repositorio, así actualizar el modelo no exige reconstruir la imagen.

## 5. Variables de entorno por servicio

| Variable | `db` | `api` | `edge` | Descripción |
| --- | --- | --- | --- | --- |
| `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD` | ✓ | ✓ | | Conexión a PostgreSQL |
| `POSTGRES_HOST` = `db` | | ✓ | | Nombre del servicio |
| `CASCOVISION_STORAGE` = `postgres` | | ✓ | | En el despliegue siempre PostgreSQL |
| `CASCOVISION_EVIDENCIA` = `/data/incidents` | | ✓ | ✓ | Raíz del volumen de evidencia |
| `JWT_SECRET` | | ✓ | | Firma de los JWT |
| `EDGE_API_TOKEN` | | ✓ | ✓ | Token del agente Edge (RNF-18) |
| `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, `TWILIO_FROM_NUMBER` | | ✓ | | SMS |
| `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD` | | ✓ | | Correo |
| `API_URL` = `http://api:8000` | | | ✓ | Dirección interna de la API |
| `BALIZA_TOKEN` | | | ✓ | Token de `POST /alert` (RNF-11) |
| `RTSP_USER`, `RTSP_PASSWORD` | | | ✓ | Credenciales de las cámaras; no van en la base de datos |
| `EDGE_COLA` = `/data/edge` | | | ✓ | Cola y caché |
| `TZ` = `America/Santiago` | ✓ | ✓ | ✓ | Zona horaria de los registros |

Frente al `.env.example` actual faltan `API_URL`, `CASCOVISION_EVIDENCIA`, `EDGE_COLA`, `RTSP_USER`, `RTSP_PASSWORD` y `TZ`.

## 6. Orden de arranque y salud

| Servicio | Verificación de salud | Espera a |
| --- | --- | --- |
| `db` | `pg_isready -U $POSTGRES_USER` cada 10 s | |
| `api` | `GET /health` cada 15 s | `db` sano. Aplica las migraciones al iniciar |
| `dashboard` | `GET /` responde | `api` iniciada |
| `edge` | Archivo de latido actualizado en los últimos 30 s | Nada: arranca con la configuración en caché aunque la API no esté (AD-04) |

Todos con `restart: unless-stopped`.

## 7. Esqueleto de `docker-compose.yml`

```yaml
name: cascovision

services:
  db:
    image: postgres:16-alpine
    env_file: .env
    volumes: [pgdata:/var/lib/postgresql/data]
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U $${POSTGRES_USER}"]
      interval: 10s
    restart: unless-stopped

  api:
    build: ./src/api
    env_file: .env
    environment: {POSTGRES_HOST: db, CASCOVISION_STORAGE: postgres}
    volumes: [evidencia:/data/incidents:ro]
    depends_on: {db: {condition: service_healthy}}
    healthcheck:
      test: ["CMD", "python", "-c", "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')"]
      interval: 15s
    restart: unless-stopped

  dashboard:
    build: ./src/dashboard
    ports: ["443:443", "80:80"]
    volumes: [certificados:/etc/nginx/certs:ro]
    depends_on: [api]
    restart: unless-stopped

  edge:
    build: ./src/edge
    env_file: .env
    environment: {API_URL: "http://api:8000"}
    volumes:
      - evidencia:/data/incidents
      - edge-datos:/data/edge
      - ./models:/models:ro
    restart: unless-stopped

  rtsp-sim:
    image: bluenviron/mediamtx:latest
    profiles: [dev]

  receptor-sim:
    build: ./src/firmware/receptor_sim
    profiles: [dev]

volumes: {pgdata: {}, evidencia: {}, edge-datos: {}, certificados: {}}
```

## 8. Comandos

| Objetivo | Comando |
| --- | --- |
| Levantar el sistema | `docker compose up -d` |
| Levantar con simuladores | `docker compose --profile dev up -d` |
| Ver el estado y la salud | `docker compose ps` |
| Ver los registros del agente | `docker compose logs -f edge` |
| Detener sin borrar datos | `docker compose down` |
| Respaldar la base de datos | `docker compose exec db pg_dump -U cascovision cascovision > respaldo.sql` |

## 9. Puntos a confirmar

- Fijar versiones exactas de las imágenes (no `latest`) antes de la entrega.
- Dónde viven los Dockerfiles: hoy el código del agente está en `Yolo/testing y modelamiento/` y debe pasar a `src/edge/` (brecha B-06).
- Cómo se genera el certificado HTTPS para la demo (autofirmado con `openssl`).
