# CascoVision — Informe de resultados de pruebas

- **Versión:** borrador 0.2 (agrega rendimiento, seguridad y la suite completa; pendiente de revisión de Benjamín Cáceres)
- **Fecha de consolidación:** 11-11-2026 (v0.1) · 25-11-2026 (v0.2)
- **Rama de referencia:** `qa` (v0.1) · `dev-iahn` en `ca0e21d`, que contiene `qa` más las correcciones DEF-03 y DEF-04 (v0.2)
- **Commit de referencia revisado:** `3899640` (`3899640278b6d1199609a13f60bb91f19d6c4a5d`) en v0.1
- **Proyecto:** PTY4614 — Capstone, Ingeniería en Informática, Duoc UC
- **Equipo:** Benjamín Cáceres, Iahn Vera, Joaquín Armijo y Fernando Muñoz

## 1. Objetivo y alcance

Este informe consolida los resultados disponibles para el cierre de las tareas internas de QA **4.21 — API y base de datos** y **4.22 — Agente Edge y receptor simulado**, y desde la versión 0.2 también **5.4 — Rendimiento** y **5.5 — Seguridad**, con los casos PR y PS del Plan de Pruebas D3 (§4.3 y §4.4). Se consideran ejecuciones locales, la ejecución de integración continua (CI) ya realizada y la validación manual de RTSP informada por el equipo.

El informe complementa el Plan de Pruebas D3 publicado en el repositorio. No reemplaza la evidencia original de consola, los registros de CI ni los respaldos visuales de las pruebas manuales.

## 2. Resumen ejecutivo

| Tarea | Resultado consolidado | Estado propuesto |
|---|---|---|
| 4.21 — API y base de datos | 48 pruebas PostgreSQL aprobadas en ejecución local anterior; 11 pruebas de configuración aprobadas; 103 pruebas de API aprobadas y 5 omitidas localmente por requerir PostgreSQL. La CI histórica ejecutó la suite con PostgreSQL configurado: 323 aprobadas y 1 omitida. | **Validada** |
| 4.22 — Agente Edge y receptor simulado | 21 pruebas automatizadas aprobadas. La prueba automatizada RTSP se omitió en el equipo local por ausencia de FFmpeg; el equipo informa que la lectura y reconexión RTSP se validaron manualmente en otro dispositivo y que conserva sus evidencias. | **Aprobada mediante validación combinada** |
| Suite completa (25-11-2026) | `pytest` con PostgreSQL 16.15 desechable y `CASCOVISION_TEST_POSTGRES=1`: **408 passed, 0 skipped** en 79 s. Sin PostgreSQL: 347 passed y 61 skipped. | **Aprobada** |
| 5.4 — Rendimiento | PR-01, PR-03 y PR-05 aprobados con el stack Docker; PR-02 y PR-04 con la medición del 05-11 (ver §5). | **Aprobada, con PR-02 parcial** |
| 5.5 — Seguridad | PS-01 a PS-09 aprobados (ver §6). | **Aprobada** |
| Defectos | DEF-03 y DEF-04 encontrados al levantar la demo del README en una base nueva, corregidos y verificados (ver §7). | **Cerrados** |

Los resultados de CI se presentan por separado y **no se suman** a los resultados locales, porque corresponden a una ejecución de la suite que se solapa con ellos.

## 3. Tarea 4.21 — API y base de datos

### 3.1 Resultados locales

| Módulo | Resultado | Observación |
|---|---:|---|
| `tests/test_db.py` | **48 passed** | Ejecución anterior con PostgreSQL de pruebas. No se repitió en esta sesión debido a su duración elevada. |
| `tests/test_config.py` | **11 passed** en 0,08 s | Reejecutada el 11-11-2026. |
| `tests/test_auth.py` | Incluida en el bloque de API | Tres pruebas PostgreSQL se omitieron en la ejecución local sin `CASCOVISION_TEST_POSTGRES=1`. |
| `tests/test_config_endpoint.py` | Incluida en el bloque de API | Validación de diagnóstico/configuración de la API. |
| `tests/test_health.py` | Incluida en el bloque de API | Validación del endpoint de salud. |
| `tests/test_incidents.py` | Incluida en el bloque de API | Dos casos parametrizados de claves foráneas se omitieron localmente sin PostgreSQL. |
| `tests/test_recursos_reporte.py` | Incluida en el bloque de API | Validación de recursos, configuración Edge y reportes. |

