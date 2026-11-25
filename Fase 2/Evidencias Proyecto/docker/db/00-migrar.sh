#!/bin/sh
# Crea el esquema de CascoVision la primera vez que arranca la base (volumen
# vacio). La imagen de PostgreSQL ejecuta este script una sola vez, con el
# usuario y la base de POSTGRES_USER y POSTGRES_DB.
#
# El orden es el de db/seed/README.md: los catalogos demo van entre la 004 y
# la 005, porque la 005 agrega las FK de incidents hacia cameras y zones.
#
# CASCOVISION_SEED=1 carga los catalogos y los incidentes de demostracion
# (camara-01, zona-norte, baliza-01) y activa la camara y la zona de la demo
# (ver el final). No usar en produccion.
set -eu

aplicar() {
    echo "[migrar] $1"
    psql -X -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" -f "/migraciones/$1"
}

aplicar migrations/001_create_incidents.sql
aplicar migrations/002_add_tracking_fields.sql
aplicar migrations/003_add_episode_lifecycle.sql
aplicar migrations/004_modelo_completo.sql
[ "${CASCOVISION_SEED:-0}" = "1" ] && aplicar seed/001_catalogos.sql
aplicar migrations/005_claves_incidentes.sql
[ "${CASCOVISION_SEED:-0}" = "1" ] && aplicar seed/002_incidentes_demo.sql
aplicar migrations/006_integridad_y_auditoria.sql
aplicar migrations/007_vistas_reporteria.sql
aplicar migrations/008_autenticacion.sql

# Con la demostracion, camara-01 y zona-norte quedan activas y apuntan a la
# camara simulada del perfil dev: el seed las deja desactivadas y con una
# direccion de ejemplo, y el agente no vigila una zona desactivada.
if [ "${CASCOVISION_SEED:-0}" = "1" ]; then
    echo "[migrar] demostracion: activa camara-01 y zona-norte (rtsp-sim)"
    psql -X -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<'SQL'
UPDATE cameras SET rtsp_url = 'rtsp://rtsp-sim:8554/camara-01', active = TRUE WHERE id = 'camara-01';
UPDATE zones SET polygon = '[[0,0],[1,0],[1,1],[0,1]]', active = TRUE WHERE id = 'zona-norte';
SQL
fi

# Primer administrador del dashboard, desde el .env (CASCOVISION_ADMIN_*). Los
# valores pasan como variables de psql, no se pegan en el SQL.
if [ -n "${CASCOVISION_ADMIN_EMAIL:-}" ] && [ -n "${CASCOVISION_ADMIN_PASSWORD:-}" ]; then
    if [ "${#CASCOVISION_ADMIN_PASSWORD}" -lt 12 ]; then
        echo "[migrar] CASCOVISION_ADMIN_PASSWORD necesita 12 caracteres o mas" >&2
        exit 1
    fi
    echo "[migrar] administrador inicial"
    psql -X -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" \
        -v correo="$CASCOVISION_ADMIN_EMAIL" -v clave="$CASCOVISION_ADMIN_PASSWORD" <<'SQL'
INSERT INTO users (id, email, full_name, password_hash, role, active)
VALUES (gen_random_uuid(), lower(:'correo'), 'Administrador', public.crypt(:'clave', public.gen_salt('bf', 12)), 'admin', TRUE)
ON CONFLICT (email) DO NOTHING;
SQL
fi
echo "[migrar] listo"
