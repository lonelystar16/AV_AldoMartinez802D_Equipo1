# CascoVision — modelo de detección de EPP con YOLOv26

> **Borrador de trabajo.** Documenta el subconjunto de EPP y el proceso de
> modelado del proyecto. Cuando el proyecto se complete, se fusionará con el
> `README.md` en un único documento de entrega.

---

## 1. Alcance del modelo

El modelo detecta elementos de seguridad en el torso de las personas dentro de
cuadro. El agente Edge opera sobre el subconjunto de **casco** y **chaleco
reflectante**: son los dos elementos asociados a la baliza de alerta. El resto de
implementos que el modelo reconoce se detecta, pero no genera incidentes.

| Elemento | Clase del modelo | Resultado |
| --- | --- | --- |
| Casco | `helmet` | cumple |
| Sin casco | `no_helmet` | `missing_helmet` |
| Chaleco reflectante | `vest` | cumple |
| Sin chaleco | `none` en torso | `missing_reflective_vest` |

El modelo trabaja con 11 clases: `helmet`, `gloves`, `vest`, `boots`, `goggles`,
`none`, `Person`, `no_helmet`, `no_goggle`, `no_gloves`, `no_boots`. Las que
interesan al producto son `Person`, `helmet`, `no_helmet` y `vest`.

### La clase `none` y su reinterpretación por zona

El modelo no incluye una clase `no_vest`. La clase `none` (id 5) es una caja
genérica de "sin implemento en esta zona", por lo que el motor la reinterpreta
según la región del cuerpo donde aparece.

Las proporciones se midieron sobre las 1426 imágenes etiquetadas del dataset
(train + val + test), emparejando cada objeto con la persona que lo contiene:

| Clase | Altura relativa a la persona | Centro vertical |
| --- | --- | --- |
| `helmet` | 0,14 | 0,11 |
| `no_helmet` | 0,18 | 0,12 |
| `vest` | 0,42 | 0,41 |
| **`none`** | **0,45** | **0,52** |

`none` tiene la proporción de un chaleco y se ubica en el torso, no en la cabeza.
De las 704 personas con una caja `none`, 564 carecen de chaleco. La regla
aplicada es:

- centro vertical **≥ 0,33** de la caja de la persona → falta chaleco
- centro vertical **< 0,33** y altura relativa **< 0,25** → falta casco
- caja grande en la zona de la cabeza → accesorio mal etiquetado, se descarta

El corte 0,33 se fijó de forma empírica: con él, el 95,7% de las cajas reales de
casco queda por debajo y el 91,5% de las de chaleco por encima.

---

## 2. Entrenamiento

| Parámetro | Valor |
| --- | --- |
| Modelo base | `yolo26s.pt` (YOLOv26-small, 10,0 M parámetros) |
| Corrida | `train-9` |
| Épocas | 100 |
| `imgsz` | 640 |
| `batch` | 16 |
| Optimizador | `auto` (AdamW) |
| Tiempo total | 13,78 h (49.600,9 s) |
| Pesos | [`models/cascovision_yolo26s.pt`](../models/) (19,4 MB, mejor época) |

### Dataset

| División | Imágenes |
| --- | --- |
| train | 1132 |
| val | 143 |
| test | 141 |

Distribución de clases en `val`: `Person` 239, `helmet` 201, `vest` 171, `boots`
151, `gloves` 136, `none` 81, `no_gloves` 56, `goggles` 47, `no_helmet` 45,
`no_goggle` 41, `no_boots` 4.

> `construccion-implementos.yaml` declara `path:` como ruta relativa a la raíz
> del repositorio, de modo que el dataset no quede atado a una máquina. Como
> Ultralytics la resuelve contra el directorio de trabajo, el entrenamiento
> debe lanzarse desde la raíz del repositorio.

### Curva de entrenamiento

| Epoch | mAP@0,5 | mAP@0,5:0,95 | Precisión | Recall |
| --- | --- | --- | --- | --- |
| 1 | 0,420 | 0,190 | 0,787 | 0,359 |
| **84 (mejor)** | **0,624** | 0,290 | 0,635 | 0,617 |
| 100 (última) | 0,592 | 0,278 | 0,615 | 0,607 |

---

## 3. Desempeño

### 3.1 Por clase

Evaluación sobre las 143 imágenes de validación, con `model.val()` y umbral de
confianza 0,001:

