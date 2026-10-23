# Mapeo de clases y protocolo de evaluación del detector

Este documento reúne las dos cosas que hay que tener a mano al trabajar con el
detector de EPP: **cómo se determinaron las clases** y **cómo se mide el
desempeño**. Sin esto, las cifras del modelo no son reproducibles ni
comparables.

---

## Parte 1. El mapeo de clases

### Resumen

| Id | Nombre | Significado | Zona en la persona |
| --- | --- | --- | --- |
| 0 | `helmet` | Casco sobre la cabeza | Cabeza, relH ≈ 0,18 |
| 1 | `no_helmet` | Persona **sin** casco | Cabeza, relH ≈ 0,20 |
| 2 | `no_vest` | Persona **sin** chaleco | Torso, relH ≈ 0,44 |
| 3 | `Person` | Persona completa | Contenedor de las demás |
| 4 | `vest` | Chaleco reflectante | Torso, relH ≈ 0,48 |

### Cómo se determinó

El dataset no traía documentación de clases: el YAML original declaraba 4
clases (`Helmet`, `NoHelmet`, `NoVest`, `Vest`) mientras las etiquetas reales
usaban índices 0..4. El mapeo se determinó combinando cuatro evidencias
independientes.

#### 1. Contención de cajas

Para cada clase se midió qué fracción de su área cae dentro de las cajas de
cada otra clase:

| Clase | Contenida en | Fracción |
| --- | --- | --- |
| 0 helmet | 3 | 0,68 |
| 1 no_helmet | 3 | 0,83 |
| 2 no_vest | 3 | 0,91 |
| 4 vest | 3 | **1,06** |

La clase 3 es el contenedor: casi toda el área de las demás cae dentro. La
fracción de 1,06 para la clase 4 (mayor que 1 porque una caja puede solaparse
con dos personas) la sitúa como algo **dentro** de la persona.

#### 2. Geometría relativa a la persona

Centro vertical relativo medido desde el centro de la persona (negativo = por
encima) y altura relativa a la altura de la persona:

| Clase | Centro vertical relativo | Altura relativa |
| --- | --- | --- |
| 0 helmet | −0,40 | 0,18 |
| 1 no_helmet | −0,38 | 0,20 |
| 2 no_vest | −0,10 | 0,44 |
| 4 vest | −0,04 | 0,48 |

Las clases 0 y 1 están en la cabeza; las clases 2 y 4 en el torso.

#### 3. Inspección visual

Se recortaron y revisaron las cajas de cada clase por separado:

- **0**: cascos rojos, blancos y amarillos.
- **1**: cabezas con pelo, sin casco.
- **2**: ropa de torso sin reflectante.
- **3**: personas completas; la caja abraza a la persona de la cabeza a los pies.
- **4**: chalecos reflectantes con bandas.

#### 4. Exclusividad mutua

Dos clases que describen el mismo fenómeno no pueden coexistir en la misma
persona. En el split de validación:

| Combinación | Frecuencia |
| --- | --- |
| `no_helmet` + `no_vest` | 25,8 % |
| `helmet` + `no_vest` | 18,2 % |
| `helmet` + `vest` | 14,4 % |
| `no_helmet` + `vest` | 9,6 % |
| `helmet` + `no_helmet` | **0,7 %** |
| `no_vest` + `vest` | **0,2 %** |

Las combinaciones coherentes abundan; las contradictorias son residuales. Eso
confirma que 0/1 son el par del casco y 2/4 el par del chaleco.

### La diferencia con el modelo anterior

El modelo de 11 clases (train-9) tenía:

| Id | Nombre | Significado |
| --- | --- | --- |
| 0 | helmet | Casco |
| 1 | gloves | Guantes |
| 2 | vest | Chaleco |
| 3 | boots | Botas |
| 4 | goggles | Gafas |
| 5 | none | Caja genérica de "sin implemento" |
| 6 | Person | Persona |
| 7 | no_helmet | Caja de objeto que no es un casco |
| 8-10 | no_goggle, no_gloves, no_boots | Negativos de esos implementos |

Dos consecuencias:

