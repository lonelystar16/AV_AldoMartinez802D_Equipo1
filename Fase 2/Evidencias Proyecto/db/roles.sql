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
    EXECUTE format('GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA %I TO auditoria_admin', schema_name);
    EXECUTE format('GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA %I TO auditoria_admin', schema_name);
    EXECUTE format('REVOKE INSERT, UPDATE, DELETE, TRUNCATE ON incident_events FROM auditoria_admin');
    EXECUTE format('REVOKE DELETE ON incidents FROM auditoria_admin');
    EXECUTE format('GRANT SELECT ON cameras, zones, beacons, incidents TO prevencion_mantencion');
    EXECUTE format('ALTER DEFAULT PRIVILEGES IN SCHEMA %I GRANT SELECT, INSERT, UPDATE ON TABLES TO cascovision', schema_name);
    EXECUTE format('ALTER DEFAULT PRIVILEGES IN SCHEMA %I GRANT SELECT, INSERT, UPDATE ON TABLES TO auditoria_admin', schema_name);
END $$;

ALTER ROLE cascovision LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT;
ALTER ROLE auditoria_admin LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT;
ALTER ROLE prevencion_mantencion LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT;

-- Prevencion recibe lectura solo en las tablas indicadas. Si se agregan tablas,
-- conceda SELECT explícitamente después de revisar si contienen datos sensibles.
