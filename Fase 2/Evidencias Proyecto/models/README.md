# Modelos de CascoVision

| Archivo | Qué es | Tamaño |
| --- | --- | --- |
| `cascovision_yolo26s.pt` | Detector de EPP entrenado por el equipo: YOLO26s, corrida `train-9`, mejor época (84 de 100) | 19,4 MB |
| `face_detection_yunet_2023mar.onnx` | Detector de rostros YuNet de OpenCV Zoo, usado para difuminar la evidencia (RF-06) | 227 KB |

`.gitignore` excluye `*.pt` y `*.onnx` en todo el repositorio, salvo en esta
carpeta. Cada archivo debe pesar menos de 100 MB, el límite de GitHub. El
proceso de entrenamiento, el dataset y el análisis completo están en
[`../Yolo/README.md`](../Yolo/README.md); las curvas y matrices de confusión, en
`../Yolo/runs/detect/train-9/`.

## Métricas de validación

Criterio de aceptación (RNF-05 del SRS): **mAP@0,5 ≥ 0,90** y ***recall* ≥ 0,85**
en el conjunto de validación (143 imágenes).

| Versión | Fecha | Dataset (train / val / test) | mAP@0,5 | mAP@0,5:0,95 | Precisión | *Recall* | ¿Cumple? |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `train-9` (11 clases) | 08-10-2026 | 1.132 / 143 / 141 | 0,624 | 0,289 | 0,635 | 0,617 | ❌ |

El promedio de 11 clases incluye guantes, botas y lentes, que el producto no
usa. Para las decisiones de negocio:

| Regla | Precisión | *Recall* | ¿Cumple el *recall* ≥ 0,85? |
| --- | --- | --- | --- |
| ¿Lleva chaleco? | 0,890 | 0,890 | ✅ |
| ¿Lleva casco? | 0,985 | 0,757 | ❌ |

Es la línea base del modelado. Hay sobreajuste: la pérdida de validación no
baja, aunque la de entrenamiento sí. El diagnóstico (tamaño del dataset,
desbalance de clases y detección por ausencia) está en el README del modelo.

> El modelo público `Hansung-Cho/yolov8-ppe-detection`, que usan el prototipo
> de Colab y la demo local de `_Base_CascoVision`, es solo una prueba de
> concepto de terceros. No cuenta como el modelo del proyecto.
