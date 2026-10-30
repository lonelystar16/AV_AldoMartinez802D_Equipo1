# Guía de uv para CascoVision

Este documento explica cómo instalar [uv](https://docs.astral.sh/uv/) en
Windows, cómo instalar las dependencias del proyecto y cómo levantar la API y
el agente Edge con un solo comando.

**uv** es el gestor de dependencias y entorno virtual del proyecto. Reemplaza
a la combinación `pip` + `venv` + `requirements.txt`: el entorno queda
declarado en `pyproject.toml`, las versiones exactas quedan fijadas en
`uv.lock`, y el entorno virtual se crea y se mantiene solo.

---

## 1. Instalar uv en Windows 

### Opción A — winget (recomendada)

```powershell
winget install --id=astral-sh.uv -e
```

Cierra y reabre la terminal para que el comando quede en el `PATH`.

### Opción B — instalador oficial

Descárgalo desde <https://docs.astral.sh/uv/getting-started/installation/> y
ejecuta el instalador `.msi` o el `.exe` de PowerShell:

```powershell
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

### Opción C — pip (si ya tienes Python)

```powershell
python -m pip install --user uv
```

### Verificar la instalación

```powershell
uv --version
```

Debe mostrar algo como `uv 0.13.4`. Si el comando no se reconoce, cierra la
terminal y vuelve a abrirla: el instalador añade uv al `PATH` del usuario.

---

## 2. El proyecto en detalle

Todo lo declarado en `pyproject.toml`, que está en la raíz del repositorio.

### Identidad del proyecto

| Campo | Valor |
| --- | --- |
| `name` | `cascovision` |
| `version` | `0.1.0` |
| `description` | CascoVision: deteccion automatizada de EPP mediante vision computacional |
| `requires-python` | `>=3.12` |
| `readme` | `README.md` |

La versión de Python se fija además en `.python-version` (`3.12`), de modo que
uv descarga e instala esa versión exacta si no está en el equipo.

### Dependencias de runtime (`[project.dependencies]`)

Son las de la API REST. La API **no** necesita OpenCV ni PyTorch: eso es del
agente Edge y del detector.

| Paquete | Versión mínima | Para qué |
| --- | --- | --- |
| `fastapi` | `>=0.156.8` | Framework de la API REST |
| `pydantic` | `>=2.14.1` | Validación de los cuerpos de las peticiones |
| `psycopg` | `>=3.3.6` | Driver de PostgreSQL (backend de incidentes) |
| `uvicorn` | `>=0.54.0` | Servidor ASGI que aloja la API |

### Grupo `dev` (`[dependency-groups]`)

Se instala con `uv sync --group dev`. Es lo mínimo para trabajar con la API.

| Paquete | Versión mínima | Para qué |
| --- | --- | --- |
| `pytest` | `>=8.4.1` | Ejecución de las pruebas |
| `httpx` | `>=0.28.1` | Cliente HTTP para las pruebas de la API |

### Grupo `yolo` (`[dependency-groups]`)

Se instala con `uv sync --group yolo`. Es lo que necesita el detector de EPP y
el agente Edge. **No lo necesita la API.**

| Paquete | Versión mínima | Para qué |
| --- | --- | --- |
| `ultralytics` | `>=8.4.183` | Motor de YOLO26. La versión 8.4 es la primera que carga un checkpoint YOLO26 |
| `torch` | `>=2.14.1` | PyTorch |
| `torchvision` | `>=0.29.1` | Utilidades de visión de PyTorch |
| `lap` | `>=0.5.12` | Seguimiento ByteTrack. Ultralytics lo importa de forma directa, así que **no puede faltar** |
| `opencv-python` | `>=4.11,<5.0` | Procesamiento de imagen. El tope de 5.0 es necesario: OpenCV 5 eliminó `cv2.CascadeClassifier`, que usan los scripts de prueba. El motor usa YuNet (`cv2.FaceDetectorYN`), disponible desde 4.5.4 |
| `numpy` | `>=1.26` | Cálculo numérico |

### Índice de PyTorch para CUDA

```toml
[[tool.uv.index]]
name = "pytorch-cu126"
url = "https://download.pytorch.org/whl/cu126"
explicit = true

[tool.uv.sources]
torch = [{ index = "pytorch-cu126", marker = "sys_platform == 'linux' or sys_platform == 'win32'" }]
torchvision = [{ index = "pytorch-cu126", marker = "sys_platform == 'linux' or sys_platform == 'win32'" }]
```

**Por qué hace falta.** PyTorch no publica ruedas con CUDA en PyPI para
Windows: la de PyPI es solo CPU. Por eso `torch` y `torchvision` se toman del
índice oficial de PyTorch, en la variante CUDA 12.6.

`explicit = true` significa que ese índice **solo** se consulta para los
paquetes que lo piden explícitamente. Así el resto de dependencias siguen
viniendo de PyPI, que es lo correcto.

El marcador `sys_platform == 'linux' or sys_platform == 'win32'` deja que en
macOS se use la variante de CPU de PyPI, porque PyTorch no publica ruedas
CUDA para macOS.

**En un equipo sin GPU NVIDIA**, borra el bloque `[tool.uv.sources]` y el
`[[tool.uv.index]]`, y ejecuta `uv lock` de nuevo. Se instalará la variante
de CPU.

### Configuración de pytest

```toml
[tool.pytest.ini_options]
testpaths = ["Fase 2/Evidencias Proyecto/tests"]
pythonpath = ["Fase 2/Evidencias Proyecto/src/api"]
```

`testpaths` hace que `uv run pytest` encuentre las pruebas sin argumentos.
`pythonpath` permite importar `app.main` sin el `sys.path.insert` manual en
cada archivo de prueba.

### Otras opciones

| Opción | Valor | Para qué |
| --- | --- | --- |
| `[tool.uv] package` | `false` | El proyecto no se instala como paquete: no tiene `src/` con un `__init__.py` en la raíz. uv solo gestiona el entorno |

---

## 3. Instalar las dependencias

Desde la raíz del repositorio:

```powershell
# Solo la API (lo mínimo para desarrollar y probar el backend)
uv sync --group dev

# API + detector de EPP y agente Edge (todo el proyecto)
uv sync --group dev --group yolo
```

`uv sync` hace tres cosas a la vez:

1. Descarga la versión de Python que indica `.python-version`, si no está.
2. Crea el entorno virtual en `.venv/`.
3. Instala exactamente las versiones de `uv.lock`.

`uv.lock` es el archivo que fija las versiones exactas. **Se versiona en
Git**, de modo que todo el equipo instala exactamente lo mismo. Se actualiza
con:

```powershell
uv lock          # recalcula el lock tras cambiar pyproject.toml
uv sync          # aplica el lock al entorno
```

Para agregar un paquete:

```powershell
uv add httpx                      # dependencia de runtime
uv add --group dev pytest         # al grupo dev
uv add --group yolo lap           # al grupo yolo
```

Y para quitarlo:

```powershell
uv remove httpx
```

---

## 4. Variables de entorno

La API lee su configuración de las variables de entorno. Hay dos formas de
proveerlas.

### Opción A — archivo `.env` (recomendada)

Copia el ejemplo y completa los valores:

```powershell
cd "Fase 2\Evidencias Proyecto"
copy .env.example .env
```

Edita `.env` y cambia los `cambiar_esto`:

```dotenv
CASCOVISION_STORAGE=json
EDGE_API_TOKEN=un_valor_secreto
```

La API carga este archivo **automáticamente** al arrancar, sin argumentos
adicionales. Las variables ya presentes en el entorno tienen prioridad sobre
las del archivo, así que puedes sobreescribir sin editarlo:

```powershell
$env:EDGE_API_TOKEN="otro_token"; uv run python "Fase 2\Evidencias Proyecto\src\api\servidor.py"
```

> `.env` está en `.gitignore`. Nunca se versiona.

### Opción B — variables en la línea de comandos

```powershell
$env:EDGE_API_TOKEN="un_valor_secreto"
```

En PowerShell el signo `=` es indispensable. En CMD:

```cmd
set EDGE_API_TOKEN=un_valor_secreto
```

### Variables disponibles

| Variable | Obligatoria | Por defecto | Para qué |
| --- | --- | --- | --- |
| `EDGE_API_TOKEN` | **Sí** | — | Token Bearer que el agente Edge envía en `POST /incidents`. Sin ella esa ruta responde `503` |
| `CASCOVISION_STORAGE` | No | `json` | Backend de incidentes: `json` o `postgres` |
| `CASCOVISION_INCIDENTES` | No | `db/incidents.json` | Ruta del archivo JSON |
| `POSTGRES_DB` | Con `postgres` | — | Base de datos |
| `POSTGRES_USER` | Con `postgres` | — | Usuario |
| `POSTGRES_PASSWORD` | Con `postgres` | — | Contraseña |
| `POSTGRES_HOST` | No | `localhost` | Servidor |
| `POSTGRES_PORT` | No | `5432` | Puerto |

El detalle completo está en `docs/API.md`.

---

## 5. Levantar la API

### El comando

```powershell
uv run python "Fase 2\Evidencias Proyecto\src\api\servidor.py"
```

Ese script hace todo: carga el `.env`, verifica la configuración, avisa de lo
que falte y levanta el servidor.

### Opciones

| Opción | Efecto |
| --- | --- |
| `--host 127.0.0.1` | Solo local (por defecto) |
| `--host 0.0.0.0` | Expone en la red local, para que la faena se conecte |
| `--port 8000` | Puerto (por defecto) |
| `--reload` | Recarga automática al cambiar el código |
| `--check` | Solo verifica la configuración y sale, sin levantar nada |
| `--requiere-token` | Falla si falta `EDGE_API_TOKEN`, en vez de solo avisar |

### Ejemplos

```powershell
# Desarrollo local con recarga automática
uv run python "Fase 2\Evidencias Proyecto\src\api\servidor.py" --reload

# Verificar la configuración sin levantar nada
uv run python "Fase 2\Evidencias Proyecto\src\api\servidor.py" --check

# Exponer en la red de la faena
uv run python "Fase 2\Evidencias Proyecto\src\api\servidor.py" --host 0.0.0.0
```

### La alternativa con uvicorn directo

El script es una comodidad. También funciona:

```powershell
uv run uvicorn app.main:app --app-dir "Fase 2\Evidencias Proyecto\src\api" --reload
```

La opción `--app-dir` es necesaria porque el punto de entrada está en
`Fase 2/Evidencias Proyecto/src/api/app/main.py`, no en la raíz del
repositorio.

Si prefieres que uv cargue el `.env` por ti, uv tiene su propia opción:

```powershell
uv run --env-file "Fase 2\Evidencias Proyecto\.env" uvicorn app.main:app --app-dir "Fase 2\Evidencias Proyecto\src\api" --reload
```

### Comprobar que funciona

Con el servidor levantado:

```powershell
# Estado del proceso
curl.exe http://localhost:8000/health

# Configuración efectiva (no expone secretos)
curl.exe http://localhost:8000/config
```

| Servicio | URL |
| --- | --- |
| Estado | <http://localhost:8000/health> |
| Configuración | <http://localhost:8000/config> |
| Documentación interactiva | <http://localhost:8000/docs> |

Respuesta de `/health`:

```json
{"status":"ok","service":"cascovision-api"}
```

Respuesta de `/config`:

```json
{
  "status": "ok",
  "almacenamiento": "json",
  "token_configurado": true,
  "archivo_env": "C:\\...\\Fase 2\\Evidencias Proyecto\\.env",
  "variables_obligatorias_faltantes": []
}
```

El endpoint `/config` informa de si el token está configurado, **nunca de su
valor**.

### Registrar un incidente de prueba

En **PowerShell**, las comillas del JSON se interpretan, así que lo más simple
es usar `Invoke-RestMethod`:

```powershell
$token = "un_valor_secreto"
$incidente = @{
    camera_id     = "camara-01"
    zone_id       = "zona-norte"
    detected_at   = "2026-01-15T14:30:00Z"
    violation_type = "missing_helmet"
    confidence    = 0.94
    evidence_path = "incidents/2026/01/15/x.jpg"
    beacon_alert  = @{ status = "skipped_offline"; latency_ms = $null }
}
Invoke-RestMethod -Uri http://localhost:8000/incidents -Method POST `
    -Headers @{ Authorization = "Bearer $token" } `
    -ContentType "application/json" -Body ($incidente | ConvertTo-Json -Depth 3)
```

Con `curl`, el JSON va en un archivo, para evitar el escapado de comillas:

```powershell
$incidente | ConvertTo-Json -Depth 3 | Set-Content incidente.json
curl.exe -X POST http://localhost:8000/incidents `
  -H "Authorization: Bearer un_valor_secreto" `
  -H "Content-Type: application/json" `
  --data-binary "@incidente.json"
```

Sin el token, la respuesta es `401`. Con el token correcto, `201`.

---

## 6. Pruebas

```powershell
uv run pytest
```

Se ejecutan las pruebas de la API y las de las reglas de negocio del motor
(36 + 16 pruebas). Para más detalle:

```powershell
uv run pytest -v
uv run pytest "Fase 2/Evidencias Proyecto/tests/test_incidents.py"
```

Las pruebas usan el almacenamiento JSON en un archivo temporal, así que no
tocan los datos reales.

---

## 7. El agente Edge y el detector

Requieren el grupo `yolo`:

```powershell
# Monitoreo local, sin API
uv run python "Fase 2\Evidencias Proyecto\Yolo\modelamiento\monitoreo_v2.py"

# Agente Edge: reporta los incidentes a la API
uv run python "Fase 2\Evidencias Proyecto\Yolo\modelamiento\monitoreo_api.py"
```

El agente Edge necesita `EDGE_API_TOKEN` con el **mismo valor** en su terminal
y en la de la API. Si no coinciden, la API responde `401`.

### Entrenar el detector

```powershell
uv run python "Fase 2\Evidencias Proyecto\Yolo\modelamiento\entrenamiento.py" --name train-11
```

### Evaluar el detector

```powershell
uv run python "Fase 2\Evidencias Proyecto\Yolo\modelamiento\evaluacion.py" `
  --model "Fase 2\Evidencias Proyecto\models\cascovision_yolo26s.pt" `
  --perfil 5clases --split test
```

---

## 8. Comandos de uv más usados

| Comando | Qué hace |
| --- | --- |
| `uv sync` | Crea el entorno e instala lo que dice `uv.lock` |
| `uv sync --group dev --group yolo` | Instala un grupo concreto |
| `uv lock` | Recalcula `uv.lock` tras cambiar `pyproject.toml` |
| `uv add <paquete>` | Agrega una dependencia y actualiza el lock |
| `uv remove <paquete>` | Quita una dependencia |
| `uv run <comando>` | Ejecuta un comando dentro del entorno del proyecto |
| `uv run python ...` | Ejecuta Python del entorno virtual |
| `uv pip list` | Lista lo instalado |
| `uv venv` | Crea el entorno virtual sin instalar nada |
| `uv python install 3.12` | Descarga la versión de Python que falte |

### Atajos que ahorran tiempo

`uv run` sincroniza el entorno antes de ejecutar, así que tras cambiar
`pyproject.toml` basta con ejecutar el comando: no hace falta un `uv sync`
previo.

`uv run --with <paquete>` ejecuta algo con un paquete adicional temporal, sin
tocar el `pyproject.toml`:

```powershell
uv run --with ruff ruff check .
```

---

## 9. Problemas frecuentes

### `uv` no se reconoce como comando

El instalador añadió uv al `PATH` del usuario, pero la terminal actual tiene
el `PATH` viejo. Cierra y reabre la terminal.

Si sigue sin funcionar, añade la carpeta manualmente. Suele estar en
`C:\Users\<usuario>\.local\bin`.

### `No solution found` al sincronizar

Suele ser una restricción de versión. Revisa qué pide cada paquete y
ajusta el `pyproject.toml`:

```powershell
uv lock --verbose
```

### PyTorch se instala sin CUDA

Significa que `torch` se resolvió desde PyPI en vez del índice de PyTorch.
Comprueba que el bloque `[tool.uv.sources]` siga en `pyproject.toml` y que
`uv lock` se haya ejecutado después de cualquier cambio.

Para comprobarlo:

```powershell
uv run python -c "import torch; print(torch.__version__, torch.cuda.is_available())"
```

Debe mostrar una versión con `+cu126` y `True`.

### `ModuleNotFoundError: lap`

Falta el grupo `yolo`:

```powershell
uv sync --group dev --group yolo
```

### El puerto 8000 está ocupado

```powershell
uv run python "Fase 2\Evidencias Proyecto\src\api\servidor.py" --port 8010
```

O libera el puerto:

```powershell
Get-NetTCPConnection -LocalPort 8000 | Select-Object OwningProcess
Stop-Process -Id <pid>
```

### La API responde 503 en `POST /incidents`

Falta `EDGE_API_TOKEN`. Comprueba la configuración:

```powershell
uv run python "Fase 2\Evidencias Proyecto\src\api\servidor.py" --check
```

### Empezar de cero

```powershell
Remove-Item -Recurse -Force .venv
uv sync --group dev --group yolo
```

---

## 10. Referencia rápida

```powershell
# Instalar uv (Windows)
winget install --id=astral-sh.uv -e

# Instalar dependencias
uv sync --group dev              # solo la API
uv sync --group dev --group yolo  # todo el proyecto

# Configurar
cd "Fase 2\Evidencias Proyecto"; copy .env.example .env

# Levantar la API
uv run python "Fase 2\Evidencias Proyecto\src\api\servidor.py" --reload

# Verificar
curl.exe http://localhost:8000/health
curl.exe http://localhost:8000/config

# Probar
uv run pytest
```
