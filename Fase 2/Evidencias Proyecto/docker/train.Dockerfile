# Entrenamiento del detector de EPP (YOLO26 con CUDA, tarea 4.2). Contexto de build:
# raiz del repositorio. El dataset no va en la imagen: se carga en un volumen
# (ver compose.train.yaml).
FROM python:3.12-slim-bookworm

# libgl1 y libglib2.0-0: las exige opencv-python (la version con GUI que fija el lock).
RUN apt-get update \
    && apt-get install -y --no-install-recommends libgl1 libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*
COPY --from=ghcr.io/astral-sh/uv:0.13.4 /uv /usr/local/bin/uv

WORKDIR /app
ENV UV_NO_CACHE=1 UV_LINK_MODE=copy UV_COMPILE_BYTECODE=1 PYTHONUNBUFFERED=1 \
    PATH="/app/.venv/bin:$PATH" \
    YOLO_AUTOINSTALL=false YOLO_CONFIG_DIR=/tmp/Ultralytics

COPY pyproject.toml uv.lock ./
# A diferencia de edge.Dockerfile, aqui si se quiere el torch del indice CUDA que fija
# el lock en Linux (torch 2.14.1+cu126 con sus paquetes nvidia-*).
RUN uv sync --frozen --no-dev --no-install-project --group yolo

COPY ["Fase 2/Evidencias Proyecto/Yolo/modelamiento", "/app/Fase 2/Evidencias Proyecto/Yolo/modelamiento"]

# Corre como root: escribe runs/ en un bind mount del host, y en Linux el uid del
# propietario de esa carpeta cambia de un equipo a otro. No publica puertos.
ENTRYPOINT ["python", "Fase 2/Evidencias Proyecto/Yolo/modelamiento/entrenamiento.py"]
CMD ["--name", "train-11", "--resume"]
