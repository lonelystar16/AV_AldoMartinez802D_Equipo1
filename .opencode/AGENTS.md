# AGENTS.md — Guía de trabajo de CascoVision

Proyecto APT · Capstone PTY4614 · Duoc UC · Equipo 1 (sección 802D).
Sistema de detección automatizada de EPP mediante visión computacional.

## Idioma

Todo se escribe en **español**: docstrings, comentarios, mensajes de consola,
documentación y nombres de variables del código de aplicación. Los nombres de
clases del modelo y las claves de API van en inglés por convención de
Ultralytics y por el contrato de la API (ver `docs/API.md`).

## Estructura

```
Fase 2/Evidencias Proyecto/
├── src/api/app/          API REST FastAPI (main.py, almacen.py)
├── src/dashboard/        Dashboard React (pendiente)
├── src/edge/             Agente Edge (pendiente: hoy vive en Yolo/)
├── src/firmware/         Firmware de la baliza (pendiente)
├── Yolo/
│   ├── dataset/          Dataset de 5 clases (NO se versiona, ~440 MB)
│   ├── models/           Checkpoints y detector YuNet (SÍ se versionan)
│   ├── runs/detect/      Corridas de entrenamiento
│   └── testing y modelamiento/   Motor, scripts de entrada y evaluación
├── db/migrations/        Esquema SQL de PostgreSQL
├── tests/                Pruebas de la API
└── docs/                 Documentación de la API y diagramas
```

## Comandos

El proyecto usa **uv** como fuente única de dependencias. No hay `requirements.txt`.

```bash
# Sincronizar el entorno (incluye GPU y el grupo de visión por computador)
uv sync --group dev --group yolo

# Pruebas de la API
uv run pytest

# API en desarrollo
uv run uvicorn app.main:app --app-dir "Fase 2/Evidencias Proyecto/src/api" --reload

# Agente Edge (con la API levantada en otra terminal)
uv run python "Fase 2/Evidencias Proyecto/Yolo/testing y modelamiento/monitoreo_api.py"

# Monitoreo local, sin API
uv run python "Fase 2/Evidencias Proyecto/Yolo/testing y modelamiento/monitoreo_v2.py"
```

Variables de entorno: la API **no lee `.env` por sí misma**. Exporta las
variables o defínelas en el entorno del proceso. Ver `.env.example` y
`docs/API.md`.

## Reglas del repositorio

- El **dataset no se versiona** (~440 MB). Las imágenes y etiquetas viven en
  `Yolo/dataset/` y se ignoran por `.gitignore`.
- Los **checkpoints sí se versionan**, pero solo los de `Yolo/models/`. Las
  corridas completas (`Yolo/runs/detect/`) se ignoran, salvo la que se documente.
- En `.gitignore` las rutas usan **barras `/`**: la barra invertida `\` es
  carácter de escape en ese archivo y la regla no aplicaría.
- Los pesos de los modelos base (`yolo26s.pt`) se descargan solos; no se
  versionan.

## Flujo de trabajo

1. Lee `README.md` y el README de la carpeta donde vas a trabajar.
2. Si el cambio toca el detector, las reglas de negocio o las métricas,
   consulta el skill `cascovision-modelo`.
3. Si toca la API o el almacenamiento, consulta `cascovision-api`.
4. Si toca el agente Edge, consulta `cascovision-edge`.
5. Antes de dar por terminado un cambio, actualiza la documentación que
   corresponda (`cascovision-docs`).
6. Las pruebas de la API deben seguir verdes: `uv run pytest`.

## Skills disponibles

| Skill | Cuándo usarlo |
| --- | --- |
| `cascovision-api` | Rutas de la API, almacenamiento JSON/PostgreSQL, migraciones, autenticación |
| `cascovision-edge` | Motor de detección, reglas de EPP, difuminado de rostros, cola y baliza |
| `cascovision-modelo` | Entrenar y evaluar el detector, métricas, RNF-05, dataset |
| `cascovision-docs` | Qué documentación actualizar y con qué cifras |
| `cascovision-git` | Ramas, commits, qué se versiona y qué no |
