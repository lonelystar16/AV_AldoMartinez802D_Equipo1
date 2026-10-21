# El mapeo de clases del detector

## Resumen

| Id | Nombre | Significado | Zona en la persona |
| --- | --- | --- | --- |
| 0 | `helmet` | Casco sobre la cabeza | Cabeza, relH ≈ 0,18 |
| 1 | `no_helmet` | Persona **sin** casco | Cabeza, relH ≈ 0,20 |
| 2 | `no_vest` | Persona **sin** chaleco | Torso, relH ≈ 0,44 |
| 3 | `Person` | Persona completa | Contenedor de las demás |
| 4 | `vest` | Chaleco reflectante | Torso, relH ≈ 0,48 |

## Cómo se determinó

El dataset no traía documentación de clases: el YAML original declaraba 4 clases
(`Helmet`, `NoHelmet`, `NoVest`, `Vest`) mientras las etiquetas reales usaban
índices 0..4. El mapeo se determinó combinando tres evidencias independientes.

### 1. Contención

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

### 2. Geometría relativa a la persona

| Clase | Centro vertical relativo | Altura relativa |
| --- | --- | --- |
| 0 helmet | −0,40 | 0,18 |
| 1 no_helmet | −0,38 | 0,20 |
| 2 no_vest | −0,10 | 0,44 |
| 4 vest | −0,04 | 0,48 |

El centro vertical relativo se mide desde el centro de la persona: negativo
significa por encima. Las clases 0 y 1 están en la cabeza; las clases 2 y 4 en
el torso.

### 3. Inspección visual

Se recortaron y revisaron las cajas de cada clase por separado:

- **0**: cascos rojos, blancos y amarillos.
- **1**: cabezas con pelo, sin casco.
- **2**: ropa de torso sin reflectante.
- **3**: personas completas; la caja abraza a la persona de la cabeza a los pies.
- **4**: chalecos reflectantes con bandas.

### 4. Exclusividad mutua

Dos clases que describen el mismo fenómeno en el mismo sentido no pueden
coexistir en la misma persona. En el split de validación, la combinación
`helmet` + `no_helmet` aparece en el 0,7 % de las personas y `no_vest` +
`vest` en el 0,2 %. Las combinaciones que sí abundan son las coherentes:
`no_helmet`+`no_vest` (25,8 %), `helmet`+`no_vest` (18,2 %), `helmet`+`vest`
(14,4 %), `no_helmet`+`vest` (9,6 %).

## La diferencia con el modelo anterior

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

## La clase `none` y su reinterpretación

El modelo de 11 clases no tenía clase `no_vest`. La clase `none` era una caja
genérica que el motor reinterpretaba por zona del cuerpo: si caía en el torso
era chaleco ausente, si caía en la cabeza era casco ausente.

Esa heurística desapareció con el detector de 5 clases: `no_vest` ya es una
clase explícita. `motor_cascovision.py` ya no tiene `clasificar_none()`, ni las
constantes `CORTE_CABEZA` y `TAMANO_CHALECO`.

La consecuencia de negocio es la importante: **la infracción ya no se infiere
de la ausencia de un casco, la declara el detector**. El SRS y las métricas deben
reflejar ese cambio de decisión.

## Cómo se evalúa un detector con este mapeo

`evaluacion.py` declara un **perfil** por detector, que traduce sus ids de clase
a los roles semánticos (casco, sin casco, chaleco, sin chaleco, persona):

- `5clases`: el detector actual.
- `11clases`: el detector anterior, que además reinterpreta `none` por zona.

El ground truth siempre usa el esquema de 5 clases. Así se puede comparar el
comportamiento de dos detectores con vocabularios distintos sobre los mismos
datos: cada uno aplica su propia regla de decisión, y se mide contra el mismo
ground truth.
