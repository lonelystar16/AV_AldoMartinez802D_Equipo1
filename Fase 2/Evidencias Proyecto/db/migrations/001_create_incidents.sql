CREATE TABLE incidents (
    id UUID PRIMARY KEY,
    camera_id TEXT NOT NULL CHECK (length(trim(camera_id)) > 0),
    zone_id TEXT NOT NULL CHECK (length(trim(zone_id)) > 0),
    detected_at TIMESTAMPTZ NOT NULL,
    violation_type TEXT NOT NULL CHECK (
        violation_type IN ('missing_helmet', 'missing_reflective_vest')
    ),
    confidence DOUBLE PRECISION NOT NULL CHECK (confidence BETWEEN 0 AND 1),
    evidence_path TEXT NOT NULL CHECK (
        length(trim(evidence_path)) > 0
        AND evidence_path NOT LIKE '/%'
        AND evidence_path <> '..'
        AND evidence_path NOT LIKE '../%'
        AND evidence_path NOT LIKE '%/../%'
        AND evidence_path NOT LIKE '%/..'
        AND position(chr(92) IN evidence_path) = 0
        AND position(':' IN evidence_path) = 0
    ),
    beacon_alert_status TEXT NOT NULL CHECK (
        beacon_alert_status IN ('alerted', 'failed', 'skipped_offline')
    ),
    beacon_alert_latency_ms INTEGER CHECK (beacon_alert_latency_ms >= 0),
    status TEXT NOT NULL DEFAULT 'open' CHECK (
        status IN ('open', 'reviewed', 'closed', 'false_positive')
    ),
    created_at TIMESTAMPTZ NOT NULL
);
