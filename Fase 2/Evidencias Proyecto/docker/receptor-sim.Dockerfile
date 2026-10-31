# Receptor simulado de la baliza (solo desarrollo y pruebas). Contexto de build:
# raiz del repositorio.
FROM python:3.12-slim-bookworm
COPY --from=ghcr.io/astral-sh/uv:0.13.4 /uv /usr/local/bin/uv

WORKDIR /app
ENV UV_NO_CACHE=1 UV_LINK_MODE=copy UV_COMPILE_BYTECODE=1 PYTHONUNBUFFERED=1 \
    PATH="/app/.venv/bin:$PATH" SIM_LOG=/data/receptor_sim.jsonl

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project
COPY ["Fase 2/Evidencias Proyecto/src/receptor_sim", "/app/receptor_sim"]

RUN useradd --system --uid 10001 --no-create-home app \
    && mkdir -p /data && chown app /data
USER app
EXPOSE 8081
CMD ["uvicorn", "main:app", "--app-dir", "/app/receptor_sim", "--host", "0.0.0.0", "--port", "8081"]
