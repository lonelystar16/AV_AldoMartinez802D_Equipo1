# CascoVision — Informe de resultados de pruebas

- **Versión:** borrador 0.1
- **Fecha de consolidación:** 11-11-2026
- **Rama de referencia:** `qa`
- **Commit de referencia revisado:** `3899640` (`3899640278b6d1199609a13f60bb91f19d6c4a5d`)
- **Proyecto:** PTY4614 — Capstone, Ingeniería en Informática, Duoc UC
- **Equipo:** Benjamín Cáceres, Iahn Vera, Joaquín Armijo y Fernando Muñoz

## 1. Objetivo y alcance

Este informe consolida los resultados disponibles para el cierre de las tareas internas de QA **4.21 — API y base de datos** y **4.22 — Agente Edge y receptor simulado**. Se consideran ejecuciones locales, la ejecución de integración continua (CI) ya realizada y la validación manual de RTSP informada por el equipo.

El informe complementa el Plan de Pruebas D3 publicado en el repositorio. No reemplaza la evidencia original de consola, los registros de CI ni los respaldos visuales de las pruebas manuales.

## 2. Resumen ejecutivo

| Tarea | Resultado consolidado | Estado propuesto |
|---|---|---|
| 4.21 — API y base de datos | 48 pruebas PostgreSQL aprobadas en ejecución local anterior; 11 pruebas de configuración aprobadas; 103 pruebas de API aprobadas y 5 omitidas localmente por requerir PostgreSQL. La CI histórica ejecutó la suite con PostgreSQL configurado: 323 aprobadas y 1 omitida. | **Validada** |
| 4.22 — Agente Edge y receptor simulado | 21 pruebas automatizadas aprobadas. La prueba automatizada RTSP se omitió en el equipo local por ausencia de FFmpeg; el equipo informa que la lectura y reconexión RTSP se validaron manualmente en otro dispositivo y que conserva sus evidencias. | **Aprobada mediante validación combinada** |

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

## 5. Evidencias que respaldan el informe

1. Salida de consola de `test_edge_agente.py` y `test_receptor_sim.py`: 21 passed.
2. Salida de consola de `test_edge_rtsp.py`: 1 skipped por falta de FFmpeg, junto con la evidencia manual RTSP conservada por el equipo.
3. Salida de consola de `test_config.py`: 11 passed.
4. Salida de consola de los cinco módulos de API: 103 passed, 5 skipped.
5. Resultado anterior de `test_db.py`: 48 passed.
6. Resultado histórico de CI del PR #30: 323 passed, 1 skipped; workflow con PostgreSQL 16.15 y `CASCOVISION_TEST_POSTGRES=1`.
7. Código y pruebas disponibles en la rama `qa` del repositorio CascoVision.

Los registros originales y las capturas se conservan como evidencia fuente. Este borrador no afirma que las capturas ya estén incorporadas al repositorio.

## 6. Criterios y límites de interpretación

- `passed` significa que el caso automatizado terminó satisfactoriamente en esa ejecución.
- `skipped` no equivale a `passed`: se conserva el motivo y se diferencia de una validación manual.
- Los resultados de CI no se suman a los resultados locales, porque existe solapamiento de casos.
- La aprobación de RTSP se basa en la validación manual informada por el equipo y sus evidencias conservadas; el `skip` local se mantiene registrado con transparencia.
- Este informe cubre las tareas 4.21 y 4.22. No declara aprobadas por extensión otras pruebas de integración, rendimiento, seguridad o aceptación que no forman parte de este alcance.

## 7. Participación y trazabilidad

Este informe se prepara para dejar trazabilidad de la ejecución y consolidación de QA en el repositorio. Las pruebas locales de esta sesión fueron ejecutadas por Benjamín Cáceres. La validación manual RTSP fue realizada por Joaquin Armijo en un segundo dispositivo; el nombre del responsable debe conservarse tal como aparezca en la evidencia original.