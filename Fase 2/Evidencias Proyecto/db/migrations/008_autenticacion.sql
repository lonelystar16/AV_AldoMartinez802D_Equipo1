-- Inicio de sesion del dashboard (RF-17, tarea 4.16).
--
-- La clave se compara con crypt() de pgcrypto contra el hash bcrypt de users.
-- pgcrypto va en public y se llama como public.crypt(), para que funcione con
-- cualquier search_path.
--
-- autenticar_usuario() es SECURITY DEFINER: el rol de la API (db/roles.sql) no
-- puede leer password_hash, solo ejecutar esta funcion, que devuelve el perfil
-- si la clave coincide y registra last_login_at. Su search_path queda fijo en el
-- esquema donde se crea, para que nadie la desvie con tablas propias.
-- Repetible.
CREATE EXTENSION IF NOT EXISTS pgcrypto WITH SCHEMA public;

DO $migracion$ BEGIN
    EXECUTE format($f$
        CREATE OR REPLACE FUNCTION autenticar_usuario(p_email TEXT, p_clave TEXT)
        RETURNS TABLE (id UUID, email TEXT, full_name TEXT, phone TEXT, role TEXT,
                       active BOOLEAN, last_login_at TIMESTAMPTZ)
        LANGUAGE sql SECURITY DEFINER SET search_path = %I, public AS $cuerpo$
            UPDATE users u SET last_login_at = now()
            WHERE u.email = lower(p_email) AND u.active
              AND u.password_hash = public.crypt(p_clave, u.password_hash)
            RETURNING u.id, u.email, u.full_name, u.phone, u.role, u.active, u.last_login_at
        $cuerpo$
    $f$, current_schema());
END $migracion$;

REVOKE ALL ON FUNCTION autenticar_usuario(TEXT, TEXT) FROM PUBLIC;
