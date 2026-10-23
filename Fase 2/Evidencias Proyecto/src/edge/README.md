# Agente Edge (tarea 4.4)

Lee la cámara a 1 cuadro por segundo y detecta la falta de casco o chaleco con el motor de `Yolo/modelamiento/` (YOLO26s, ByteTrack y difuminado YuNet). Solo avisa de las personas que pisan la zona de riesgo de la cámara. La alerta sale primero hacia la baliza (`docs/PROTOCOLO_BALIZA.md`) y después hacia la API, desde un hilo aparte. Si la API no responde, los incidentes quedan en una cola en disco.

```powershell
uv sync --group dev
uv pip install --index-url https://download.pytorch.org/whl/cpu torch torchvision
uv pip install ultralytics lap "opencv-python>=4.11,<5.0"   # más onnxruntime si se usa --modelo .onnx
$env:EDGE_API_TOKEN = "<token de la API>"; $env:BALIZA_TOKEN = "<token de la baliza>"
uv run python "Fase 2/Evidencias Proyecto/src/edge/agente.py" --fuente 0
```

| Opción | Uso |
| --- | --- |
| `--config` | JSON con la cámara, la zona, el polígono, la baliza y la API (ver `config.example.json`) |
| `--fuente` | `rtsp://…`, un archivo de video o el índice de la webcam. También vale la variable `CAMARA_FUENTE`, para no dejar las credenciales de la cámara en un archivo |
| `--fps` | Cuadros analizados por segundo (1 por defecto) |
| `--modelo` | `.pt` u `.onnx` (por defecto, `models/cascovision_yolo26s.pt`) |
| `--ping` | Segundos entre reavisos de quien sigue sin EPP (60 por defecto) |
| `--bucle`, `--sin-ventana` | Repite el video al terminar; no abre la ventana |

El polígono de `poligono` va en coordenadas relativas (0 a 1) del cuadro. Una persona está en la zona si el punto medio de sus pies cae dentro. Se usan `127.0.0.1` o una IP fija, no `localhost`: en Windows, `localhost` prueba IPv6 primero y suma ~1,5 s a cada alerta.

Salidas en `edge-datos/` (fuera de Git): la cola `cola_incidentes.jsonl` y `ultimo_cuadro.jpg`, el último cuadro ya difuminado para la vista en vivo. La evidencia queda en `incidents/AAAA/MM/DD/`.

## Cámaras IP (RTSP)

- **Transporte:** el agente pide RTSP por TCP. Por UDP, un paquete perdido corrompe el cuadro que analiza el modelo. Para cambiarlo se define `OPENCV_FFMPEG_CAPTURE_OPTIONS` antes de lanzar el agente.
- **Caída de la cámara:** si pasan 5 s sin cuadros, el agente la da por caída y vuelve a abrir la URL cada 2 s. Si al volver la persona sigue en la imagen, el seguimiento continúa sobre el mismo incidente.
- **Prueba sin cámara real:** `tests/camara_rtsp_simulada.py` publica un video como cámara IP en H.264, con el ffmpeg del sistema:

  ```powershell
  uv run python "Fase 2/Evidencias Proyecto/tests/camara_rtsp_simulada.py" video.mp4 8554
  uv run python "Fase 2/Evidencias Proyecto/src/edge/agente.py" --fuente rtsp://127.0.0.1:8554/camara
  ```

  `tests/test_edge_rtsp.py` comprueba la lectura en vivo y la reconexión. Sin ffmpeg, la prueba se omite.
- **Prueba de punta a punta (23-10-2026):** cámara simulada, agente con `cascovision_yolo26s.pt`, baliza simulada y API. Resultado:
  - Se registró un incidente con pings cada 10 s y la baliza se alertó en 7 a 37 ms.
  - Se cortó la cámara 6 s: el agente lo detectó a los 5 s y se reconectó.
  - Al volver la cámara, siguió el mismo incidente, que terminó con 5 pings.

Pendiente: leer la configuración desde `GET /edge/config` e informar el estado de la baliza con `PUT /edge/beacons/{id}/status`, cuando la API los tenga (tarea 4.15), y armar su imagen Docker (tarea 4.17).
