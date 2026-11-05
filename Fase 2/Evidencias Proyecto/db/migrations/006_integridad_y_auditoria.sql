BEGIN;

ALTER TABLE incidents ADD COLUMN IF NOT EXISTS face_blurred BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE incidents ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ NOT NULL DEFAULT now();
ALTER TABLE notifications ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ NOT NULL DEFAULT now();
ALTER TABLE notifications ADD COLUMN IF NOT EXISTS destination TEXT;

UPDATE notifications n
SET destination = CASE n.channel WHEN 'sms' THEN u.phone ELSE u.email END
FROM users u
WHERE u.id = n.user_id AND n.destination IS NULL;

UPDATE incidents
SET violation_types = array_append(COALESCE(violation_types, ARRAY[]::TEXT[]), violation_type)
WHERE violation_types IS NULL OR NOT (violation_type = ANY(violation_types));

DO $$ BEGIN
    IF EXISTS (SELECT 1 FROM notifications WHERE destination IS NULL OR btrim(destination) = '') THEN
        RAISE EXCEPTION 'Hay notificaciones sin destino; complete el destino real antes de aplicar 006';
    END IF;
    IF EXISTS (
        SELECT 1 FROM incidents
        WHERE violation_types IS NULL OR NOT (violation_type = ANY(violation_types))
           OR (event = 'fin' AND ended_at IS NULL)
           OR (started_at IS NOT NULL AND last_ping_at IS NOT NULL AND started_at > last_ping_at)
    ) THEN
        RAISE EXCEPTION 'Hay incidentes que incumplen las nuevas reglas de consistencia';
    END IF;
    IF EXISTS (SELECT 1 FROM incident_events WHERE from_status = to_status
        OR (to_status IN ('closed', 'false_positive') AND NULLIF(btrim(comment), '') IS NULL)) THEN
        RAISE EXCEPTION 'Hay eventos de incidente incompatibles con las nuevas reglas';
    END IF;
    IF EXISTS (
        SELECT 1 FROM notifications GROUP BY incident_id, user_id, channel HAVING count(*) > 1
    ) THEN
        RAISE EXCEPTION 'Hay notificaciones duplicadas; deduplique conservando su historial antes de aplicar 006';
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conrelid='zones'::regclass AND conname='zones_camera_id_id_key') THEN
        ALTER TABLE zones ADD CONSTRAINT zones_camera_id_id_key UNIQUE (camera_id, id);
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conrelid='incidents'::regclass AND conname='incidents_camera_zone_fkey') THEN
        IF EXISTS (
            SELECT 1 FROM incidents i JOIN zones z ON z.id=i.zone_id
            WHERE z.camera_id <> i.camera_id
        ) THEN RAISE EXCEPTION 'Hay incidentes cuya zona pertenece a otra camara'; END IF;
        ALTER TABLE incidents ADD CONSTRAINT incidents_camera_zone_fkey
            FOREIGN KEY (camera_id, zone_id) REFERENCES zones(camera_id, id);
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conrelid='incidents'::regclass AND conname='incidents_violation_type_in_array') THEN
        ALTER TABLE incidents ADD CONSTRAINT incidents_violation_type_in_array
            CHECK (violation_types IS NOT NULL AND violation_type = ANY(violation_types));
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conrelid='incidents'::regclass AND conname='incidents_fin_requires_ended_at') THEN
        ALTER TABLE incidents ADD CONSTRAINT incidents_fin_requires_ended_at
            CHECK (event <> 'fin' OR ended_at IS NOT NULL);
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conrelid='incidents'::regclass AND conname='incidents_ping_after_start') THEN
        ALTER TABLE incidents ADD CONSTRAINT incidents_ping_after_start
            CHECK (started_at IS NULL OR last_ping_at IS NULL OR started_at <= last_ping_at);
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conrelid='incident_events'::regclass AND conname='incident_events_status_changed') THEN
        ALTER TABLE incident_events ADD CONSTRAINT incident_events_status_changed CHECK (from_status <> to_status);
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conrelid='incident_events'::regclass AND conname='incident_events_close_comment_required') THEN
        ALTER TABLE incident_events ADD CONSTRAINT incident_events_close_comment_required
            CHECK (to_status NOT IN ('closed', 'false_positive') OR NULLIF(btrim(comment), '') IS NOT NULL);
    END IF;
END $$;

ALTER TABLE notifications ALTER COLUMN destination SET NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS notifications_incident_user_channel_idx
    ON notifications (incident_id, user_id, channel);

CREATE OR REPLACE FUNCTION set_incident_updated_at() RETURNS trigger
LANGUAGE plpgsql AS $$ BEGIN NEW.updated_at = now(); RETURN NEW; END $$;
DROP TRIGGER IF EXISTS incidents_set_updated_at ON incidents;
CREATE TRIGGER incidents_set_updated_at BEFORE UPDATE ON incidents
FOR EACH ROW EXECUTE FUNCTION set_incident_updated_at();

COMMIT;
