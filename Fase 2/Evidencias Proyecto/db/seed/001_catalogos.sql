BEGIN;

-- Dispositivos ficticios y desactivados; direcciones reservadas para ejemplos.
INSERT INTO cameras (id, name, rtsp_url, location, active) VALUES
    ('camara-01', 'Cámara demo acceso', 'rtsp://192.0.2.10/demo', 'Acceso de prueba', FALSE),
    ('camara-02', 'Cámara demo bodega', 'rtsp://192.0.2.11/demo', 'Bodega de prueba', FALSE)
ON CONFLICT (id) DO NOTHING;

INSERT INTO zones (id, camera_id, name, polygon, active) VALUES
    ('zona-norte', 'camara-01', 'Zona norte demo', '[[0,0],[0.5,0],[0.5,1],[0,1]]', FALSE),
    ('zona-sur', 'camara-01', 'Zona sur demo', '[[0.5,0],[1,0],[1,1],[0.5,1]]', FALSE),
    ('zona-bodega', 'camara-02', 'Bodega demo', '[[0,0],[1,0],[1,1],[0,1]]', FALSE)
ON CONFLICT (id) DO NOTHING;

INSERT INTO beacons (id, zone_id, name, ip, sound, message) VALUES
    ('baliza-01', 'zona-norte', 'Baliza norte demo', '192.0.2.20', 'beep', 'DEMO: usar EPP'),
    ('baliza-02', 'zona-sur', 'Baliza sur demo', '192.0.2.21', 'voice', 'DEMO: usar EPP')
ON CONFLICT (id) DO NOTHING;

-- Hash bcrypt de ejemplo; cuentas deshabilitadas, sin acceso de demostración.
INSERT INTO users (id, email, full_name, password_hash, role, active) VALUES
    ('d2000000-0000-4000-8000-000000000101', 'admin@example.invalid', 'Administrador demo',
     '$2b$12$LQv3c1yqBWVHxkd0LHAkCOYz6TtxYrO5JjSHuNZ1hX.V06K9TlrUa', 'admin', FALSE),
    ('d2000000-0000-4000-8000-000000000102', 'prevencion@example.invalid', 'Prevencionista demo',
     '$2b$12$LQv3c1yqBWVHxkd0LHAkCOYz6TtxYrO5JjSHuNZ1hX.V06K9TlrUa', 'prevencionista', FALSE),
    ('d2000000-0000-4000-8000-000000000103', 'supervisor@example.invalid', 'Supervisor demo',
     '$2b$12$LQv3c1yqBWVHxkd0LHAkCOYz6TtxYrO5JjSHuNZ1hX.V06K9TlrUa', 'supervisor', FALSE)
ON CONFLICT (id) DO NOTHING;

INSERT INTO shifts (id, name, starts_at, ends_at) VALUES
    (1, 'Mañana', '06:00', '14:00'),
    (2, 'Tarde', '14:00', '22:00'),
    (3, 'Noche', '22:00', '06:00')
ON CONFLICT (id) DO NOTHING;

COMMIT;
