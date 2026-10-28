-- Datos semilla: la camara, la zona y la baliza de `src/edge/config.example.json`.
--
-- Es lo minimo para que `GET /edge/config` tenga algo que entregar y el
-- reporte no salga con claves huerfanas. Idempotente: se puede volver a correr.
--
--   psql -d cascovision -f db/migrations/004_modelo_recursos.sql
--   psql -d cascovision -f db/migrations/005_indices_incidentes.sql
--   psql -d cascovision -f db/seed.sql

INSERT INTO cameras (id, name, rtsp_url, location, active) VALUES
    ('camara-01', 'Camara 01 - Entrada norte',
     'rtsp://192.168.50.10:554/stream1', 'Entrada norte', true)
ON CONFLICT (id) DO NOTHING;

-- Poligono completo del cuadro: es el valor por defecto del agente y significa
-- "se vigila todo el encuadre".
INSERT INTO zones (id, camera_id, name, polygon, suppression_s, active) VALUES
    ('zona-norte', 'camara-01', 'Zona Norte',
     '[[0.0, 0.0], [1.0, 0.0], [1.0, 1.0], [0.0, 1.0]]'::jsonb, 60, true)
ON CONFLICT (id) DO NOTHING;

-- 127.0.0.1 porque en desarrollo el receptor simulado (tarea 4.6) corre en la
-- misma maquina. En el protocolo la baliza escucha en el puerto 80, asi que de
-- aqui sale `http://127.0.0.1`. Si se usa el simulado en 8081, manda el
-- `baliza.url` del config local del agente, que es el respaldo previsto.
-- `online` arranca en false hasta que exista el firmware (tarea 4.7).
INSERT INTO beacons (id, zone_id, name, ip, duration_s, sound, message, online) VALUES
    ('baliza-01', 'zona-norte', 'Baliza Norte', '127.0.0.1', 10, 'siren',
     'USO OBLIGATORIO DE CASCO', false)
ON CONFLICT (id) DO NOTHING;