Ejecución conjunta de los cinco módulos de API: **103 passed, 5 skipped en 1,80 s**.

Los cinco omitidos se desglosan así:

- Tres casos de `test_auth.py` que requieren PostgreSQL para probar creación/autenticación de usuario, rechazo de usuario inactivo y persistencia de revisiones en `incident_events`.
- Dos casos de `test_incidents.py` que comprueban el rechazo de una cámara o zona inexistente mediante claves foráneas.

### 3.2 Respaldo de integración continua

La ejecución histórica de CI asociada al PR #30 informó **323 passed y 1 skipped**. El workflow del repositorio configura un servicio PostgreSQL 16.15 y establece `CASCOVISION_TEST_POSTGRES=1`, por lo que la suite de CI ejecuta las pruebas condicionadas a PostgreSQL que se omitieron en la ejecución local descrita anteriormente.

La CI se registra como respaldo separado; sus conteos no se agregan a los resultados locales.

### 3.3 Conclusión de 4.21

Los resultados disponibles respaldan la validación funcional de API y persistencia: hay ejecución local satisfactoria de la batería PostgreSQL y configuración, pruebas de rutas aprobadas y una ejecución CI con PostgreSQL habilitado. No se registraron fallos en las ejecuciones informadas para este alcance.

**Estado propuesto: VALIDADA.**

## 4. Tarea 4.22 — Agente Edge y receptor simulado

### 4.1 Pruebas automatizadas locales

Ejecución conjunta del 11-11-2026:

| Archivo | Resultado |
|---|---:|
| `tests/test_edge_agente.py` | **8 passed** |
| `tests/test_receptor_sim.py` | **13 passed** |
| **Total** | **21 passed en 15,68 s** |

Las pruebas cubren, entre otros aspectos, el filtrado por zona, el envío de alertas, reintentos, detección de baliza fuera de línea, recuperación, autenticación del receptor, validación de órdenes, duplicados y registro JSONL.

### 4.2 Lectura y reconexión RTSP

La ejecución local de `tests/test_edge_rtsp.py` terminó con:

- **1 skipped** en 0,13 s.
- Motivo: `ffmpeg no está instalado` en el equipo local.

Este resultado se registra como una limitación del entorno local; no se presenta como una aprobación de la prueba automatizada.

Por separado, el equipo informa que la lectura de cámara RTSP y la reconexión fueron comprobadas manualmente en otro dispositivo y que conserva las evidencias de esa validación. Además, el README del agente Edge contiene un registro de prueba de punta a punta fechado el 23-10-2026 con cámara simulada, agente, baliza simulada y API: se documenta la recepción de alertas, el corte de cámara y la reconexión.

La evidencia visual o de consola conservada por el compañero no se adjunta en esta versión del informe; se mantiene resguardada para incorporarla en la consolidación final de evidencias, sin volver a clasificar la validación como pendiente.

### 4.3 Conclusión de 4.22

Las pruebas automatizadas del agente y receptor simulado aprobaron en su totalidad (21/21). La validación RTSP se considera satisfecha mediante la comprobación manual realizada por el equipo en otro dispositivo, diferenciándola explícitamente del test automatizado omitido en el equipo local.

**Estado propuesto: APROBADA mediante validación combinada (automatizada + manual).**

## 5. Tarea 5.4 — Rendimiento

**Ambiente (25-11-2026):** notebook con Windows 11, Intel i5-11400H (6 núcleos, 12 hilos), 16 GB de RAM y Docker Desktop 29.0.1 (WSL2). Stack `docker compose -p cv-entrega --profile dev up -d --build` sobre una base nueva: `db` (PostgreSQL 16.15), `api`, `dashboard`, `edge` (CPU, ONNX Runtime), `rtsp-sim`, `receptor-sim` y `mailpit`. Video `video_prueba.mp4` de la demo (300×300, en bucle). Modelo `cascovision_yolo26s.onnx` (`train-10`).

