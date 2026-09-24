# Modelo de detección de EPP

Aquí se versiona el modelo YOLOv8 entrenado por el equipo (tarea 4.1 de la Gantt, semanas 9 a 11), en dos formatos:

| Archivo | Uso |
| --- | --- |
| `cascovision_yolov8.pt` | Pesos de Ultralytics, para reentrenar o evaluar |
| `cascovision_yolov8.onnx` | Modelo exportado que usa el agente Edge para la inferencia local |

`.gitignore` excluye `*.pt` y `*.onnx` en todo el repositorio, salvo en esta carpeta. Cada archivo debe pesar menos de 100 MB, que es el límite de GitHub.

## Métricas de validación

Criterio de aceptación (RNF-05 del SRS): **mAP@0,5 ≥ 0,90** y ***recall* ≥ 0,85** en el conjunto de validación.

| Versión | Fecha | Dataset (imágenes train / val) | mAP@0,5 | mAP@0,5:0,95 | Precisión | *Recall* | ¿Cumple? |
| --- | --- | --- | --- | --- | --- | --- | --- |
| *pendiente* | | | | | | | |

Junto a cada versión se guardan la matriz de confusión y las curvas (`results.png`, `confusion_matrix.png`) que genera Ultralytics al validar.

> El modelo público `Hansung-Cho/yolov8-ppe-detection`, que usan el prototipo de Colab y la demo local de `_Base_CascoVision`, es solo una prueba de concepto de terceros. No cuenta como el modelo del proyecto ni acredita el RNF-05.
