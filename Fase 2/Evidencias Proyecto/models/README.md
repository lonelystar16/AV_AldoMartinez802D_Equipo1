# Modelos de CascoVision

| Archivo | Qué es | Tamaño |
| --- | --- | --- |
| `cascovision_yolo26s.pt` | Detector de EPP entrenado por el equipo: YOLO26s, corrida `train-10`, mejor época (64 de 100) | 19,4 MB |
| `face_detection_yunet_2023mar.onnx` | Detector de rostros YuNet de OpenCV Zoo, usado para difuminar la evidencia (RF-06) | 227 KB |

`.gitignore` excluye `*.pt` y `*.onnx` en todo el repositorio, salvo en esta
carpeta. Cada archivo debe pesar menos de 100 MB, el límite de GitHub. El
proceso de entrenamiento, el dataset y el análisis completo están en
[`../Yolo/README.md`](../Yolo/README.md); las curvas y matrices de confusión, en
`../Yolo/runs/detect/train-10/`.

## Clases del detector

| Id | Clase | Significado |
| --- | --- | --- |
| 0 | `helmet` | Casco sobre la cabeza |
| 1 | `no_helmet` | Persona **sin** casco (clase negativa) |
| 2 | `no_vest` | Persona **sin** chaleco (clase negativa) |
| 3 | `Person` | Persona completa; contiene a las demás |
| 4 | `vest` | Chaleco reflectante |

Las cinco clases son del producto. Las infracciones se **detectan de forma
positiva**: antes había que inferir que faltaba un casco por su ausencia.

## Métricas de validación

Criterio de aceptación (RNF-05 del SRS): **mAP@0,5 ≥ 0,90** y ***recall* ≥ 0,85**.

Evaluación sobre el split `test` (129 imágenes), con el detector de 5 clases:

| Versión | Fecha | Dataset (train / val / test) | mAP@0,5 | mAP@0,5:0,95 | Precisión | *Recall* | ¿Cumple? |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `train-10` (5 clases) | 21-10-2026 | 5.033 / 732 / 129 | 0,877 | 0,606 | 0,791 | 0,784 | ❌ |
| `train-9` (11 clases) | 08-10-2026 | 1.132 / 143 / 141 | 0,624 | 0,289 | 0,635 | 0,617 | ❌ |

El promedio de mAP@0,5 de `train-10` queda por debajo del 0,90 del RNF-05, pero
**no es una comparación justa con `train-9`**: el dataset anterior tenía 11
clases de las cuales 6 el producto no usaba (guantes, botas, gafas y sus
negativos), y esas hundían el promedio. El dataset nuevo tiene 5 clases, todas
del producto. La comparación válida son las reglas de negocio.

### Por clase (`train-10`)

| Clase | mAP@0,5 | mAP@0,5:0,95 | Precisión | *Recall* |
| --- | --- | --- | --- | --- |
| `vest` | 0,953 | 0,725 | 0,911 | 0,963 |
| `Person` | 0,909 | 0,667 | 0,899 | 0,826 |
| `no_helmet` | 0,844 | 0,544 | 0,859 | 0,802 |
| `no_vest` | 0,842 | 0,507 | 0,824 | 0,720 |
| `helmet` | 0,836 | 0,589 | 0,762 | 0,784 |

## Métricas de negocio

Son las que importan para el producto: el SRS no busca detectar cajas, sino
avisar cuando alguien no lleva EPP. Ambas reglas se miden sobre el mismo split
`test`, con la lógica de decisión de cada modelo.

| Regla | `train-9` (11 clases) | `train-10` (5 clases) | Mejora |
| --- | --- | --- | --- |
| ¿Lleva casco? | P 1,000 · R 0,643 · E 0,643 | **P 0,986 · R 0,947 · E 0,934** | *recall* **+0,304** |
| ¿Lleva chaleco? | P 0,951 · R 0,583 · E 0,566 | **P 1,000 · R 0,887 · E 0,887** | *recall* **+0,304** |

**El RNF-05 se cumple en las dos reglas de negocio:** el *recall* pasa de 0,643
a 0,947 en la regla de casco, y de 0,583 a 0,887 en la de chaleco. Ninguna de
las dos cumplía el umbral de 0,85 antes.

La mejora viene del *recall*, no de un canje de precisión por *recall*: la
precisión se mantiene en ~0,99. El modelo anterior era muy preciso pero se le
escapaban muchos casos, porque la infracción se infería de la **ausencia** de un
casco. Con `no_helmet` y `no_vest` como clases negativas explícitas, el
detector la declara directamente.

## Diagnóstico

La corrida se detuvo por *early stopping* en la época 94, con la mejor época en
la 64 (`patience` 30). La curva de validación se aplanó desde la época 45 en
torno a 0,845-0,854 de mAP@0,5, mientras las pérdidas de entrenamiento
siguieron bajando: la señal de sobreajuste de `train-9` se repite, aunque con
un techo mucho más alto (0,85 frente a 0,62).

El techo de ~0,88 de mAP@0,5 se explica por dos factores:

1. **El conjunto de validación tiene 732 imágenes** frente a 143 en `train-9`,
   pero la distribución de clases sigue siendo desigual: `vest` tiene 181
   instancias frente a 492 de `Person`.
2. **La clase `no_vest` es la más débil** (mAP@0,5 0,507 en mAP@0,5:0,95).
   Es la clase que reemplaza la antigua `none`, que se reinterpretaba por zona
   del cuerpo: la red tiene que aprender a distinguir "torso sin chaleco" de
   "torso con chaleco" solo por la ausencia de reflectante, que es la tarea
   que peor resuelve un detector de conjunto cerrado.

La línea de trabajo pendiente es atacar esa clase: más ejemplos de
`no_vest`, o una versión del dataset que marque explícitamente el torso.

> El modelo público `Hansung-Cho/yolov8-ppe-detection`, que usan el prototipo
> de Colab y la demo local de `_Base_CascoVision`, es solo una prueba de
> concepto de terceros. No cuenta como el modelo del proyecto.
