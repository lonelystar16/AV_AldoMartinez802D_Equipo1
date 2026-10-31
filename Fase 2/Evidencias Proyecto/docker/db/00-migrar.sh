#!/bin/sh
# Crea el esquema de CascoVision la primera vez que arranca la base (volumen
# vacio). La imagen de PostgreSQL ejecuta este script una sola vez, con el
# usuario y la base de POSTGRES_USER y POSTGRES_DB.
#
# El orden es el de db/seed/README.md. No basta con recorrer db/migrations/ en
# orden alfabetico: 004_modelo_recursos.sql y 005_indices_incidentes.sql son
# alternativas anteriores que chocan con 004_modelo_completo.sql.
#
# CASCOVISION_SEED=1 carga los catalogos y los incidentes de demostracion
# (camara-01, zona-norte, baliza-01; todo desactivado). No usar en produccion.
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
echo "[migrar] listo"
