# Receptor simulado de la baliza (solo desarrollo y pruebas, tarea 4.6). Contexto
# de build: raiz del repositorio. Solo usa la biblioteca estandar de Python.
FROM python:3.12-slim-bookworm

WORKDIR /app
ENV PYTHONUNBUFFERED=1 SIM_HOST=0.0.0.0 SIM_PORT=8081 SIM_LOG_PATH=/data/alerts.jsonl
COPY ["Fase 2/Evidencias Proyecto/src/firmware/receptor-sim/server.py", "/app/server.py"]

RUN useradd --system --uid 10001 --no-create-home app \
    && mkdir -p /data && chown app /data
USER app
EXPOSE 8081
CMD ["python", "/app/server.py"]
