---
name: Agente Edge de CascoVision
description: Agente Edge de CascoVision - motor de deteccion de EPP, reglas de zona, difuminado de rostros con YuNet, seguimiento ByteTrack, cola local de incidentes y envio a la API. Usalo al trabajar en Yolo/testing y modelamiento/motor_cascovision.py, monitoreo_api.py, monitoreo_v2.py o el flujo de evidencia.
---

# Agente Edge de CascoVision

El agente Edge analiza el video de la cámara, decide quién va sin EPP, difumina
los rostros de la evidencia y reporta los incidentes a la API. Corre en la red
de la faena: el video nunca sale de la obra.

## Archivos

| Archivo | Rol |
| --- | --- |
| `Yolo/testing y modelamiento/motor_cascovision.py` | Toda la lógica: detección, reglas, difuminado, evidencia |
| `Yolo/testing y modelamiento/monitoreo_api.py` | Agente Edge. Reporta a la API con reintentos y cola local |
| `Yolo/testing y modelamiento/monitoreo_v2.py` | Monitoreo local, sin API |

## Flujo de una detección

1. `model.track(frame, persist=True, tracker="bytetrack.yaml")` — el tracker se
   fija explícitamente porque el checkpoint arrastra `tracktrack.yaml`, que en
   Ultralytics 8.4 devuelve identificadores nulos.
2. Se filtran las detecciones por clase y por confianza mínima
   (`CONF_MIN_POR_CLASE`).
3. Se agrupan por persona: el EPP se asocia a la persona si su solapamiento
   dentro de la caja de la persona supera `SOLAPAMIENTO_MIN` (0,35).
4. `evaluar_persona()` decide el estado de cada persona.
5. Se difuminan los rostros **antes de dibujar**, para que la evidencia salga
   limpia.
6. Se dibuja y se guarda la evidencia.
7. Si el estado es una infracción, se registra y se envía a la API.

## Reglas de negocio

El detector de 5 clases declara las infracciones de forma positiva:

- `helmet` detectada → cumple. `no_helmet` detectada → **falta casco**.
- `vest` detectada → cumple. `no_vest` detectada → **falta chaleco**.
- Ninguna de las dos en esa zona → estado indeterminado.

Cuando coexisten `helmet` y `no_helmet` (el detector se contradice), gana la de
mayor confianza; si hay empate en confianza, el positivo.

El caso indeterminado lo resuelve `POLITICA_SIN_DATOS`:
- `"infraccion"` (por defecto): también se notifica. Conservador: en una faena
  no avisar puede costar un accidente.
- `"cumple"`: solo se notifica la infracción confirmada.

## Seguimiento y suavizado

- Una infracción se confirma tras aparecer en **2 de los últimos 5 frames**
  (`VENTANA_SUAVIZADO`, `MIN_FRAMES_PARA_ALERTAR`). Evita alertas por ruido de
  un solo frame.
- Se notifica **una vez por cambio semántico**: `clave_violacion()` traduce los
  estados a tipos de infracción, así que alternar entre `falta_chaleco` y
  `sin_chaleco` no genera incidentes repetidos.
- Una persona que no aparece durante `FRAME_PARA_DESCARTAR` frames (45) se
  descarta del historial.

## Difuminado de rostros

- YuNet (`cv2.FaceDetectorYN`), detector neuronal que cubre frontal y perfil.
  No es una cascada Haar: OpenCV 5.0 eliminó `CascadeClassifier`.
- La banda difuminada se ancla en el punto medio de los dos ojos que reporta
  YuNet y se recorta a la caja de la cara, así que nunca queda más ancha ni
  más alta que el rostro.
- Si YuNet no encuentra un rostro, se aplica una banda conservadora sobre la
  caja de cabeza (`CLASES_CABEZA`: `helmet`, `no_helmet`).
- Se difumina **antes** de dibujar las cajas y el texto, para que la evidencia
  no contenga marcas de detección sobre las caras.

## Evidencia

Se guarda en `incidents/AAAA/MM/DD/`, con el frame ya difuminado y anotado. La
ruta que se envía a la API es **relativa** (`incidents/AAAA/MM/DD/archivo.jpg`),
porque la API rechaza rutas absolutas.

## Cola local

`monitoreo_api.py` no pierde evidencia si la API no responde:

- 3 intentos con 5 s de espera entre ellos, timeout de 10 s.
- Si la API no está disponible, el incidente se guarda en
  `db/cola_incidentes.jsonl` (máximo 500).
- La cola se reenvía cuando la API se recupera.
- Errores 400/401/403/422 **no** se reintentan: no tiene sentido, el incidente
  es inválido o no autorizado.

## Baliza

Hoy el agente informa `beacon_alert.status = "skipped_offline"`: la orden
`POST /alert` a la baliza es la tarea 4.4 y todavía no existe. El flujo
previsto es que el agente Edge llame **directamente** a la baliza (sin pasar
por la API) para que la alerta sea rápida y funcione aunque la API esté caída.

## Requisitos

- `EDGE_API_TOKEN` debe tener el **mismo valor** en la terminal de la API y en
  la del agente. Si no, la API responde 401.
- `lap` instalado (el grupo `yolo` de uv lo incluye): ByteTrack lo importa de
  forma directa.
- `cv2.FaceDetectorYN` requiere OpenCV ≥ 4.5.4.

## Referencias

- `references/clases.md` — el mapeo de clases del detector y su relación con las
  reglas de negocio.
