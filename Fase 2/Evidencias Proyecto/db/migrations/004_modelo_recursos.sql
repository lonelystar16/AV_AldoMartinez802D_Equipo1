-- Recursos que el dashboard administra y que la API entrega al agente Edge:
-- camaras, zonas de riesgo y balizas.
--
-- Se separa de las migraciones 001-003 porque esas tocan solo `incidents` y
-- ya estan en uso. Las claves foraneas de `incidents` hacia estas tablas NO
-- se crean aqui ni en 005: exigen que existan las camaras y zonas de los
-- incidentes ya registrados, y un arranque que falla por datos viejos es peor
-- que un arranque sin integridad referencial. Van en una migracion aparte
-- cuando exista la semilla (db/seed.sql).
--
-- Numeracion: MODELO_DATOS.md preveia "003_modelo_completo.sql", pero el 003
-- quedo ocupado por el ciclo de vida del episodio. Corregido en ese documento.

CREATE TABLE cameras (
    id TEXT PRIMARY KEY CHECK (length(trim(id)) > 0),
    name TEXT NOT NULL CHECK (length(trim(name)) > 0),
    -- Sin credenciales: la contrasena de la camara vive en una variable de
    -- entorno, no en la base de datos.
    rtsp_url TEXT NOT NULL CHECK (length(trim(rtsp_url)) > 0),
    location TEXT,
    active BOOLEAN NOT NULL DEFAULT true,
    last_frame_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE zones (
    id TEXT PRIMARY KEY CHECK (length(trim(id)) > 0),
    camera_id TEXT NOT NULL REFERENCES cameras(id) ON DELETE CASCADE,
    name TEXT NOT NULL CHECK (length(trim(name)) > 0),
    -- Poligono en coordenadas relativas (0..1): el mismo formato que usa
    -- `zonas.py` y el `poligono` del JSON del agente, sin conversion.
    polygon JSONB NOT NULL CHECK (
        jsonb_typeof(polygon) = 'array'
        AND jsonb_array_length(polygon) >= 3
    ),
    suppression_s INTEGER NOT NULL DEFAULT 60
        CHECK (suppression_s BETWEEN 10 AND 600),
    active BOOLEAN NOT NULL DEFAULT true
);

CREATE TABLE beacons (
    id TEXT PRIMARY KEY CHECK (length(trim(id)) > 0),
    -- 1 a 0..1: una zona tiene a lo mas una baliza. SET NULL porque
    -- desinstalar la baliza no debe borrar la zona que vigila.
    zone_id TEXT UNIQUE REFERENCES zones(id) ON DELETE SET NULL,
    name TEXT NOT NULL CHECK (length(trim(name)) > 0),
    ip INET NOT NULL UNIQUE,
    duration_s INTEGER NOT NULL DEFAULT 10 CHECK (duration_s BETWEEN 1 AND 30),
    sound TEXT NOT NULL DEFAULT 'siren' CHECK (sound IN ('siren', 'voice', 'beep')),
    message VARCHAR(40),
    -- Estado segun el heartbeat (RNF-14). Arranca en false: mientras no exista
    -- el firmware (tarea 4.7) el reporte muestra `skipped_offline`, que es la
    -- verdad y no un hueco en el datos.
    online BOOLEAN NOT NULL DEFAULT false,
    battery_pct INTEGER CHECK (battery_pct BETWEEN 0 AND 100),
    last_seen_at TIMESTAMPTZ
);
