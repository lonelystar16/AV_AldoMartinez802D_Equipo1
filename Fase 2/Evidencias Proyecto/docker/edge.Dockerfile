# Agente Edge de CascoVision (YOLO26 + ByteTrack, CPU). Contexto de build: raiz
# del repositorio. El modelo no va en la imagen: se monta desde models/.
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
# En Linux el lock resuelve torch contra el indice CUDA y trae ~3 GB de paquetes
# nvidia-*, cuda-* y triton. La inferencia del servidor es en CPU (AD-08): se
# excluyen del sync (se detectan en el lock, para no mantener la lista a mano) y
# torch y torchvision se instalan aparte desde el indice CPU, con las mismas
# versiones que fija el lock.
RUN EXCLUIR=$(grep -oE '^name = "(nvidia-[a-z0-9-]+|cuda-[a-z0-9-]+|triton|torch|torchvision)"' uv.lock \
        | cut -d'"' -f2 | sort -u | sed 's/^/--no-install-package /' | tr '\n' ' ') \
    && uv sync --frozen --no-dev --no-install-project --group yolo $EXCLUIR \
    && uv pip install --python .venv/bin/python \
        --index-url https://download.pytorch.org/whl/cpu \
        torch==2.14.1 torchvision==0.29.1 \
    # El agente carga el .onnx primero (tarea 4.3). Sin onnxruntime, Ultralytics
    # intentaria instalarlo en tiempo de ejecucion.
    && uv pip install --python .venv/bin/python onnxruntime==1.31.1

# El motor sigue en Yolo/modelamiento (ver el "shortcut" de src/edge/agente.py).
COPY ["Fase 2/Evidencias Proyecto/src/edge", "/app/Fase 2/Evidencias Proyecto/src/edge"]
COPY ["Fase 2/Evidencias Proyecto/Yolo/modelamiento", "/app/Fase 2/Evidencias Proyecto/Yolo/modelamiento"]

RUN useradd --system --uid 10001 --no-create-home app \
    && mkdir -p /data/edge "/app/Fase 2/Evidencias Proyecto/incidents" \
    && chown -R app /data/edge "/app/Fase 2/Evidencias Proyecto/incidents"
USER app
CMD ["python", "Fase 2/Evidencias Proyecto/src/edge/agente.py", "--config", "/config/edge.json", "--sin-ventana"]
