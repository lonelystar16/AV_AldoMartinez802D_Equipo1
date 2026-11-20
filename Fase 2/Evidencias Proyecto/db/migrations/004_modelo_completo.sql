BEGIN;

-- CHECK no admite subconsultas: se valida cada punto antes de convertirlo.
CREATE OR REPLACE FUNCTION valid_zone_polygon(points JSONB) RETURNS BOOLEAN
LANGUAGE plpgsql IMMUTABLE STRICT AS $$
DECLARE
    point JSONB;
BEGIN
    IF jsonb_typeof(points) <> 'array' THEN
        RETURN FALSE;
    END IF;
    IF jsonb_array_length(points) < 3 THEN
        RETURN FALSE;
    END IF;
    FOR point IN SELECT value FROM jsonb_array_elements(points) LOOP
        IF jsonb_typeof(point) <> 'array' THEN
            RETURN FALSE;
        END IF;
        IF jsonb_array_length(point) <> 2 THEN
            RETURN FALSE;
        END IF;
        IF jsonb_typeof(point->0) <> 'number'
            OR jsonb_typeof(point->1) <> 'number' THEN
            RETURN FALSE;
        END IF;
        IF (point->>0)::NUMERIC NOT BETWEEN 0 AND 1
            OR (point->>1)::NUMERIC NOT BETWEEN 0 AND 1 THEN
            RETURN FALSE;
        END IF;
    END LOOP;
    RETURN TRUE;
END;
$$;

CREATE TABLE IF NOT EXISTS cameras (
    id TEXT PRIMARY KEY CHECK (length(trim(id)) > 0),
    name TEXT NOT NULL CHECK (length(trim(name)) > 0),
    rtsp_url TEXT NOT NULL CHECK (
        rtsp_url ~ '^rtsps?://[^/@[:space:]]+(/[^[:space:]]*)?$'
    ),
    location TEXT,
    active BOOLEAN NOT NULL DEFAULT TRUE,
    last_frame_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS zones (
    id TEXT PRIMARY KEY CHECK (length(trim(id)) > 0),
    camera_id TEXT NOT NULL REFERENCES cameras(id) ON DELETE CASCADE,
    name TEXT NOT NULL CHECK (length(trim(name)) > 0),
    polygon JSONB NOT NULL CHECK (valid_zone_polygon(polygon)),
    suppression_s INTEGER NOT NULL DEFAULT 60 CHECK (suppression_s BETWEEN 10 AND 600),
    active BOOLEAN NOT NULL DEFAULT TRUE
);

CREATE TABLE IF NOT EXISTS beacons (
    id TEXT PRIMARY KEY CHECK (length(trim(id)) > 0),
    zone_id TEXT UNIQUE REFERENCES zones(id) ON DELETE SET NULL,
    name TEXT NOT NULL CHECK (length(trim(name)) > 0),
    ip INET NOT NULL UNIQUE,
    duration_s INTEGER NOT NULL DEFAULT 10 CHECK (duration_s BETWEEN 1 AND 30),
    sound TEXT NOT NULL DEFAULT 'siren' CHECK (sound IN ('siren', 'voice', 'beep')),
    message VARCHAR(40),
    online BOOLEAN NOT NULL DEFAULT FALSE,
    battery_pct INTEGER CHECK (battery_pct BETWEEN 0 AND 100),
    last_seen_at TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS users (
    id UUID PRIMARY KEY,
    email TEXT NOT NULL UNIQUE CHECK (
        email = lower(email) AND email ~ '^[^[:space:]@]+@[^[:space:]@]+[.][^[:space:]@]+$'
    ),
    full_name TEXT NOT NULL CHECK (length(trim(full_name)) > 0),
    phone TEXT CHECK (phone ~ '^\+[1-9][0-9]{1,14}$'),
    password_hash TEXT NOT NULL CHECK (
        password_hash ~ '^\$2[aby]\$[0-9]{2}\$[./A-Za-z0-9]{53}$'
    ),
    role TEXT NOT NULL CHECK (role IN ('admin', 'prevencionista', 'supervisor')),
    active BOOLEAN NOT NULL DEFAULT TRUE,
    last_login_at TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS incident_events (
    id BIGSERIAL PRIMARY KEY,
    incident_id UUID NOT NULL REFERENCES incidents(id) ON DELETE CASCADE,
    user_id UUID NOT NULL REFERENCES users(id),
    from_status TEXT NOT NULL CHECK (
        from_status IN ('open', 'reviewed', 'closed', 'false_positive')
    ),
    to_status TEXT NOT NULL CHECK (
        to_status IN ('open', 'reviewed', 'closed', 'false_positive')
    ),
    comment TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS notifications (
    id BIGSERIAL PRIMARY KEY,
    incident_id UUID NOT NULL REFERENCES incidents(id) ON DELETE CASCADE,
    user_id UUID NOT NULL REFERENCES users(id),
    channel TEXT NOT NULL CHECK (channel IN ('sms', 'email')),
    status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'sent', 'failed')),
    attempts INTEGER NOT NULL DEFAULT 0 CHECK (attempts >= 0),
    sent_at TIMESTAMPTZ,
    error TEXT
);

CREATE TABLE IF NOT EXISTS shifts (
    id SMALLINT PRIMARY KEY,
    name TEXT NOT NULL UNIQUE CHECK (length(trim(name)) > 0),
    starts_at TIME NOT NULL,
    ends_at TIME NOT NULL CHECK (ends_at <> starts_at)
);

COMMIT;