1. **El vocabulario no coincide.** El mapeo por nombre de Ultralytics no
   traslada nada útil: el modelo nuevo no tiene `none`, ni guantes, ni botas.
   Por eso el entrenamiento parte de la base limpia `yolo26s.pt`.
2. **El significado de `no_helmet` cambió.** Antes era "caja de objeto que no
   es un casco" (se descartaba por tamaño y posición); ahora es "persona sin
   casco", una clase negativa explícita.

### La clase `none` y su reinterpretación

El modelo de 11 clases no tenía clase `no_vest`. La clase `none` era una caja
genérica que el motor reinterpretaba por zona del cuerpo: si caía en el torso
era chaleco ausente, si caía en la cabeza era casco ausente.

Esa heurística desapareció con el detector de 5 clases: `no_vest` ya es una
clase explícita. `motor_cascovision.py` ya no tiene `clasificar_none()`, ni las
constantes `CORTE_CABEZA` y `TAMANO_CHALECO`.

La consecuencia de negocio es la importante: **la infracción ya no se infiere
de la ausencia de un casco, la declara el detector**. El SRS y las métricas deben
reflejar ese cambio de decisión.

---

## Parte 2. Protocolo de evaluación

### Por qué hay dos juegos de métricas

El SRS (RNF-05) fija un criterio de aceptación en términos de mAP y recall:

> mAP@0,5 ≥ 0,90 y recall ≥ 0,85

Pero el producto no vende "detectar cajas": vende **avisar cuando alguien no
lleva EPP**. Un detector puede tener un mAP mediocre y ser excelente avisando,
o al revés. Por eso se miden las dos cosas y hay que reportar las dos.

### Métricas por clase

Las que usa el RNF-05, obtenidas con `model.val()`:

- mAP@0,5 y mAP@0,5:0,95, media sobre las clases.
- Precisión y recall, medios sobre las clases.
- Y por clase, con `metricas.box.class_result(i)`, que devuelve
  `(precision, recall, ap50, ap)`.

> Ojo con la API de Ultralytics: `metricas.box.maps` es el mAP@0,5:0,95 **por
> clase**, no el mAP@0,5. Para el mAP@0,5 por clase está `ap50`, dentro de
> `class_result(i)`.

### Métricas de negocio

Las reglas ¿lleva casco? y ¿lleva chaleco?, sobre el split de test:

- **Aciertos**: el sistema dijo lo correcto.
- **Falsos positivos**: dijo "no lleva" cuando sí llevaba. Es el error caro:
  un aviso injusto desgasta al prevencionista y hace que ignoren el sistema.
- **Falsos negativos**: dijo "sí lleva" cuando no llevaba. Es el error más
  grave: no se avisa a quien va sin EPP.
- Precisión, recall y exactitud de cada regla.

### Ground truth de las reglas

El dataset trae clases negativas explícitas, así que la verdad de "¿lleva
casco?" sale de las cajas dentro de cada persona:

- Una persona con caja `helmet` → sí lleva casco.
- Una persona con caja `no_helmet` → no lleva casco.
- Una persona sin ninguna de las dos → **indeterminado**: se excluye de la
  métrica, porque no hay verdad que aplicar.

En el split de test, 129 imágenes con 205 personas. 112 personas tienen ground
truth evaluable para la regla de casco y 136 para la de chaleco (el resto no
tiene señal en esa zona).

### Emparejamiento de personas

1. Se calculan las cajas de la clase `Person` detectadas y las reales.
2. Se asignan por IoU máximo, de forma **global** (no codiciosa): se ordenan
   los pares por IoU descendente y se van fijando. Un emparejamiento codicioso
   puede dejar sin emparejar una detección correcta si una detección peor se
   lleva antes a la misma persona real.
3. Umbral de IoU: 0,30.

El EPP (casco, chaleco) se asocia a una persona si su solapamiento **dentro**
de la caja de la persona supera 0,35. Es el mismo criterio que usa el motor en
tiempo real, así que la evaluación mide lo que el sistema haría.

### Personas no detectadas

Una persona real que el detector no vio se cuenta como **falso negativo**: el
sistema no dice nada, y no avisar a quien va sin EPP es el peor resultado. Se
registra como una predicción de "sí lleva" (cumplimiento), que es como se
comporta el sistema en la práctica.

