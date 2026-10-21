---
name: Modelo de detección de EPP
description: Entrenar, evaluar y mantener el detector de EPP (YOLO26) de CascoVision. Úsalo al trabajar en Yolo/dataset, Yolo/models, Yolo/runs, el motor de detección, las métricas de mAP/recall, el RNF-05 del SRS o el mapeo de clases del detector.
---

# Modelo de detección de EPP

El detector es un YOLO26-small de **5 clases**. Toda la lógica de negocio del
producto (¿lleva casco? ¿lleva chaleco?) se apoya en este vocabulario, así que
cualquier cambio en el detector tiene que propagationarse a `motor_cascovision.py`,
a `evaluacion.py` y a la documentación.

## Las 5 clases y su semántica

| Id | Nombre | Qué es | Dónde se ubica |
| --- | --- | --- | --- |
| 0 | `helmet` | Casco sobre la cabeza | Cabeza (relH ≈ 0,18) |
| 1 | `no_helmet` | Persona **sin** casco (clase negativa) | Cabeza (relH ≈ 0,20) |
| 2 | `no_vest` | Persona **sin** chaleco (clase negativa) | Torso (relH ≈ 0,44) |
| 3 | `Person` | Persona completa | Contiene a las demás |
| 4 | `vest` | Chaleco reflectante | Torso (relH ≈ 0,48) |

Dato clave: la clase `Person` **contiene** a las demás. El `Person` de una
persona se empareja con sus cajas de EPP por solapamiento (≥ 0,35 del área del
EPP dentro de la caja de la persona).

Las clases negativas son la diferencia con el modelo anterior de 11 clases: ahí
la infracción se **infería** de la ausencia de un casco; aquí el detector la
**declara**. Eso ataca de frente el factor limitante que el SRS documentaba
(recall de la regla de casco de 0,757).

## Dataset

- Ubicación: `Fase 2/Evidencias Proyecto/Yolo/dataset/`
- **No se versiona** (~440 MB). Configuración en `construccion-implementos.yaml`.
- Splits disjuntos por nombre de archivo original de Roboflow (sin el sufijo
  `.rf.<hash>`), para que una imagen con distintas augmentations no caiga en
  dos splits.

| Split | Imágenes | c0 helmet | c1 no_helmet | c2 no_vest | c3 Person | c4 vest |
| --- | --- | --- | --- | --- | --- | --- |
| train | 5.033 | 5.994 | 4.871 | 5.669 | 9.234 | 2.916 |
| valid | 732 | 835 | 618 | 722 | 1.121 | 296 |
| test | 129 | 147 | 114 | 143 | 205 | 54 |

El YAML **no declara `path:`**: Ultralytics resuelve las rutas contra la carpeta
del propio YAML, y así el entrenamiento funciona desde cualquier directorio de
trabajo. Si declaras `path:`, queda atado al directorio desde el que se lanza.

## Entrenar

```bash
uv run python "Fase 2/Evidencias Proyecto/Yolo/testing y modelamiento/entrenamiento.py" \
    --name train-10 --epochs 100 --batch 16 --patience 30 --device 0 --workers 4
```

Parámetros por defecto y por qué:

| Parámetro | Valor | Motivo |
| --- | --- | --- |
| `--model` | `yolo26s.pt` | Base COCO. La clase `Person` hereda sus pesos por el remapeo por nombre de Ultralytics; las otras 4 se inicializan |
| `--epochs` | 100 | Igual que train-9, para comparabilidad |
| `--imgsz` | 640 | Igual que train-9 |
| `--batch` | 16 | Cabe en 6 GB. Si hay OOM, baja a 8 |
| `--patience` | 30 | train-9 usó 100 y sobreajustó (mejor época 84, val loss plana) |
| `--workers` | 4 | En Windows, 8+ satura la RAM con 5.000 imágenes |
| `cos_lr` | `True` (fijo) | train-9 lo dejó en `false` y las pérdidas de validación se estancaron |
| `close_mosaic` | 10 (fijo) | Igual que train-9 |

La corrida se guarda en `Fase 2/Evidencias Proyecto/Yolo/runs/detect/<nombre>/`.
Se ignora por `.gitignore`; solo se versiona la corrida que se documente.