| clase | n (val) | mAP@0,5 | mAP@0,5:0,95 | Precisión | Recall | Uso |
| --- | --- | --- | --- | --- | --- | --- |
| `Person` | 239 | **0,936** | 0,534 | 0,869 | 0,918 | sí |
| `vest` | 171 | **0,889** | 0,551 | 0,838 | 0,848 | sí |
| `helmet` | 201 | 0,848 | 0,445 | 0,845 | 0,851 | sí |
| `boots` | 151 | 0,813 | 0,455 | 0,755 | 0,788 | no |
| `goggles` | 47 | 0,808 | 0,346 | 0,719 | 0,787 | no |
| `gloves` | 136 | 0,805 | 0,379 | 0,806 | 0,728 | no |
| `none` | 81 | 0,622 | 0,217 | 0,585 | 0,580 | reinterpetada |
| `no_helmet` | 45 | 0,493 | 0,147 | 0,592 | 0,511 | sí |
| `no_goggle` | 41 | 0,220 | 0,065 | 0,358 | 0,195 | no |
| `no_gloves` | 56 | 0,206 | 0,048 | 0,340 | 0,286 | no |
| `no_boots` | 4 | 0,078 | 0,016 | 0,000 | 0,000 | no |


### 3.2 Por decisión de negocio

La métrica que importa es si el sistema acierta al declarar una infracción. Se
validaron las detecciones contra las 656 etiquetas de `val`, emparejando cada
persona detectada con su persona real y aplicando la lógica de zonas:

| regla | precisión | recall | exactitud |
| --- | --- | --- | --- |
| ¿lleva casco? | 0,985 | **0,757** | 0,773 |
| ¿lleva chaleco? | 0,890 | 0,890 | 0,869 |

La regla de chaleco cumple el umbral de recall. La de casco queda por debajo:
el sistema tiene alta precisión al declarar cumplimiento, pero pierde alrededor
de un cuarto de los casos en que la persona sí lleva casco.

El factor limitante es la detección, no la asociación de cajas. La precisión de la regla de casco es 0,985, es decir que cuando el sistema declara que falta casco, casi siempre acierta. Lo que se pierde ocurre antes: la caja `helmet` nose detecta o no se asocia a la persona correcta. `helmet` tiene recall 0,851 a nivel de clase, y la decisión de negocio se queda en 0,757.

### 3.3 Estado frente al RNF-05

El criterio de aceptación del SRS exige **mAP@0,5 ≥ 0,90** y **recall ≥ 0,85**.

| Métrica | Obtenido | Requerido | Estado |
| --- | --- | --- | --- |
| mAP@0,5 (promedio de 11 clases) | 0,611 | ≥ 0,90 | por debajo |
| mAP@0,5 (clases del producto) | 0,792 | ≥ 0,90 | por debajo |
| mAP@0,5 (3 clases decisivas) | 0,891 | ≥ 0,90 | por debajo |
| Recall (regla de casco) | 0,757 | ≥ 0,85 | por debajo |
| Recall (regla de chaleco) | 0,890 | ≥ 0,85 | **cumple** |

La versión actual es la línea base del modelado.

### 3.4 Diagnóstico: sobreajuste

Las pérdidas de entrenamiento bajan durante el entrenamiento, pero las de
validación se mantienen planas:

| Pérdida | Epoch 1 | Epoch 100 | Variación |
| --- | --- | --- | --- |
| `train/box_loss` | 1,930 | 1,077 | **−44%** |
| `val/box_loss` | 1,898 | 1,891 | **−0,4%** |
| `train/cls_loss` | 3,916 | 0,464 | **−88%** |
| `val/cls_loss` | 3,345 | 1,311 | −61% |

El modelo aprende el conjunto de entrenamiento sin mejorar en validación. El
mejor epoch es el 84 y a partir de ahí las métricas caen; con `patience` en 100
el entrenamiento continuó hasta el final sin detenerse.

Factores que explican el comportamiento:

1. **Tamaño del dataset.** 1132 imágenes de entrenamiento es limitado para
   detección de objetos pequeños en cuadro.
2. **Desbalance entre clases.** `no_boots` tiene 4 instancias en validación,  `goggles` y `no_goggle` suman 88.
3. **Detección de ausencia.** La regla de casco se decide por la **ausencia** de una caja `helmet`, y la ausencia de un objeto es la tarea que peor resuelve un detector de conjunto cerrado.


## 4. Componentes del sistema