### Comparar detectores con vocabularios distintos

El modelo anterior de 11 clases y el actual de 5 clases no comparten ids de
clase. Para compararlos, `evaluacion.py` declara un **perfil** por detector, que
traduce sus ids de clase a los roles semánticos (casco, sin casco, chaleco, sin
chaleco, persona):

| Perfil | Modelo | Regla de decisión que aplica |
| --- | --- | --- |
| `5clases` | El actual | `helmet`/`no_helmet`, `vest`/`no_vest` explícitos |
| `11clases` | El anterior | `helmet` presente → cumple; si no, falta. `none` reinterpretado por zona |

Ambos se miden contra el mismo ground truth del split de test. Lo que se
compara es el **comportamiento**, no los ids.

### Línea base

Modelo de 11 clases (`cascovision_yolo26s.pt`) sobre el split de test:

| Regla | Precisión | Recall | Exactitud |
| --- | --- | --- | --- |
| ¿Lleva casco? | 1,000 | 0,643 | 0,643 |
| ¿Lleva chaleco? | 0,951 | 0,583 | 0,566 |

Interpretación: el modelo anterior era muy preciso —casi nunca acusaba a
alguien que sí llevaba casco— pero se le escapaban muchos casos: su recall de
0,64 en la regla de casco es la medida de ese problema. Es el mismo
comportamiento que documenta el README del modelo para train-9 (medido con otro
dataset y otro protocolo).

### Advertencia sobre el mAP promedio

El dataset anterior tenía 11 clases, de las cuales 6 no usaba el producto
(guantes, botas, gafas y sus negativos). El promedio de mAP@0,5 de train-9
(0,611) estaba hundido por esas 6 clases irrelevantes.

El dataset nuevo tiene 5 clases, todas del producto. **El promedio de mAP@0,5
sube por construcción, no porque el modelo sea mejor.** La comparación honesta
son las reglas de negocio y las métricas por clase, no el promedio.

### Guardas

- Los splits train/valid/test son disjuntos por nombre de archivo original
  (sin el sufijo `.rf.<hash>` de Roboflow). Al agregar imágenes, mantén esa
  propiedad o las métricas se inflan.
- Si cambias el dataset, regenera el `labels.cache` (bórralo) antes de evaluar.
- Verifica que `verify_image_label` acepta todas las etiquetas con el `nc` del
  YAML: si no, Ultralytics las descarta en silencio.

---

## Parte 3. Errores ya cometeros que conviene no repetir

- **YAML con `nc` equivocado**: Ultralytics no lanza error, marca la imagen como
  corrupta y la **descarta en silencio**. Con `nc: 4` sobre este dataset se
  perdía el 30 % de las imágenes de train.
- **Nombres con sufijo de Roboflow**: `imagen.with_suffix(".txt")` borra el
  `.rf.<hash>` y produce un nombre inexistente. Usa `imagen.stem + ".txt"`.
- **Coordenadas normalizadas contra píxeles**: las etiquetas de YOLO vienen en
  0-1; las detecciones del modelo, en píxeles. Convierte antes de comparar.
- **Emparejamiento codicioso**: emparejar por mejor IoU detección por detección
  deja detecciones correctas sin emparejar. Haz la asignación global.
- **`opencv-python` 5.x**: eliminó `cv2.CascadeClassifier`, que usan los scripts
  de prueba. La versión válida es `>=4.11,<5.0`.
- **Falta `lap`**: `ultralytics/trackers/utils/matching.py` lo importa de forma
  directa para ByteTrack.
- **`path: .` en el YAML**: Ultralytics resuelve `path` contra el directorio de
  trabajo, no contra la carpeta del YAML. Omite `path:` y usa rutas relativas.
- **Barra invertida en `.gitignore`**: `\` es carácter de escape, no separador.
  Las reglas no aplican y el dataset se puede subir por error.
- **`git check-ignore` con excepciones**: reporta la última regla coincidente,
  incluso si es una negación. La fuente de verdad es
  `git status --porcelain --ignored=matching`.
- **`core.ignorecase=true` en Windows**: una regla `agents.md` también ignora
  `AGENTS.md`.