| ID | Medición | Resultado | Criterio | Estado |
|---|---|---|---|---|
| PR-01 | Latencia de la alerta física: hora del cuadro con infracción (`detected_at`, que el agente fija al guardar la evidencia, después de la inferencia) contra la hora de llegada a `receptor-sim` | **12 episodios: mediana 3,9 ms, máximo 9,4 ms.** Tramo de red de **137 órdenes** (envío → llegada): mediana 1,9 ms, percentil 95 de 6,4 ms. Sumando la inferencia de PR-03 (p95 100 ms), del cuadro a la baliza son menos de 0,2 s | < 5 s en el 95 % | ✅ |
| PR-02 | Tasa de análisis | 1 cuadro por segundo con 1 flujo; el agente usa ~1,4 núcleos y ~490 MB (medición del 05-11) | ≥ 1 cuadro/s por cámara con 4 flujos | ⚠️ Parcial: no se repitió con 4 flujos |
| PR-03 | Tiempo de inferencia en CPU, 500 cuadros | Mediana 88 ms, **p95 100 ms**, máximo 132 ms | ≤ 0,5 s por cuadro | ✅ |
| PR-04 | Actualización del dashboard | Intervalo de 2,5 s (medición del 05-11; se bajó desde 5 s por este caso) | ≤ 3 s | ✅ |
| PR-05 | Incidente registrado en la API → correo en el buzón (Mailpit) | **10 correos: mediana 0,08 s, máximo 0,12 s**; 10 de 10 quedaron `sent` en `notifications` | ≤ 30 s | ✅ |

Notas de método:

- **PR-01.** El aviso repetido de una persona que sigue sin EPP (ping) reusa el incidente, así que solo el inicio de cada episodio trae la hora del cuadro. Para juntar episodios se reinició el agente 10 veces y se repitió el aviso cada 10 s (`--ping 10`, solo para esta medición). Esa opción cambia la frecuencia de los avisos, no su latencia.
- **PR-05.** La API solo envía correo a prevencionistas activos. En una base nueva solo existe el administrador, así que se creó un prevencionista de prueba antes de medir. El tiempo no incluye la entrega por un servidor SMTP externo.

## 6. Tarea 5.5 — Seguridad

Los casos PS-01 a PS-05 y PS-09 se ejecutaron contra el stack en vivo del §5, además de las pruebas automatizadas que los cubren.

| ID | Caso | Resultado | Estado |
|---|---|---|---|
| PS-01 | Rutas de la API sin JWT, con firma alterada o con el token del agente | `401`, `401`, `401`. Automatizadas en `test_auth.py`, que también cubre el JWT vencido y el rol desconocido | ✅ |
| PS-02 | Supervisor intenta crear un usuario o modificar una baliza | `403`, `403`. Automatizadas en `test_usuarios.py` y `test_gestion_recursos.py` | ✅ |
| PS-03 | Evidencia de un incidente sin JWT | `401`; no se entrega la imagen | ✅ |
| PS-04 | `POST /alert` a la baliza sin token o con token incorrecto | `401`, `401`; no suena. Automatizada en `test_receptor_sim.py` | ✅ |
| PS-05 | `zone_id=' OR 1=1 --` en `/incidents` y `/reports` | `200` con 0 filas y `200`, sin error 500. En `almacen.py` los valores de los filtros van como parámetros (`%s`) y los nombres de columna salen de listas fijas (`FILTROS_PERMITIDOS`) | ✅ |
| PS-06 | Búsqueda de secretos en el repositorio | Solo se versiona `.env.example`; `git grep` de claves y tokens no encuentra valores reales, solo ejemplos de la documentación (`un_valor_secreto`) | ✅ |
| PS-07 | Rostros en la evidencia guardada | **0 de 12** evidencias con rostro detectable por YuNet (umbral 0,6). Control: en el video original, el mismo detector encuentra rostros en 40 de 65 cuadros muestreados. Las 12 evidencias reales tienen `face_blurred = true`; las 4 con `false` son los incidentes ficticios del seed, sin imagen | ✅ con 12 evidencias (el plan pide 50) |
| PS-08 | Conexiones salientes del servidor | 205 muestras en 20 minutos de las conexiones TCP establecidas de `api`, `edge` y `receptor-sim`: **ninguna hacia fuera de la red local**. El SMS quedó fuera de alcance, así que ya no hay conexiones a Twilio | ✅ con 20 minutos (el plan pide una hora) |
| PS-09 | Contraseñas en la tabla `users` | 6 de 6 con hash bcrypt (`$2…`) | ✅ |

**Observación de seguridad (OBS-03):** desde el commit `bc351c9`, la API se publica en todas las interfaces (`0.0.0.0:8000`) y no solo en `127.0.0.1`, porque la baliza StickS3 le informa su estado por la red local. Las rutas de la baliza exigen su token y la guía de despliegue indica que el equipo debe estar en la red separada de dispositivos. Siguen pendientes los puntos conocidos del 05-11: no hay límite de intentos de login, y desactivar un usuario no corta un token ya emitido (vence en 8 h).

