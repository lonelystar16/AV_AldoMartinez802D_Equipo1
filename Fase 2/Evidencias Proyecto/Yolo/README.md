# CascoVision — modelo de detección de EPP con YOLO26

> **Borrador de trabajo.** Documenta el subconjunto de EPP y el proceso de
> modelado del proyecto. Cuando el proyecto se complete, se fusionará con el
> `README.md` en un único documento de entrega.

---

## 0. Estado actual

> 🚧 **Detector de 5 clases en producción.** La corrida `train-10` cerró por
> *early stopping* en la época 94, con la mejor época en la 64. El modelo
> entregado es [`models/cascovision_yolo26s.pt`](../models/). La sección 3.5
> recoge sus métricas y la comparación con la línea base `train-9`.

---

## 1. Alcance del modelo

El detector actual opera sobre un esquema de **5 clases**, todas del producto:

| Id | Clase | Qué es | Resultado |
| --- | --- | --- | --- |
| 0 | `helmet` | Casco sobre la cabeza | cumple |
| 1 | `no_helmet` | Persona **sin** casco | `missing_helmet` |
| 2 | `no_vest` | Persona **sin** chaleco | `missing_reflective_vest` |
| 3 | `Person` | Persona completa | ancla de la asociación |
| 4 | `vest` | Chaleco reflectante | cumple |

La diferencia con el modelo anterior (train-9, 11 clases) es que **las
infracciones se detectan de forma positiva**: antes había que inferir que
faltaba un casco por su ausencia, y la clase `none` genérica se reinterpretaba
por zona del cuerpo. Ahora `no_helmet` y `no_vest` son clases explícitas, y la
heurística de reinterpretación desapareció.

El mapeo de clases se determinó combinando contención de cajas, geometría
relativa a la persona, inspección visual de recortes y exclusividad mutua.
Está documentado en [`../docs/MODELO.md`](../docs/MODELO.md).

### El modelo anterior (train-9)

Para referencia histórica, el modelo de 11 clases tenía: `helmet`, `gloves`,
`vest`, `boots`, `goggles`, `none`, `Person`, `no_helmet`, `no_goggle`,
`no_gloves`, `no_boots`. Las seis clases que el producto no usa hundían el
promedio de mAP@0,5 y no permitían una comparación justa de clases.

### La clase `none` y su reinterpretación por zona (modelo de 11 clases)

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
| Modelo base | `yolo26s.pt` (YOLO26-small, 10,0 M parámetros) |
| Corrida | `train-9` |
| Épocas | 100 |
| `imgsz` | 640 |
| `batch` | 16 |
| Optimizador | `auto` (AdamW) |
| Tiempo total | 13,78 h (49.600,9 s) |
| Pesos | [`models/cascovision_yolo26s.pt`](../models/) (19,4 MB, mejor época) |

### Dataset

Hay **dos datasets** distintos en el historial del proyecto.

#### Dataset actual (5 clases) — el que se usa para `train-10`

Export de **Roboflow** del conjunto Construction-PPE, con esquema de 5 clases
propio. **No se versiona en Git** por su tamaño (~440 MB). La configuración
está en `Yolo/dataset/construccion-implementos.yaml` y las imágenes y
etiquetas en `Yolo/dataset/{train,valid,test}/{images,labels}/`.

| División | Imágenes |
| --- | --- |
| train | 5.033 |
| valid | 732 |
| test | 129 |

Distribución de instancias:

| División | `helmet` | `no_helmet` | `no_vest` | `Person` | `vest` |
| --- | --- | --- | --- | --- | --- |
| train | 5.994 | 4.871 | 5.669 | 9.234 | 2.916 |
| valid | 835 | 618 | 722 | 1.121 | 296 |
| test | 147 | 114 | 143 | 205 | 54 |

Los tres splits son **disjuntos por nombre de archivo original** de Roboflow
(sin el sufijo `.rf.<hash>`): una misma imagen con distintas augmentations no
cae en dos splits, para que las métricas no se inflen.

> `construccion-implementos.yaml` **no declara `path:`**. Ultralytics resuelve
> entonces las rutas contra la carpeta del propio YAML, así que el
> entrenamiento funciona desde cualquier directorio de trabajo. Declarar
> `path:` ataría el dataset al directorio desde el que se lanza la corrida.

