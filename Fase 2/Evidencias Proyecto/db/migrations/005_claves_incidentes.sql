BEGIN;

-- No se inventan catálogos ni se eliminan incidentes para hacer pasar las FK.
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM incidents i
        LEFT JOIN cameras c ON c.id = i.camera_id
        LEFT JOIN zones z ON z.id = i.zone_id
        WHERE c.id IS NULL OR z.id IS NULL
    ) THEN
        RAISE EXCEPTION 'Hay incidentes con cámaras o zonas inexistentes'
            USING HINT = 'Revise la consulta de huérfanos en db/seed/README.md y cargue los catálogos reales antes de aplicar la 005.';
    END IF;

    -- ADD CONSTRAINT no admite IF NOT EXISTS; se consulta la tabla concreta.
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conrelid = 'incidents'::regclass AND conname = 'incidents_camera_id_fkey'
    ) THEN
        ALTER TABLE incidents ADD CONSTRAINT incidents_camera_id_fkey
            FOREIGN KEY (camera_id) REFERENCES cameras(id);
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conrelid = 'incidents'::regclass AND conname = 'incidents_zone_id_fkey'
    ) THEN
        ALTER TABLE incidents ADD CONSTRAINT incidents_zone_id_fkey
            FOREIGN KEY (zone_id) REFERENCES zones(id);
    END IF;
END;
$$;

-- El índice general por detected_at ya existe desde la migración 002.
CREATE INDEX IF NOT EXISTS incidents_zone_detected_at_idx ON incidents (zone_id, detected_at DESC);
CREATE INDEX IF NOT EXISTS incidents_open_idx ON incidents (status) WHERE status = 'open';
CREATE INDEX IF NOT EXISTS incident_events_incident_created_at_idx ON incident_events (incident_id, created_at);
CREATE INDEX IF NOT EXISTS notifications_pending_idx ON notifications (status) WHERE status = 'pending';

COMMIT;
