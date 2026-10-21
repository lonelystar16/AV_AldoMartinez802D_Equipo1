---
name: Documentación de CascoVision
description: Qué documentación de CascoVision actualizar y con qué cifras - README raíz, README del modelo, README de la API, SRS y evidencias de fase. Úsalo al cambiar el comportamiento del sistema, el detector, la API o las métricas, o antes de entregar una fase.
---

# Documentación de CascoVision

La documentación es una entrega evaluada del proyecto, no un adorno. Cada
cambio de comportamiento obliga a actualizar un documento concreto. Esta skill
es el mapa de qué tocar y cuándo.

## Mapa de documentos

| Documento | Qué documenta | Se actualiza cuando |
| --- | --- | --- |
| `README.md` (raíz) | Descripción, arquitectura, tecnologías, estado del proyecto | Cambia la arquitectura, el estado de una fase o cómo se ejecuta algo |
| `Fase 2/Evidencias Proyecto/Yolo/README.md` | Dataset, entrenamiento, métricas del modelo, reglas de decisión | Cambia el detector, el dataset, las métricas o las reglas de negocio |
| `Fase 2/Evidencias Proyecto/models/README.md` | Los checkpoints versionados y sus métricas | Se cambia un modelo en `models/` |
| `Fase 2/Evidencias Proyecto/docs/API.md` | Contrato de la API: rutas, variables, migraciones, errores | Cambia una ruta, un campo, una validación o una variable de entorno |
| `Fase 2/Evidencias Grupales/D1_SRS_CascoVision.docx` | Requerimientos (RF, RNF) | Cambia un requisito o una decisión de negocio |

## Al cambiar el detector

Obligatorio en `Yolo/README.md`:

- El esquema de clases y su tabla de distribución por split.
- La tabla de métricas por clase y las de reglas de negocio.
- La comparación con la línea base, si cambió.
- El estado frente al RNF-05, sea cual sea: si no cumple, se documenta que no
  cumple y por qué, con el diagnóstico.

Y en `models/README.md` si el checkpoint de `models/` se reemplaza.

## Al cambiar las reglas de negocio

Esto es un cambio de **requisito**, no una mejora técnica. El SRS (`D1`) tiene
que reflejarlo.

Ejemplo real: con el detector de 5 clases, la regla de casco pasó de
"no se detectó casco" a "se detectó `no_helmet`". La decisión cambia de
*inferir la ausencia* a *detectar la negativa*. Eso toca:

- El SRS (RNF-05 y las reglas de negocio de los RF asociados).
- `Yolo/README.md`, en "Reglas de decisión".
- `docs/API.md` solo si cambia el contrato de la API (en este caso no: los
  tipos de incidencia siguen siendo `missing_helmet` y
  `missing_reflective_vest`).

## Al cambiar la API

`docs/API.md` es la referencia del contrato. Actualiza:

- La tabla de rutas (método, ruta, autenticación, descripción).
- La tabla de variables de entorno.
- La tabla de validaciones de campos, si cambia alguna.
- Los códigos de error, si cambian.
- La sección "Pendiente", cuando se cierre algo pendiente.

## Reglas de estilo

- **En español**, con las cifras en formato español: coma decimal, punto de
  miles (`0,857` no `0.857`).
- Las métricas siempre accompanied de con qué split y con qué protocolo se
  midieron. Una cifra sin contexto no es comparable.
- Si una métrica mejora porque cambió el criterio de medición, dilo
  explícitamente. Un mAP promedio que sube porque se quitaron 6 clases
  irrelevantes no es una mejora del modelo.
- No declares "cumple el RNF-05" si no cumple. Declara el estado real y el
  trabajo pendiente.

## Estado del proyecto

El `README.md` raíz lleva el estado de la fase en un bloque destacado al
principio. Actualízalo cuando:

- Avanza una fase o una entrega.
- Cambia lo que es ejecutable (por ejemplo, si la API pasa a requiring
  PostgreSQL o si aparece un `docker-compose.yml`).
- Cambian los comandos de ejecución.

## Evidencias de fase

Las carpetas `Fase 1/`, `Fase 2/Evidencias Grupales/` e
`Fase 2/Evidencias Individuales/` son entregables del curso: se versionan y no
se editan a la ligera. Antes de tocarlas, confirma con el equipo qué se
entrega en la fase actual.