Para continuar una corrida interrumpida: `--resume` (recupera el estado del
optimizador y el contador de épocas del checkpoint).

### Guardas antes de lanzar

```bash
uv run python -c "import torch; print(torch.__version__, torch.cuda.is_available())"
```

Si `cuda.is_available()` es `False`, **detente**: entrenar en CPU no es viable.
Ocurre si se sincronizó el entorno sin el grupo `yolo` o sin el índice de
PyTorch con las ruedas CUDA.

## Evaluar

```bash
uv run python "Fase 2/Evidencias Proyecto/Yolo/testing y modelamiento/evaluacion.py" \
    --model "Fase 2/Evidencias Proyecto/Yolo/runs/detect/train-10/weights/best.pt" \
    --perfil 5clases --split test --json informe.json
```

El script reporta dos cosas distintas:

1. **Métricas por clase**: mAP@0,5, mAP@0,5:0,95, precisión y recall. Son las
   que usa el criterio RNF-05 del SRS (mAP@0,5 ≥ 0,90 y recall ≥ 0,85).
2. **Métricas de negocio**: precisión, recall y exactitud de las reglas
   ¿lleva casco? y ¿lleva chaleco?. **Son las que importan para el producto.**

Ojo al comparar detectores con vocabularios distintos: el modelo de 11 clases
anterior no se puede evaluar clase a clase contra este dataset (sus ids no
coinciden). Para eso está el flag `--perfil`, que declara el vocabulario de cada
modelo y aplica **su propia** regla de decisión sobre el mismo ground truth.
Perfiles disponibles: `5clases` y `11clases`.

Línea base medida con el modelo de 11 clases sobre este mismo split test:

| Regla | Precisión | Recall | Exactitud |
| --- | --- | --- | --- |
| ¿Lleva casco? | 1,000 | 0,643 | 0,643 |
| ¿Lleva chaleco? | 0,951 | 0,583 | 0,566 |

## Reglas de negocio en el motor

`Yolo/testing y modelamiento/motor_cascovision.py` decide así:

- `helmet` detectada → cumple. `no_helmet` detectada → **falta casco**.
- `vest` detectada → cumple. `no_vest` detectada → **falta chaleco**.
- Ninguna de las dos → estado indeterminado (`falta_casco` / `falta_chaleco`).

El caso indeterminado se resuelve con `POLITICA_SIN_DATOS`:

- `"infraccion"` (por defecto): también se notifica. Es la opción
  conservadora: en una faena no avisar puede costar un accidente.
- `"cumple"`: solo se notifica la infracción confirmada. Menos falsos
  positivos, a costa de no avisar en los casos indeterminados.

Es un cambio de decisión de negocio: si lo cambias, actualiza el SRS y la
documentación de métricas.

## Errores que ya se cometieron (no repetirlos)

- **YAML con `nc` equivocado**: Ultralytics no lanza error, marca la imagen como
  corrupta y la **descarta en silencio**. Con `nc: 4` sobre este dataset se
  perdía el 30 % de las imágenes de train. Verifícalo con
  `ultralytics.data.utils.verify_image_label`.
- **Nombres con sufijo de Roboflow**: `imagen.with_suffix(".txt")` borra el
  `.rf.<hash>` y produce un nombre inexistente. Usa
  `imagen.stem + ".txt"`.
- **Coordenadas normalizadas contra píxeles**: las etiquetas de YOLO vienen en
  0-1; las detecciones del modelo, en píxeles. Convierte antes de comparar.
- **Emparejamiento codicioso**: emparejar por mejor IoU detección por detección
  deja detecciones correctas sin emparejar. Haz la asignación global.
- **`opencv-python` 5.x**: eliminó `cv2.CascadeClassifier`, que usan los scripts
  de prueba. La versión válida es `>=4.11,<5.0`.
- **Falta `lap`**: `ultralytics/trackers/utils/matching.py` lo importa de
  forma directa para ByteTrack. Está en el grupo `yolo`.

## Referencias

- `references/metricas.md` — protocolo de evaluación y cómo leer las cifras.
- `references/clases.md` — el mapeo de clases y cómo llegó a determinarse.
