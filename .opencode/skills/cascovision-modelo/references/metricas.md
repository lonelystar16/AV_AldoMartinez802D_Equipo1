# Protocolo de evaluación y cómo leer las cifras

## Qué se mide y por qué hay dos juegos de métricas

El SRS (RNF-05) fija un criterio de aceptación en términos de mAP y recall
sobre el conjunto de validación:

> mAP@0,5 ≥ 0,90 y recall ≥ 0,85

Pero el producto no vende "detectar cajas": vende **avisar cuando alguien no
lleva EPP**. Un detector puede tener un mAP mediocre y ser excelente avisando,
o al revés. Por eso se miden las dos cosas y hay que reportar las dos.

### Métricas por clase

Las que usa el RNF-05. Se obtienen con `model.val()`:

- mAP@0,5 y mAP@0,5:0,95, media sobre las clases.
- Precisión y recall, medios sobre las clases.
- Y por clase, con `metricas.box.class_result(i)` que devuelve
  `(precision, recall, ap50, ap)`.

Ojo con la API de Ultralytics: `metricas.box.maps` es el mAP@0,5:0,95 **por
clase**, no el mAP@0,5. Para el mAP@0,5 por clase está `ap50`, dentro de
`class_result(i)`.

### Métricas de negocio

Las reglas ¿lleva casco? y ¿lleva chaleco?, sobre el split de test:

- **Aciertos**: el sistema dijo lo correcto.
- **Falsos positivos**: dijo "no lleva" cuando sí llevaba. Es el error caro:
  un aviso injusto desgasta al prevencionista y hace que ignoren el sistema.
- **Falsos negativos**: dijo "sí lleva" cuando no llevaba. Es el error más
  grave: no se avisa a quien va sin EPP.
- Precisión, recall y exactitud de cada regla.

## Cómo se construye el ground truth de las reglas

El dataset trae clases negativas explícitas, así que la verdad de "¿lleva
casco?" sale de las cajas dentro de cada persona:

- Una persona con caja `helmet` → sí lleva casco.
- Una persona con caja `no_helmet` → no lleva casco.
- Una persona sin ninguna de las dos → **indeterminado**: se excluye de la
  métrica, porque no hay verdad que aplicar.

En el split de test, 129 imágenes con 205 personas. 112 personas tienen ground
truth evaluable para la regla de casco y 136 para la de chaleco (el resto no
tiene señal en esa zona).

## Cómo se empareja una persona detectada con una real

1. Se calculan las cajas de la clase `Person` detectadas y las reales.
2. Se asignan por IoU máximo, de forma **global** (no codiciosa): se ordenan
   los pares por IoU descendente y se van fijando. Un emparejamiento codicioso
   puede dejar sin emparejar una detección correcta si una detección peor se
   lleva antes a la misma persona real.
3. Umbral de IoU: 0,30.

El EPP (casco, chaleco) se asocia a una persona si su solapamiento **dentro**
de la caja de la persona supera 0,35. Es el mismo criterio que usa el motor en
tiempo real, así que la evaluación mide lo que el sistema haría.

## Personas no detectadas

Una persona real que el detector no vio se cuenta como **falso negativo**: el
sistema no dice nada, y no avisar a quien va sin EPP es el peor resultado. Se
registra como una predicción de "sí lleva" (cumplimiento), que es como se
comporta el sistema en la práctica.

## Comparar detectores con vocabularios distintos

El modelo anterior de 11 clases y el actual de 5 clases no comparten ids de
clase. Para compararlos hay que usar el flag `--perfil`:

| Perfil | Modelo | Regla de decisión que aplica |
| --- | --- | --- |
| `5clases` | El actual | `helmet`/`no_helmet`, `vest`/`no_vest` explícitos |
| `11clases` | El anterior | `helmet` presente → cumple; si no, falta. `none` reinterpretado por zona |

Ambos se miden contra el mismo ground truth del split de test. Lo que se
compara es el **comportamiento**, no los ids.

## Línea base

Modelo de 11 clases (`cascovision_yolo26s.pt`) sobre el split de test:

| Regla | Precisión | Recall | Exactitud |
| --- | --- | --- | --- |
| ¿Lleva casco? | 1,000 | 0,643 | 0,643 |
| ¿Lleva chaleco? | 0,951 | 0,583 | 0,566 |

Interpretación: el modelo anterior era muy preciso (casi nunca acusaba a
alguien que sí llevaba casco) pero se le escapaban muchos casos: su recall de
0,64 en la regla de casco es la medida de ese problema. Es exactamente el
comportamiento que el SRS documentaba para train-9 (recall 0,757 medido con
otro dataset y otro protocolo).

## Advertencia sobre el mAP promedio

El dataset anterior tenía 11 clases, de las cuales 6 no usaba el producto
(guantes, botas, gafas y sus negativos). El promedio de mAP@0,5 de train-9
(0,611) estaba_lastamente_hundido por esas 6 clases irrelevantes.

El dataset nuevo tiene 5 clases, todas del producto. **El promedio de mAP@0,5
sube por construcción, no porque el modelo sea mejor.** La comparación honesta
son las reglas de negocio y las métricas por clase, no el promedio.

## Guardas

- Los splits train/valid/test son disjuntos por nombre de archivo original
  (sin el sufijo `.rf.<hash>` de Roboflow). Al agregar imágenes, mantén esa
  propiedad o las métricas se inflan.
- Si cambias el dataset, regenera el `labels.cache` (bórralo) antes de evaluar.
- Verifica que `verify_image_label` acepta todas las etiquetas con el `nc` del
  YAML: si no, Ultralytics las descarta en silencio.