## 7. Defectos encontrados el 25-11-2026

| ID | Defecto | Causa | Corrección | Verificación |
|---|---|---|---|---|
| DEF-03 | Con `docker compose --profile dev up`, la baliza simulada nunca recibía la orden (`baliza failed`) | `docker/edge/config.json` apuntaba a la IP de un StickS3 real (`bc351c9`), y la URL local tiene prioridad sobre la que entrega la API | Vuelve a `http://receptor-sim:8081` (commit `61225fe`). Para la demo con webcam y StickS3, `scripts/iniciar-cascovision-camara.ps1` deja la URL vacía y el agente usa la IP que el Stick informa a la API, en cualquier red Wi-Fi (commit `c1281af`) | Base nueva: la baliza recibe la orden en 2 a 5 ms |
| DEF-04 | En una base nueva con `CASCOVISION_SEED=1`, el agente quedaba en «vigilancia en pausa» y no detectaba nada | El seed deja `camara-01` y `zona-norte` desactivadas y con una dirección de ejemplo | `docker/db/00-migrar.sh` las activa y apunta la cámara a `rtsp-sim` solo cuando se carga la demostración. No toca el seed, que usan las pruebas, ni la producción (commit `61225fe`) | Base nueva: el agente detecta en los primeros 10 s |

## 8. Evidencias que respaldan el informe

1. Salida de consola de `test_edge_agente.py` y `test_receptor_sim.py`: 21 passed.
2. Salida de consola de `test_edge_rtsp.py`: 1 skipped por falta de FFmpeg, junto con la evidencia manual RTSP conservada por el equipo.
3. Salida de consola de `test_config.py`: 11 passed.
4. Salida de consola de los cinco módulos de API: 103 passed, 5 skipped.
5. Resultado anterior de `test_db.py`: 48 passed.
6. Resultado histórico de CI del PR #30: 323 passed, 1 skipped; workflow con PostgreSQL 16.15 y `CASCOVISION_TEST_POSTGRES=1`.
7. Código y pruebas disponibles en la rama `qa` del repositorio CascoVision.
8. Salida de consola de la suite completa del 25-11-2026: 408 passed con PostgreSQL; 347 passed y 61 skipped sin PostgreSQL.
9. Mediciones del 25-11-2026 (§5 y §6), en la carpeta `D3_evidencias_2026-11-25/` junto a este informe: los scripts (`pr03_inferencia.py`, `e2e_mediciones.py`, `seguridad_vivo.py`, `ps07_rostros.py` y `compose.pr01.yaml`), sus resultados (`e2e.json`, `ps08.json` y `salidas_consola.txt`) y una evidencia difuminada de muestra.

Los registros originales y las capturas se conservan como evidencia fuente. Este borrador no afirma que las capturas ya estén incorporadas al repositorio.

## 9. Criterios y límites de interpretación

- `passed` significa que el caso automatizado terminó satisfactoriamente en esa ejecución.
- `skipped` no equivale a `passed`: se conserva el motivo y se diferencia de una validación manual.
- Los resultados de CI no se suman a los resultados locales, porque existe solapamiento de casos.
- La aprobación de RTSP se basa en la validación manual informada por el equipo y sus evidencias conservadas; el `skip` local se mantiene registrado con transparencia.
- Este informe cubre las tareas 4.21, 4.22, 5.4 y 5.5. No declara aprobadas por extensión las pruebas de aceptación (PA) ni los casos de integración que no se listan aquí.
- Los resultados de rendimiento valen para el ambiente descrito en el §5. PR-02 queda parcial, y PS-07 y PS-08 se ejecutaron con muestras menores que las del plan; se informan con su tamaño real.

## 10. Participación y trazabilidad

Este informe se prepara para dejar trazabilidad de la ejecución y consolidación de QA en el repositorio. Las pruebas locales de esta sesión fueron ejecutadas por Benjamín Cáceres. La validación manual RTSP fue realizada por Joaquin Armijo en un segundo dispositivo; el nombre del responsable debe conservarse tal como aparezca en la evidencia original. Las mediciones de rendimiento y seguridad de la versión 0.2 (25-11-2026) las ejecutó Iahn Vera en su equipo; Benjamín Cáceres, responsable de las tareas 5.4, 5.5 y 5.9, revisa esta versión antes de subirla a `qa`.