| Componente | Ruta | Función |
| --- | --- | --- |
| Motor de análisis | `Yolo/testing y modelamiento/motor_cascovision.py` | Detección, zonas, difuminado y registro de incidentes |
| Monitoreo local | `Yolo/testing y modelamiento/monitoreo_v2.py` | Ejecuta el motor contra la cámara |
| Agente Edge | `Yolo/testing y modelamiento/monitoreo_api.py` | Reporta los incidentes a la API |
| API REST | `src/api/app/main.py` | `/health` y rutas de incidentes |
| Persistencia | `src/api/app/almacen.py` | Almacenamiento en JSON, encapsulado para migrar a PostgreSQL |

### Reglas de decisión

Para cada persona se asocian los elementos de seguridad detectados dentro de su caja, se resuelven los conflictos por confianza (el casco real gana sobre `no_helmet` cuando ambos aparecen) y se evalúan dos reglas:
- **falta casco:** no se detectó ni `helmet` ni `no_helmet`
- **falta chaleco:** no se detectó `vest`, o se detectó `none` en el torso

Una infracción se confirma tras aparecer en 2 de los últimos 5 frames, lo que evita alertas por ruido de un solo frame.

### Evidencia

Cada infracción confirmada guarda el frame, ya con los rostros difuminados, en `incidents/AAAA/MM/DD/`. El incidente se registra en la API con la referencia a ese archivo en `evidence_path`.

---

## 5. Dependencias

Entorno validado: **Python 3.12**. Ver
[`requirements-yolo.txt`](../requirements-yolo.txt).

```bash
# 1) PyTorch con CUDA. En Windows el build con GPU no está en PyPI: el de PyPI
#    es CPU-only y la tarjeta quedaría sin usar.
pip install torch==2.14.1+cu126 torchvision==0.29.1+cu126 --index-url https://download.pytorch.org/whl/cu126

# 2) Ultralytics 8.4 o superior: best.pt se entrenó con yolo26s.pt
pip install ultralytics==8.4.177

# 3) OpenCV con techo 5.0: la 5.x eliminó cv2.CascadeClassifier
pip install "opencv-python>=4.6.0,<5.0"

# 4) NumPy nunca por debajo de 2.4
pip install "numpy>=1.24"

# 5) Métrica de tracking
pip install "lap>=0.5.12"
```

### Notas del entorno

- **PyTorch en Windows no publica build con CUDA en PyPI.** Sin el `--index-url`,
  el wheel de PyPI es CPU-only (~118 MB) y la GPU no se usa.
- **El difuminado usa YuNet** (`cv2.FaceDetectorYN`), una red neuronal, no una
  cascada Haar: OpenCV 5.0 eliminó la API de cascadas. El modelo
  `face_detection_yunet_2023mar.onnx` (227 KB) se versiona en
  [`models/`](../models/). Detecta rostros frontales
  y de perfil, y entrega las coordenadas de ambos ojos.
- **El seguimiento usa ByteTrack.** El checkpoint arrastra `tracktrack.yaml` en sus
  argumentos y ese tracker devuelve identificadores nulos en Ultralytics 8.4, sin
  los cuales no hay seguimiento ni suavizado.
- **NumPy por debajo de 2.4** no tiene ruedas para Python 3.15 y pip intenta
  compilarlo, lo que falla sin Visual Studio Build Tools.

---

## 6. Ejecución

### Monitoreo y API

Desde la carpeta `Fase 2/Evidencias Proyecto`:

```bash
cd "Fase 2/Evidencias Proyecto"

# Monitoreo local, sin API
python "Yolo/testing y modelamiento/monitoreo_v2.py"

# Agente Edge: reporta los incidentes a la API
python -m uvicorn app.main:app --app-dir src/api --reload
python "Yolo/testing y modelamiento/monitoreo_api.py"
```

Presionar `q` en la ventana de video para finalizar.

### Entrenamiento

El entrenamiento se lanza **desde la raíz del repositorio**, porque el dataset
usa una ruta relativa a esa carpeta. El modelo base `yolo26s.pt` no se versiona:
Ultralytics lo descarga automáticamente la primera vez que se usa.

```bash
cd <raíz-del-repositorio>
python "Fase 2/Evidencias Proyecto/Yolo/testing y modelamiento/entrenamiento.py"
```

### Anonimización de la evidencia

La banda difuminada se ancla en el punto medio de los dos ojos que reporta YuNet
y se recorta a la caja de la cara, de modo que nunca queda más ancha ni más alta
que el rostro. La detección de rostros se mide sobre la misma cámara y el mismo
dataset: YuNet acierta en el 100% de las personas frente al 17% de una cascada
Haar frontal, con 16,9 ms frente a 58,9 ms de latencia.
