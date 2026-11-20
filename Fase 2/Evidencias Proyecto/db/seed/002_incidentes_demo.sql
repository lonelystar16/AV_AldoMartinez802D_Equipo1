BEGIN;

-- UUID y fechas fijos permiten repetir la carga sin duplicar los casos.
-- Las rutas son referencias ficticias: este seed no genera imágenes.
INSERT INTO incidents (
    id, camera_id, zone_id, detected_at, violation_type, violation_types,
    confidence, evidence_path, beacon_alert_status, beacon_alert_latency_ms,
    person_track_id, status, created_at, episode_id, event, ping_count,
    started_at, last_ping_at, ended_at
) VALUES
    ('d2000000-0000-4000-8000-000000001001', 'camara-01', 'zona-norte',
     '2026-01-15T10:00:00Z', 'missing_helmet', ARRAY['missing_helmet'],
     0.94, 'demo/2026/01/15/incidente-1001.jpg', 'alerted', 820,
     7, 'open', '2026-01-15T10:00:01Z', 'd2000000-0000-4000-8000-000000002001',
     'inicio', 0, '2026-01-15T10:00:00Z', NULL, NULL),
    ('d2000000-0000-4000-8000-000000001002', 'camara-01', 'zona-sur',
     '2026-01-15T18:00:00Z', 'missing_reflective_vest', ARRAY['missing_reflective_vest'],
     0.88, 'demo/2026/01/15/incidente-1002.jpg', 'failed', 1500,
     8, 'reviewed', '2026-01-15T18:00:01Z', 'd2000000-0000-4000-8000-000000002002',
     'ping', 2, '2026-01-15T18:00:00Z', '2026-01-15T18:02:00Z', NULL),
    ('d2000000-0000-4000-8000-000000001003', 'camara-01', 'zona-norte',
     '2026-01-16T02:00:00Z', 'missing_helmet', ARRAY['missing_helmet', 'missing_reflective_vest'],
     0.97, 'demo/2026/01/16/incidente-1003.jpg', 'skipped_offline', NULL,
     9, 'closed', '2026-01-16T02:00:01Z', 'd2000000-0000-4000-8000-000000002003',
     'fin', 1, '2026-01-16T02:00:00Z', '2026-01-16T02:01:00Z', '2026-01-16T02:05:00Z'),
    ('d2000000-0000-4000-8000-000000001004', 'camara-02', 'zona-bodega',
     '2026-01-16T12:00:00Z', 'missing_reflective_vest', ARRAY['missing_reflective_vest'],
     0.65, 'demo/2026/01/16/incidente-1004.jpg', 'skipped_offline', NULL,
     10, 'false_positive', '2026-01-16T12:00:01Z', 'd2000000-0000-4000-8000-000000002004',
     'fin', 0, '2026-01-16T12:00:00Z', NULL, '2026-01-16T12:02:00Z')
ON CONFLICT (id) DO NOTHING;

COMMIT;
