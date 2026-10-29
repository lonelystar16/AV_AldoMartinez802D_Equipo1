-- Indices de reporteria sobre incidents.
--
-- Las claves foraneas hacia cameras y zones NO se agregan todavia: exigen que
-- existan las camaras y zonas de los incidentes ya registrados (datos semilla
-- de la tarea 4.9). Mientras tanto la API valida camera_id y zone_id en el
-- modelo, y el reporte los une por igualdad de texto. Van en una migracion
-- aparte cuando exista la semilla.
--
-- `002` ya crea incidents_detected_at_idx, que cubre el historial simple.

-- Filtro por zona del reporte y del dashboard.
CREATE INDEX incidents_zone_detected_at_idx
    ON incidents (zone_id, detected_at DESC);

-- Mismo filtro por camara.
CREATE INDEX incidents_camera_detected_at_idx
    ON incidents (camera_id, detected_at DESC);

-- Los incidentes abiertos son la consulta del dashboard; los cerrados, que son
-- la mayoria, no se tocan.
CREATE INDEX incidents_abiertos_idx
    ON incidents (status) WHERE status = 'open';
