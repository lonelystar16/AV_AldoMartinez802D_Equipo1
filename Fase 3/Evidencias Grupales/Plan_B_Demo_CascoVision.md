# CascoVision: checklist y plan B de la demo en vivo

Esto es para la defensa de la Fase 3 (semanas 17 y 18) y corresponde a la tarea 7.4. La demo corre en un solo PC con Docker Desktop. Usa la webcam, o la cámara simulada, y la baliza StickS3. Este documento dice qué revisar antes y qué hacer si algo falla en vivo.

## 1. El día anterior

- [ ] Hacer `git pull` de `main` en el PC de la demo y revisar que el `.env` tenga los valores reales: `JWT_SECRET`, `BALIZA_TOKEN`, `EDGE_API_TOKEN` y la cuenta del administrador.
- [ ] Ejecutar `docker compose --profile dev build` con internet, para no depender de la red de la sala.
- [ ] Copiar el video público de la cámara simulada en `docker/rtsp-sim/video_prueba.mp4`. No se versiona: ver `docker/rtsp-sim/README.md`.
- [ ] Ejecutar `docker compose --profile dev up -d` y recorrer el flujo completo:
  1. Hay detección.
  2. La baliza se activa.
  3. El incidente aparece en el dashboard.
  4. Llega el correo a Mailpit (`http://127.0.0.1:8025`).
- [ ] Cargar el StickS3 y dejar a mano su cable USB-C. La batería es de 250 mAh, así que en la demo debe ir enchufado.
- [ ] Tener a mano el video de respaldo `Fase 3/Evidencias Grupales/VideoDeMuestra.mp4`, abierto en un reproductor local y no desde GitHub.
- [ ] Hacer un respaldo de la base de datos con datos de ejemplo (`docs/DESPLIEGUE_DOCKER.md`), para mostrar el historial y los reportes aunque la demo en vivo no genere incidentes.

## 2. Una hora antes, en la sala

- [ ] Conectar el PC y el StickS3 a la **misma red**, que debe ser el router propio o el hotspot del celular. El Wi-Fi de la universidad aísla a los clientes y la baliza no recibe la orden.
- [ ] Ejecutar `scripts/conectar-stick.ps1`, que configura por USB el Wi-Fi y la URL de la API en el Stick. Esperar el mensaje «Listo: Stick conectado».
- [ ] Revisar que el firewall de Windows permita conexiones entrantes TCP en el puerto de la API (8000). Si lo bloquea, el Stick no llega a la API.
- [ ] Si cambió la red, revisar `baliza.url` en `docker/edge/config.json`. Con una URL fija, el agente **no** toma la IP nueva que informa el Stick. Hay dos opciones: dejar `"url": ""`, para que la tome desde la API, o escribir la IP nueva.
- [ ] Levantar el sistema con `scripts/iniciar-cascovision-camara.ps1` (webcam) o con `docker compose --profile dev up -d` (cámara simulada).
- [ ] Entrar al dashboard (`http://127.0.0.1:8080`) con el administrador y dejar abierta la pestaña de monitoreo.

## 3. Si algo falla en vivo

| Falla | Señal | Plan B | Tiempo |
| --- | --- | --- | --- |
| La red de la sala no deja conectar el Stick | El Stick no muestra la API en pantalla | Usar el hotspot del celular y volver a ejecutar `conectar-stick.ps1` | 2 min |
| El StickS3 no responde | No suena, o `conectar-stick.ps1` no encuentra el puerto | Pasar a la baliza simulada del perfil `dev` y mostrar `http://127.0.0.1:8081/health` con `"alerting": true` | 1 min |
| La webcam no abre o detecta mal por la luz | Ventana negra o sin cajas | Cambiar a la cámara simulada (`docker compose --profile dev up -d`), que repite un video conocido | 2 min |
| La GPU falla (error 43 del controlador) | El agente no carga el modelo en CUDA | Correr el modelo `.onnx` en CPU: rinde unos 11 FPS y la demo solo necesita 1 FPS por cámara | 1 min |
| Docker no levanta o la API no responde | `docker compose ps` muestra servicios caídos | Reiniciar con `docker compose restart api`. Si no se arregla, pasar al video de respaldo | 3 min |
| Ningún plan B funciona | — | Mostrar `VideoDeMuestra.mp4` y el historial y los reportes desde el respaldo de la base | inmediato |

## 4. Quién hace qué durante la demo

| Rol | Persona | Responsabilidad |
| --- | --- | --- |
| Presenta | Por definir en el ensayo (tarea 7.3) | Narra el flujo y explica la alerta en la zona |
| Opera el PC | Por definir | Levanta el sistema, cambia de plan si algo falla y muestra el dashboard |
| Baliza y red | Por definir | Se encarga del Stick, el hotspot y `conectar-stick.ps1` |

> Antes de la defensa hay que ensayar la demo completa al menos una vez en la red que se va a usar, incluido el cambio a la baliza simulada.
