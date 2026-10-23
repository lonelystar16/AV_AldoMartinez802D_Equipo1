# Protocolo de la baliza zonal

**Versión 1.0 · 20-10-2026 · tarea 3.3 del D2.** Responsable: Iahn Vera. Apoyo: Fernando Muñoz (firmware y receptor simulado).

Este documento es el **contrato** entre el agente Edge y la baliza zonal. Lo cumplen por igual el firmware del M5Stack StickS3 (tarea 4.7) y el receptor simulado (tarea 4.6), así el agente no distingue entre los dos. Corresponde a las interfaces **I-02** (`POST /alert`) e **I-03** (`GET /health`) del capítulo de arquitectura, y a los requisitos RF-07, RF-09, RF-10, RNF-02, RNF-11 y RNF-14 del SRS.

## 1. Red y direccionamiento

| Aspecto | Definición |
| --- | --- |
| Red | WiFi de 2,4 GHz con WPA2, en una red de dispositivos separada de la de los usuarios (SSID o VLAN propia) |
| Dirección | IP fija mediante reserva DHCP en el router. Opcional: nombre mDNS `cv-<beacon_id>.local` |
| Transporte | HTTP/1.1 sobre TCP, puerto **80** |
| Formato | JSON en UTF-8 (`Content-Type: application/json`). Cuerpo máximo de 1 KB |
| Quién inicia | Siempre el agente Edge. La baliza nunca abre conexiones hacia el servidor |
| Resolución de la baliza | El agente obtiene de la API la relación zona → baliza → IP (`GET /edge/config`) y la mantiene en memoria |

## 2. Autenticación

- `POST /alert` exige la cabecera `Authorization: Bearer <BALIZA_TOKEN>`. Sin token, o con un token distinto, la baliza responde `401` y no suena (RNF-11).
- El token es una cadena aleatoria de al menos 32 caracteres. El agente lo lee de la variable de entorno `BALIZA_TOKEN`; el firmware lo guarda en la memoria NVS del dispositivo. Nunca se escribe en el código ni se sube al repositorio.
- La baliza compara el token en tiempo constante.
- `GET /health` es público y no entrega datos de incidentes.

## 3. `POST /alert`: activar la alerta

### Petición

```http
POST /alert HTTP/1.1
Host: 192.168.50.21
Authorization: Bearer <BALIZA_TOKEN>
Content-Type: application/json
```

```json
{
  "alert_id": "6f1c2a9e-3b7d-4e55-9a10-2c8f1d7e4b21",
  "zone_id": "zona-norte",
  "zone_name": "Zona Norte",
  "violations": ["missing_helmet", "missing_reflective_vest"],
  "duration_s": 10,
  "sound": "siren",
  "message": "USO OBLIGATORIO DE CASCO",
  "sent_at": "2026-10-20T14:30:00.120Z"
}
```

| Campo | Tipo | Obligatorio | Validación |
| --- | --- | --- | --- |
| `alert_id` | UUID | Sí | Identifica la orden. Un reintento usa el **mismo** `alert_id` |
| `zone_id` | Texto | Sí | Debe coincidir con la zona configurada en la baliza; si no, responde `409` |
| `zone_name` | Texto | Sí | Hasta 20 caracteres; se muestra en pantalla |
| `violations` | Lista | Sí | Uno o dos valores entre `missing_helmet` y `missing_reflective_vest` |
| `duration_s` | Entero | Sí | Entre 1 y 30 (RF-10) |
| `sound` | Texto | No | `siren` (por defecto), `voice` o `beep` (RF-10) |
| `message` | Texto | No | Hasta 40 caracteres; reemplaza el texto por defecto |
| `sent_at` | Fecha ISO 8601 | Sí | Con zona horaria. Solo informativo: la baliza no depende de su reloj |

### Respuestas

| Código | Cuándo | Cuerpo |
| --- | --- | --- |
| `200 OK` | La alerta empezó, o ya estaba sonando con el mismo `alert_id` (reintento) | `{"status": "alerting", "alert_id": "…", "duplicate": false}` |
| `400 Bad Request` | JSON inválido o un campo fuera de rango | `{"error": "invalid_field", "field": "duration_s"}` |
| `401 Unauthorized` | Token ausente o incorrecto | `{"error": "unauthorized"}` |
| `409 Conflict` | El `zone_id` no es el de esta baliza | `{"error": "wrong_zone", "zone_id": "zona-sur"}` |
| `413 Payload Too Large` | Cuerpo mayor que 1 KB | Sin cuerpo |

**La baliza responde antes de terminar de sonar.** Valida, arranca el sonido y la pantalla en segundo plano y responde en menos de 200 ms. El sonido dura `duration_s` segundos.

**Alertas superpuestas.** Si llega una orden nueva mientras suena otra, la baliza muestra la más reciente y reinicia la duración. Un reintento con el mismo `alert_id` responde `200` con `"duplicate": true` y no reinicia nada.

### Política del agente Edge

| Situación | Acción del agente | Valor de `beacon_alert.status` en la API |
| --- | --- | --- |
| Responde `200` | Mide el tiempo de ida y vuelta | `alerted`, con `latency_ms` |
| No responde en **1,5 s** o falla la conexión | Reintenta **una vez** con el mismo `alert_id` | `alerted` si el reintento funciona |
| El reintento tampoco responde (3 s en total) | Deja de intentar | `failed` |
| Responde `400`, `401`, `409` o `413` | No reintenta: es un error de configuración | `failed` (y lo registra en su log) |
| La baliza ya estaba marcada fuera de línea | No envía la orden | `skipped_offline` |

