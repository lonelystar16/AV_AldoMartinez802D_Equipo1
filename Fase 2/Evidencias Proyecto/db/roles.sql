-- Ejecutar conectado a la base del proyecto como propietario o administrador.
-- Luego asigne una clave por rol con psql: \password cascovision
-- Repita para auditoria_admin y prevencion_mantencion.
DO $$ DECLARE schema_name TEXT := current_schema(); BEGIN
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname='cascovision') THEN CREATE ROLE cascovision LOGIN; END IF;
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname='auditoria_admin') THEN CREATE ROLE auditoria_admin LOGIN; END IF;
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname='prevencion_mantencion') THEN CREATE ROLE prevencion_mantencion LOGIN; END IF;
    IF EXISTS (
        SELECT 1 FROM pg_auth_members m JOIN pg_roles r ON r.oid IN (m.roleid, m.member)
        WHERE r.rolname IN ('cascovision', 'auditoria_admin', 'prevencion_mantencion')
    ) THEN RAISE EXCEPTION 'Revise membresias de los roles CascoVision antes de asignar GRANT'; END IF;
    EXECUTE format('GRANT CONNECT ON DATABASE %I TO cascovision, auditoria_admin, prevencion_mantencion', current_database());
    EXECUTE format('GRANT USAGE ON SCHEMA %I TO cascovision, auditoria_admin, prevencion_mantencion', schema_name);
    EXECUTE format('REVOKE ALL PRIVILEGES ON ALL TABLES IN SCHEMA %I FROM cascovision, auditoria_admin, prevencion_mantencion', schema_name);
    EXECUTE format('REVOKE ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA %I FROM cascovision, auditoria_admin, prevencion_mantencion', schema_name);
    EXECUTE format('ALTER DEFAULT PRIVILEGES IN SCHEMA %I REVOKE ALL ON TABLES FROM cascovision, auditoria_admin, prevencion_mantencion', schema_name);
    EXECUTE format('ALTER DEFAULT PRIVILEGES IN SCHEMA %I REVOKE ALL ON SEQUENCES FROM cascovision, auditoria_admin, prevencion_mantencion', schema_name);
    EXECUTE format('GRANT SELECT, INSERT, UPDATE ON incidents TO cascovision');
    EXECUTE format('GRANT SELECT ON cameras, zones, beacons, shifts TO cascovision');
    EXECUTE format('GRANT UPDATE (online, battery_pct, last_seen_at) ON beacons TO cascovision');
    -- Alta y edición de cámaras, zonas y balizas desde el dashboard (tarea 4.19).
    -- Sin DELETE: se desactivan, porque los incidentes las referencian.
    EXECUTE format('GRANT INSERT (id, name, rtsp_url, location, active), UPDATE (name, rtsp_url, location, active) ON cameras TO cascovision');
    EXECUTE format('GRANT INSERT (id, camera_id, name, polygon, suppression_s, active), UPDATE (camera_id, name, polygon, suppression_s, active) ON zones TO cascovision');
    EXECUTE format('GRANT INSERT (id, zone_id, name, ip, duration_s, sound, message), UPDATE (zone_id, name, ip, duration_s, sound, message) ON beacons TO cascovision');
    -- Login, alta de usuarios y revisión de incidentes (tarea 4.16). La API lee el
    -- perfil pero nunca password_hash: el login pasa por autenticar_usuario() (008).
    EXECUTE format('GRANT SELECT (id, email, full_name, phone, role, active, last_login_at) ON users TO cascovision');
    EXECUTE format('GRANT INSERT (id, email, full_name, phone, password_hash, role, active) ON users TO cascovision');
    EXECUTE format('GRANT EXECUTE ON FUNCTION autenticar_usuario(TEXT, TEXT) TO cascovision');
    EXECUTE format('GRANT SELECT, INSERT ON incident_events TO cascovision');
    EXECUTE format('GRANT USAGE ON SEQUENCE incident_events_id_seq TO cascovision');
    EXECUTE format('GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA %I TO auditoria_admin', schema_name);
    EXECUTE format('GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA %I TO auditoria_admin', schema_name);
    EXECUTE format('REVOKE INSERT, UPDATE, DELETE, TRUNCATE ON incident_events FROM auditoria_admin');
    EXECUTE format('REVOKE DELETE ON incidents FROM auditoria_admin');
    EXECUTE format('GRANT SELECT ON cameras, zones, beacons, incidents TO prevencion_mantencion');
    EXECUTE format('ALTER DEFAULT PRIVILEGES IN SCHEMA %I GRANT SELECT, INSERT, UPDATE ON TABLES TO auditoria_admin', schema_name);
END $$;

ALTER ROLE cascovision LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT;
ALTER ROLE auditoria_admin LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT;
ALTER ROLE prevencion_mantencion LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT;

-- Prevencion recibe lectura solo en las tablas indicadas. Si se agregan tablas,
-- conceda SELECT explícitamente después de revisar si contienen datos sensibles.
