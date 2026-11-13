-- Evidencia de integracion Baliza -> Agente Edge -> API -> PostgreSQL.
-- Solo lectura: estas consultas no insertan ni modifican datos.
-- Ejecutar desde la raiz del repositorio con:
-- psql -h localhost -p 5432 -U cascovision -d cascovision -f "Fase 2/Evidencias Proyecto/db/evidencia_integracion_baliza_api.sql"
--
-- beacon_alert_status='alerted' es la respuesta que el agente recibio de la
-- baliza y envio a la API junto con el incidente. last_seen_at refleja el
-- heartbeat de la baliza recibido por la API.

-- 1. Base de datos y usuario que ejecutan la evidencia.
SELECT current_database() AS base_datos,
       current_user AS usuario,
       clock_timestamp() AS consultado_en;

-- 2. Baliza asociada a la zona y ultimo heartbeat reportado a la API.
SELECT b.id AS baliza_id,
       b.zone_id AS zona_id,
       b.name AS baliza,
       b.online AS en_linea,
       b.last_seen_at AS ultimo_heartbeat
FROM beacons AS b
WHERE b.zone_id = 'zona-norte';

-- 3. Resumen de incidentes que la API persistio para esta camara y zona.
SELECT camera_id AS camara_id,
       zone_id AS zona_id,
       COUNT(*) AS incidentes_guardados,
       COUNT(*) FILTER (WHERE beacon_alert_status = 'alerted') AS alertas_confirmadas_por_baliza,
       COUNT(*) FILTER (WHERE beacon_alert_status = 'failed') AS alertas_fallidas,
       COUNT(*) FILTER (WHERE beacon_alert_status = 'skipped_offline') AS alertas_omitidas_por_desconexion
FROM incidents
WHERE camera_id = 'camara-01'
  AND zone_id = 'zona-norte'
GROUP BY camera_id, zone_id;

-- 4. Detalle de los avisos recientes recibidos por la API y guardados en PostgreSQL.
SELECT detected_at AS detectado_en,
       event AS evento,
       camera_id AS camara_id,
       zone_id AS zona_id,
       person_track_id AS persona,
       violation_type AS infraccion_principal,
       violation_types AS infracciones,
       confidence AS confianza,
       beacon_alert_status AS resultado_baliza,
       beacon_alert_latency_ms AS latencia_baliza_ms,
       status AS estado_registro
FROM incidents
WHERE camera_id = 'camara-01'
  AND zone_id = 'zona-norte'
ORDER BY detected_at DESC
LIMIT 20;
