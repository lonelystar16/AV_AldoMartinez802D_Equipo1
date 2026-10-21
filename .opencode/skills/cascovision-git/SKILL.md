---
name: Flujo de trabajo con Git en CascoVision
description: Ramas, commits y que archivos se versionan en el repositorio de CascoVision - reglas de .gitignore, el dataset que no debe subirse, los checkpoints y el peso de las evidencias de fase. Usalo antes de hacer commit, antes de un pull o push, o cuando unsure de si un archivo debe versionarse.
---

# Flujo de trabajo con Git en CascoVision

## Ramas

El repositorio tiene dos ramas de trabajo: `main` y las ramas de desarrollo
por fase (`Yolo26`, `development_02.10.2026`). La práctica del equipo es:

- `main` es la línea de entrega: lo que se presenta.
- Las ramas de desarrollo agrupan el trabajo de una iteración del curso.
- Los cambios se integran a `main` mediante pull request.

Antes de empezar una línea de trabajo nueva, revisa qué ramas existen:

```bash
git branch -a
git log --oneline -10
```

## Qué se versiona y qué no

| Ruta | ¿Se versiona? | Por qué |
| --- | --- | --- |
| `Fase 2/Evidencias Proyecto/Yolo/dataset/` | **No** | ~440 MB de imágenes y etiquetas. Se regenera o se descarga |
| `Fase 2/Evidencias Proyecto/Yolo/runs/detect/*` | **No** | Corridas completas: checkpoints, curvas, CSV |
| `Fase 2/Evidencias Proyecto/models/*.pt` | **Sí** | El modelo entregado. Excepción explícita a la regla `*.pt` |
| `Fase 2/Evidencias Proyecto/models/*.onnx` | **Sí** | El detector de rostros YuNet |
| `Fase 2/Evidencias Proyecto/incidents/` | **No** | Evidencia generada en local |
| `Fase 2/Evidencias Proyecto/db/incidents.json` | **No** | Incidentes generados en local |
| `Fase 2/Evidencias Proyecto/db/cola_incidentes.jsonl` | **No** | Cola del agente Edge |
| `.env` | **No** | Secretos. Solo `.env.example` se versiona |
| `Fase 1/`, `Fase 2/Evidencias Grupales/`, `Fase 2/Evidencias Individuales/` | **Sí** | Entregables del curso |
| `.opencode/` | **Sí** | Skills y guía del proyecto |

## La trampa de las barras en `.gitignore`

En `.gitignore` la **barra invertida `\` es carácter de escape**, no separador
de directorios. Una regla escrita con `\` no aplica:

```
# MAL: la regla no aplica
Fase 2\Evidencias Proyecto\Yolo\dataset\train/

# BIEN
Fase 2/Evidencias Proyecto/Yolo/dataset/train/
```

Un `.gitignore` con reglas rotas es silencioso: el archivo aparece como
"untracked" sin avisar, y un `git add -A` sube 440 MB. **Verifica siempre
después de tocar `.gitignore`:**

```bash
git check-ignore -v --no-index "Fase 2/Evidencias Proyecto/Yolo/dataset/train/images/x.jpg"
```

Si no imprime nada y sale con código 1, la regla **no** aplica. Si imprime
`!ruta`, el archivo está explícitamente incluido (una excepción).

La fuente de verdad final es:

```bash
git status --porcelain --ignored=matching -- <ruta>
```

## Antes de hacer commit

```bash
git status --short
git diff
uv run pytest
```

Revisa que:

- No haya archivos grandes ni generados (`.cache`, `labels.cache`, checkpoints
  sueltos, `yolo26s.pt` en la raíz).
- No haya secretos. `.env` está ignorado, pero revisa los cambios por si
  quedó alguna clave en un archivo de código o documentación.
- Las pruebas pasan.

## Commits

Mensajes en **español**, en imperativo y en una línea, que describan el
cambio y no el proceso:

```
Agrega detector de EPP de 5 clases con dataset de Roboflow
Corrige .gitignore: rutas con barra invertida no aplicaban
Migra dependencias a uv como fuente unica
Actualiza metricas del modelo con la evaluacion sobre split test
```

## Antes de un push

```bash
git fetch origin
git log --oneline origin/main..HEAD
```

Si hay commits en `origin/main` que no tienes, integra antes de subir.

## Cosas que se olvidan

- **Los archivos `.cache`**: Ultralytics genera `labels.cache` junto a las
  etiquetas del dataset. Está bajo `Yolo/dataset/`, que ya está ignorado, pero
  si cambiaste la estructura del dataset, revisa que siga cubierto.
- **El modelo base `yolo26s.pt`** se descarga en la raíz del repositorio al
  entrenar. La regla `*.pt` lo cubre, pero verifícalo con `git status`.
- **`runs/detect/val*`**: Ultralytics crea las carpetas de validación en el
  directorio de trabajo. Si evalúas desde la raíz, aparecen en `runs/detect/`,
  fuera de la carpeta versionada del proyecto.