> ⚠️ El `nc` del YAML debe coincidir con el número real de clases del
> dataset. Si no coincide, Ultralytics **no lanza error**: marca la imagen como
> corrupta y la descarta en silencio. Con `nc: 4` sobre este dataset se perdía
> el 30 % de las imágenes de train.

#### Dataset anterior (11 clases) — el de `train-9`

**Construction-PPE de Ultralytics**
(<https://docs.ultralytics.com/datasets/detect/construction-ppe>), con 11
clases. Sus métricas son las de la sección 3.

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

### 3.5 Detector de 5 clases (`train-10`)

Corrida cerrada por *early stopping* en la época 94, con la mejor época en la
**64** (`patience` 30). El modelo entregado es
[`models/cascovision_yolo26s.pt`](../models/), 19,4 MB.

#### Métricas por clase

Evaluación sobre el split `test` (129 imágenes):

| Clase | mAP@0,5 | mAP@0,5:0,95 | Precisión | *Recall* |
| --- | --- | --- | --- | --- |
| `vest` | 0,953 | 0,725 | 0,911 | 0,963 |
| `Person` | 0,909 | 0,667 | 0,899 | 0,826 |
| `no_helmet` | 0,844 | 0,544 | 0,859 | 0,802 |
| `no_vest` | 0,842 | 0,507 | 0,824 | 0,720 |
| `helmet` | 0,836 | 0,589 | 0,762 | 0,784 |
| **promedio** | **0,877** | **0,606** | 0,791 | 0,784 |

#### Por decisión de negocio

La métrica que importa es si el sistema acierta al declarar una infracción. Para
comparar conjustice, el modelo de 11 clases se evaluó sobre el **mismo** split
`test`, aplicando su propia lógica de decisión (inferir la ausencia de casco)
sobre el mismo ground truth:

| regla | `train-9` (11 clases) | `train-10` (5 clases) | Mejora |
| --- | --- | --- | --- |
| ¿lleva casco? | P 1,000 · R 0,643 · E 0,643 | **P 0,986 · R 0,947 · E 0,934** | *recall* **+0,304** |
| ¿lleva chaleco? | P 0,951 · R 0,583 · E 0,566 | **P 1,000 · R 0,887 · E 0,887** | *recall* **+0,304** |

**El RNF-05 se cumple en las dos reglas de negocio.** El *recall* pasa de 0,643 a
0,947 en la regla de casco, y de 0,583 a 0,887 en la de chaleco. Ninguna de las
dos cumplía el umbral de 0,85 antes.

La mejora viene del *recall*, no de un canje de precisión por *recall*: la
precisión se mantiene en ~0,99. El modelo anterior era muy preciso —casi nunca
acusaba a alguien que sí llevaba casco— pero se le escapaban muchos casos,
porque la infracción se infería de la **ausencia** de un casco. Con `no_helmet`
y `no_vest` como clases negativas explícitas, el detector la declara
directamente.

#### Estado frente al RNF-05

| Métrica | Obtenido | Requerido | Estado |
| --- | --- | --- | --- |
| *Recall* (regla de casco) | 0,947 | ≥ 0,85 | **cumple** |
| *Recall* (regla de chaleco) | 0,887 | ≥ 0,85 | **cumple** |
| mAP@0,5 (promedio de 5 clases) | 0,877 | ≥ 0,90 | por debajo |

> ⚠️ **El mAP@0,5 promedio no es comparable con el de `train-9`.** El dataset
> anterior tenía 11 clases de las cuales 6 el producto no usaba (guantes, botas,
> gafas y sus negativos), y esas hundían el promedio a 0,611. El dataset nuevo
> tiene 5 clases, todas del producto, así que el promedio sube por
> construcción y no por mejor modelo. La comparación honesta son las **reglas
> de negocio** y las **métricas por clase**, no el promedio.

#### Configuración de la corrida

| Parámetro | Valor |
| --- | --- |
| Modelo base | `yolo26s.pt` (COCO, 80 clases) |
| Datos | `dataset/construccion-implementos.yaml` (5 clases) |
| Épocas | 100 (`patience` 30) → **parada en la 94** |
| Mejor época | **64** |
| `imgsz` | 640 |
| `batch` | 16 |
| Optimizador | `auto` (AdamW) |
| `cos_lr` | `True` |
| `close_mosaic` | 10 |
| `workers` | 4 |
| Semilla | 0 |
| Tiempo total | ~3,2 h |

Se parte de la **base limpia** y no del checkpoint de 11 clases: el vocabulario
de clases es incompatible, así que el mapeo por nombre de Ultralytics no
trasladaría pesos útiles de las clases negativas. La clase `Person` sí hereda
sus pesos de COCO, porque el nombre coincide.

#### Protocolo de evaluación

```bash
uv run python "Fase 2/Evidencias Proyecto/Yolo/modelamiento/evaluacion.py" \
    --model "Fase 2/Evidencias Proyecto/Yolo/runs/detect/train-10/weights/best.pt" \
    --perfil 5clases --split test --json informe.json
```

El protocolo completo y cómo leer las cifras está en
[`../docs/MODELO.md`](../docs/MODELO.md).

#### Diagnóstico y línea de trabajo pendiente

La curva de validación se aplanó desde la época 45 en torno a 0,845-0,854 de
mAP@0,5, mientras las pérdidas de entrenamiento siguieron bajando: la señal de
sobreajuste de `train-9` se repite, aunque con un techo mucho más alto (0,88
frente a 0,62).

El techo de ~0,88 de mAP@0,5 se explica por dos factores:

1. **Desequilibrio de clases**: `vest` tiene 181 instancias en validación frente
   a 492 de `Person`.
2. **La clase `no_vest` es la más débil** (0,507 de mAP@0,5:0,95). Es la clase
   que reemplaza la antigua `none`, que se reinterpretaba por zona del cuerpo:
   la red tiene que aprender a distinguir "torso sin chaleco" de "torso con
   chaleco" solo por la ausencia de reflectante, que es la tarea que peor
   resuelve un detector de conjunto cerrado.

La línea de trabajo pendiente es atacar esa clase: más ejemplos de `no_vest`, o
una versión del dataset que marque explícitamente el torso.

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
| Motor de análisis | `Yolo/modelamiento/motor_cascovision.py` | Detección, zonas, difuminado y registro de incidentes |
| Monitoreo local | `Yolo/modelamiento/monitoreo_v2.py` | Ejecuta el motor contra la cámara |
| Agente Edge | `Yolo/modelamiento/monitoreo_api.py` | Reporta los incidentes a la API |
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

Entorno validado: **Python 3.12**. El proyecto usa **uv** como fuente única de
dependencias, con el grupo `yolo` para el motor de detección:

```bash
uv sync --group dev --group yolo
```

Ese grupo instala, en este orden: PyTorch con CUDA 12.6 desde el índice de
PyTorch, Ultralytics 8.4 (necesario para cargar un checkpoint YOLO26), OpenCV
anterior a 5.0, NumPy y `lap` (el seguimiento de ByteTrack). En un equipo sin GPU
NVIDIA, hay que quitar el índice de PyTorch del `pyproject.toml` para instalar
la versión de PyTorch para CPU.

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
- **Python 3.12.** Es la versión validada. Con versiones más nuevas de Python,
  pip puede no encontrar ruedas precompiladas de NumPy o PyTorch e intentar
  compilarlas, lo que falla sin Visual Studio Build Tools.

---

## 6. Ejecución

### Monitoreo y API

Desde la raíz del repositorio:

```bash
# Monitoreo local, sin API
uv run python "Fase 2/Evidencias Proyecto/Yolo/modelamiento/monitoreo_v2.py"

# Agente Edge: reporta los incidentes a la API
uv run uvicorn app.main:app --app-dir "Fase 2/Evidencias Proyecto/src/api" --reload
uv run python "Fase 2/Evidencias Proyecto/Yolo/modelamiento/monitoreo_api.py"
```

Presionar `q` en la ventana de video para finalizar.

### Entrenamiento

El entrenamiento se lanza **desde la raíz del repositorio**. El modelo base
`yolo26s.pt` no se versiona: Ultralytics lo descarga automáticamente la
primera vez que se usa.

```bash
uv run python "Fase 2/Evidencias Proyecto/Yolo/modelamiento/entrenamiento.py"
```

### Anonimización de la evidencia

La banda difuminada se ancla en el punto medio de los dos ojos que reporta YuNet
y se recorta a la caja de la cara, de modo que nunca queda más ancha ni más alta
que el rostro. La detección de rostros se mide sobre la misma cámara y el mismo
dataset: YuNet acierta en el 100% de las personas frente al 17% de una cascada
Haar frontal, con 16,9 ms frente a 58,9 ms de latencia.