Con esta política, la alerta ocupa como máximo 3 s del presupuesto de 5 s (RNF-02).

## 4. `GET /health`: *heartbeat*

### Petición y respuesta

```http
GET /health HTTP/1.1
Host: 192.168.50.21
```

```json
{
  "status": "ok",
  "protocol": "1",
  "beacon_id": "baliza-01",
  "zone_id": "zona-norte",
  "firmware": "1.0.0",
  "battery_pct": 87,
  "charging": false,
  "uptime_s": 12345,
  "rssi_dbm": -61,
  "alerting": false
}
```

`status` vale `ok`, o `low_battery` si la batería está bajo el 15 %. El campo `protocol` permite cambiar este contrato más adelante sin romper balizas antiguas.

### Reglas del *heartbeat*

| Regla | Valor |
| --- | --- |
| Frecuencia | Cada **30 s** por baliza (RNF-14) |
| Espera máxima | 1,5 s |
| Paso a fuera de línea | **3 fallos consecutivos** (unos 90 s) |
| Vuelta a en línea | El primer `200` |
| Aviso a la API | Solo cuando cambia el estado o la batería baja del 15 %: `PUT /edge/beacons/{beacon_id}/status` con `{"online": true, "battery_pct": 87, "checked_at": "…"}` (I-05) |

## 5. Comportamiento de la baliza

| Estado | Pantalla (1,14") | Sonido |
| --- | --- | --- |
| Conectando | «Conectando…», nombre de la red | Ninguno |
| En línea (reposo) | Nombre de la zona, IP, batería y un punto verde | Ninguno |
| Alerta | Fondo rojo, nombre de la zona y el EPP faltante en letras grandes («SIN CASCO», «SIN CHALECO» o ambos), o el `message` si viene | `siren`, `voice` o `beep` durante `duration_s` |
| Sin WiFi | «Sin conexión» y un punto rojo; reintenta cada 5 s | Ninguno |
| Batería baja | Aviso «Batería baja» en reposo | Un pitido corto cada 5 minutos |

- **Botón A:** silencia la alerta en curso (la pantalla se mantiene hasta que termina la duración).
- **Sin vibración:** la baliza es fija y nadie la porta (decisión del 23-09-2026).
- **Mensaje de voz** (`sound: "voice"`): un audio pregrabado por tipo de infracción, guardado en la memoria del equipo.

## 6. Configuración del firmware

Cada baliza se configura una vez, antes de instalarla:

| Parámetro | Ejemplo | Dónde se guarda |
| --- | --- | --- |
| `wifi_ssid`, `wifi_password` | `CascoVision-Dispositivos` | NVS |
| `beacon_id` | `baliza-01` | NVS |
| `zone_id` | `zona-norte` | NVS |
| `token` | 32 caracteres aleatorios | NVS |

El repositorio incluye solo `secrets.example.h` con valores de ejemplo; el archivo real queda fuera de Git. La misma `beacon_id` y la IP se registran en el dashboard (RF-09) para que la API las entregue al agente.

## 7. Receptor simulado

El receptor simulado (`receptor-sim`, tarea 4.6) implementa exactamente este contrato para desarrollar y probar sin el equipo físico. Además:

- Registra cada orden recibida en un archivo JSONL con la hora de llegada, para medir la latencia de extremo a extremo (prueba de RNF-02).
- Acepta variables para simular fallas: `SIM_DELAY_MS` (demora la respuesta) y `SIM_FAIL_RATE` (fracción de peticiones que no responde).
- Responde `GET /health` con una batería ficticia.

## 8. Seguridad y limitaciones

- El tráfico va por HTTP sin cifrar, así que el token podría verse dentro de la red de dispositivos. Se mitiga separando esa red (§1). La evolución prevista es MQTT con TLS.
- Una baliza solo acepta órdenes de su propia zona (`409` en caso contrario), lo que evita que un error de configuración haga sonar el sector equivocado.
- El cuerpo tiene un tope de 1 KB y los textos un largo máximo, para proteger la memoria del dispositivo.

## 9. Casos de prueba que se derivan de este contrato

| ID | Caso | Resultado esperado |
| --- | --- | --- |
| PB-01 | Orden válida | `200`, suena y muestra la zona en < 200 ms |
| PB-02 | Sin token o con token incorrecto | `401`, no suena |
| PB-03 | `duration_s` = 0 o 31 | `400` con `field: "duration_s"` |
| PB-04 | `zone_id` de otra zona | `409`, no suena |
| PB-05 | Reintento con el mismo `alert_id` | `200` con `duplicate: true`, no reinicia |
| PB-06 | Receptor con `SIM_DELAY_MS=2000` | El agente reintenta una vez y registra `failed` a los 3 s |
| PB-07 | Receptor apagado 3 ciclos | La baliza pasa a fuera de línea y el agente informa a la API |
| PB-08 | Baliza fuera de línea y nueva infracción | No se envía la orden; el incidente queda con `skipped_offline` |

Estos casos se incorporan al plan de pruebas (D3, tarea 3.7).

## Cambios respecto del borrador del 23-09-2026

- Los campos pasan del español (`zona`, `tipo`, `duracion_s`) al inglés, igual que el contrato de la API.
- Se agregan `alert_id` (reintentos sin duplicar la alerta), la validación de zona (`409`) y los campos de batería y señal en `/health`.
- Se fija la política de 1,5 s por intento con un reintento, que cierra el SRS v0.4 (§4.6).
