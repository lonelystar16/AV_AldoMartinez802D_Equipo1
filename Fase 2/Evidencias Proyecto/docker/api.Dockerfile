# API REST de CascoVision (FastAPI). Contexto de build: raiz del repositorio.
FROM python:3.12-slim-bookworm

# libpq5: psycopg la necesita en tiempo de ejecucion para hablar con PostgreSQL.
RUN apt-get update \
    && apt-get install -y --no-install-recommends libpq5 \
    && rm -rf /var/lib/apt/lists/*
COPY --from=ghcr.io/astral-sh/uv:0.13.4 /uv /usr/local/bin/uv

WORKDIR /app
ENV UV_NO_CACHE=1 UV_LINK_MODE=copy UV_COMPILE_BYTECODE=1 PYTHONUNBUFFERED=1 \
    PATH="/app/.venv/bin:$PATH"

# Dependencias primero: esta capa solo se rehace si cambia el lock.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

# El codigo busca la carpeta "Fase 2" para ubicar su raiz: se conserva el layout.
COPY ["Fase 2/Evidencias Proyecto/src/api", "/app/Fase 2/Evidencias Proyecto/src/api"]

RUN useradd --system --uid 10001 --no-create-home app
USER app
EXPOSE 8000
CMD ["python", "Fase 2/Evidencias Proyecto/src/api/servidor.py", "--host", "0.0.0.0", "--port", "8000"]
