"""Integración SQL real; se omite sin CASCOVISION_TEST_POSTGRES=1."""

from pathlib import Path

import pytest

PROJECT = Path(__file__).resolve().parents[1]
CATALOGS = PROJECT / "db/seed/001_catalogos.sql"
INCIDENTS = PROJECT / "db/seed/002_incidentes_demo.sql"
FOREIGN_KEYS = PROJECT / "db/migrations/005_claves_incidentes.sql"


@pytest.fixture
def seeded_db(postgres_db):
    postgres_db.execute(INCIDENTS.read_text(encoding="utf-8"))
    return postgres_db


def test_seed_repetible_y_conserva_cambios(seeded_db):
    db = seeded_db
    db.execute("UPDATE cameras SET name = 'Nombre conservado' WHERE id = 'camara-01'")
    db.execute("UPDATE incidents SET status = 'reviewed' WHERE person_track_id = 7")
    db.execute(CATALOGS.read_text(encoding="utf-8"))
    db.execute(INCIDENTS.read_text(encoding="utf-8"))

    assert db.execute("SELECT count(*) FROM cameras").fetchone()[0] == 2
    assert db.execute("SELECT count(*) FROM zones").fetchone()[0] == 3
    assert db.execute("SELECT count(*) FROM beacons").fetchone()[0] == 2
    assert db.execute("SELECT count(*) FROM users").fetchone()[0] == 3
    assert db.execute("SELECT count(*) FROM shifts").fetchone()[0] == 3
    assert db.execute("SELECT count(*) FROM incidents").fetchone()[0] == 4
    assert db.execute("SELECT name FROM cameras WHERE id = 'camara-01'").fetchone()[0] == 'Nombre conservado'
    assert db.execute("SELECT status FROM incidents WHERE person_track_id = 7").fetchone()[0] == 'reviewed'
    assert db.execute("SELECT count(*) FROM cameras WHERE active").fetchone()[0] == 0
    assert db.execute("SELECT count(*) FROM users WHERE active").fetchone()[0] == 0
    assert db.execute("SELECT count(*) FROM beacons WHERE online").fetchone()[0] == 0


def test_repetir_migraciones_conserva_datos_y_objetos(seeded_db):
    from psycopg import sql

    db = seeded_db
    db.execute("UPDATE incidents SET ping_count = 5 WHERE person_track_id = 7")
    tables = ('cameras', 'zones', 'beacons', 'users', 'shifts', 'incidents',
              'incident_events', 'notifications')
    data = {
        table: db.execute(sql.SQL("SELECT * FROM {} ORDER BY id").format(sql.Identifier(table))).fetchall()
        for table in tables
    }
    objects_sql = (
        "SELECT relname, oid FROM pg_class WHERE relnamespace = current_schema()::regnamespace "
        "ORDER BY relname"
    )
    constraints_sql = (
        "SELECT conname, oid FROM pg_constraint WHERE connamespace = current_schema()::regnamespace "
        "ORDER BY oid"
    )
    objects = db.execute(objects_sql).fetchall()
    constraints = db.execute(constraints_sql).fetchall()
    for _ in range(2):
        for path in sorted((PROJECT / 'db/migrations').glob('*.sql')):
            db.execute(path.read_text(encoding='utf-8'))
        db.execute(CATALOGS.read_text(encoding='utf-8'))
        db.execute(INCIDENTS.read_text(encoding='utf-8'))

    for table in tables:
        assert db.execute(sql.SQL("SELECT * FROM {} ORDER BY id").format(sql.Identifier(table))).fetchall() == data[table]
    assert db.execute(objects_sql).fetchall() == objects
    assert db.execute(constraints_sql).fetchall() == constraints


def test_004_reemplaza_funcion_existente(postgres_db):
    db = postgres_db
    db.execute(
        "CREATE OR REPLACE FUNCTION valid_zone_polygon(points JSONB) RETURNS BOOLEAN "
        "LANGUAGE sql IMMUTABLE STRICT AS 'SELECT TRUE'"
    )
    db.execute((PROJECT / 'db/migrations/004_modelo_completo.sql').read_text(encoding='utf-8'))
    assert db.execute("SELECT valid_zone_polygon('[]')").fetchone()[0] is False
    assert db.execute("SELECT valid_zone_polygon('[[0,0],[1,0],[0,1]]')").fetchone()[0] is True


@pytest.mark.parametrize('existing', ['camera', 'zone'])
def test_005_completa_fk_faltante(db_before_foreign_keys, existing):
    from psycopg import sql

    db = db_before_foreign_keys
    column = f'{existing}_id'
    target = 'cameras' if existing == 'camera' else 'zones'
    db.execute(sql.SQL("ALTER TABLE incidents ADD CONSTRAINT {} FOREIGN KEY ({}) REFERENCES {}(id)").format(
        sql.Identifier(f'incidents_{column}_fkey'), sql.Identifier(column), sql.Identifier(target),
    ))
    db.execute(FOREIGN_KEYS.read_text(encoding='utf-8'))
    names = db.execute(
        "SELECT conname FROM pg_constraint WHERE conrelid = 'incidents'::regclass AND contype = 'f'"
    ).fetchall()
    assert {name for (name,) in names} == {'incidents_camera_id_fkey', 'incidents_zone_id_fkey'}


def test_005_no_confunde_constraint_de_otra_tabla(db_before_foreign_keys):
    db = db_before_foreign_keys
    db.execute(
        "CREATE TABLE other_table (camera_id TEXT, CONSTRAINT incidents_camera_id_fkey "
        "FOREIGN KEY (camera_id) REFERENCES cameras(id))"
    )
    db.execute(FOREIGN_KEYS.read_text(encoding='utf-8'))
    assert db.execute(
        "SELECT count(*) FROM pg_constraint WHERE conrelid = 'incidents'::regclass AND contype = 'f'"
    ).fetchone()[0] == 2


def test_consulta_por_zona_y_rango_de_fechas(seeded_db):
    rows = seeded_db.execute(
        "SELECT person_track_id FROM incidents WHERE zone_id = %s "
        "AND detected_at >= %s AND detected_at < %s ORDER BY detected_at DESC",
        ('zona-norte', '2026-01-15T00:00:00Z', '2026-01-17T00:00:00Z'),
    ).fetchall()
    assert rows == [(9,), (7,)]
    assert seeded_db.execute(
        "SELECT person_track_id FROM incidents WHERE zone_id = 'zona-norte' "
        "AND detected_at >= '2026-01-15T10:00:00Z' AND detected_at < '2026-01-16T02:00:00Z'"
    ).fetchall() == [(7,)]


def test_indices_del_modelo(postgres_db):
    indexes = dict(postgres_db.execute(
        "SELECT indexname, indexdef FROM pg_indexes WHERE schemaname = current_schema()"
    ).fetchall())
    assert '(zone_id, detected_at DESC)' in indexes['incidents_zone_detected_at_idx']
    assert "WHERE (status = 'open'::text)" in indexes['incidents_open_idx']
    assert '(incident_id, created_at)' in indexes['incident_events_incident_created_at_idx']
    assert "WHERE (status = 'pending'::text)" in indexes['notifications_pending_idx']
    assert sum('(detected_at DESC)' in definition for definition in indexes.values()) == 1


@pytest.mark.parametrize("value", [
    '{}', 'null', '[]', '[[0,0],[1,1]]',
    '[[0,0],[1,0],[0,1.1]]', '[[0,0],[1,0],[-0.1,1]]',
    '[[0,0],[1,0],[0,"1"]]', '[[0,0],[1,0],[0,null]]',
    '[[0,0],[1,0],false]', '[[0,0],[1,0],[0,1,0]]',
])
def test_poligono_invalido_se_rechaza(postgres_db, value):
    import psycopg

    with pytest.raises(psycopg.errors.CheckViolation):
        postgres_db.execute("UPDATE zones SET polygon = %s WHERE id = 'zona-norte'", (value,))


@pytest.mark.parametrize("statement,error", [
    ("UPDATE cameras SET id = ' ' WHERE id = 'camara-02'", 'CheckViolation'),
    ("UPDATE cameras SET rtsp_url = 'rtsp://usuario:secreto@192.0.2.10/live'", 'CheckViolation'),
    ("UPDATE zones SET suppression_s = 9", 'CheckViolation'),
    ("UPDATE zones SET suppression_s = 601", 'CheckViolation'),
    ("UPDATE beacons SET duration_s = 31", 'CheckViolation'),
    ("UPDATE beacons SET sound = 'otro'", 'CheckViolation'),
    ("UPDATE beacons SET battery_pct = -1", 'CheckViolation'),
    ("UPDATE beacons SET battery_pct = 101", 'CheckViolation'),
    ("UPDATE beacons SET zone_id = 'zona-norte' WHERE id = 'baliza-02'", 'UniqueViolation'),
    ("UPDATE beacons SET ip = '192.0.2.20' WHERE id = 'baliza-02'", 'UniqueViolation'),
    ("UPDATE users SET email = 'ADMIN@example.invalid'", 'CheckViolation'),
    ("UPDATE users SET role = 'root'", 'CheckViolation'),
    ("UPDATE users SET phone = '56912345678'", 'CheckViolation'),
    ("UPDATE users SET password_hash = 'texto-plano'", 'CheckViolation'),
    ("UPDATE shifts SET ends_at = starts_at", 'CheckViolation'),
    ("UPDATE zones SET camera_id = 'no-existe'", 'ForeignKeyViolation'),
])
def test_restricciones_de_catalogos(postgres_db, statement, error):
    import psycopg

    with pytest.raises(getattr(psycopg.errors, error)):
        postgres_db.execute(statement)


@pytest.mark.parametrize("column", ['camera_id', 'zone_id'])
def test_incidente_sin_catalogo_se_rechaza(seeded_db, column):
    import psycopg
    from psycopg import sql

    with pytest.raises(psycopg.errors.ForeignKeyViolation):
        seeded_db.execute(sql.SQL("UPDATE incidents SET {} = 'no-existe'").format(sql.Identifier(column)))


@pytest.mark.parametrize("column", ['camera_id', 'zone_id'])
def test_005_con_huerfanos_falla_sin_borrar_datos(db_before_foreign_keys, column):
    import psycopg
    from psycopg import sql

    db = db_before_foreign_keys
    db.execute(INCIDENTS.read_text(encoding="utf-8"))
    db.execute(sql.SQL("UPDATE incidents SET {} = 'no-existe'").format(sql.Identifier(column)))
    with pytest.raises(psycopg.errors.RaiseException, match='Hay incidentes'):
        db.execute(FOREIGN_KEYS.read_text(encoding="utf-8"))
    db.rollback()
    assert db.execute("SELECT count(*) FROM incidents").fetchone()[0] == 4
    assert db.execute(
        "SELECT count(*) FROM pg_constraint WHERE conrelid = 'incidents'::regclass AND contype = 'f'"
    ).fetchone()[0] == 0
    assert db.execute("SELECT to_regclass('incidents_zone_detected_at_idx')").fetchone()[0] is None


def test_relaciones_y_borrado_de_historial(seeded_db):
    import psycopg

    db = seeded_db
    incident = 'd2000000-0000-4000-8000-000000001001'
    user = 'd2000000-0000-4000-8000-000000000102'
    db.execute(
        "INSERT INTO incident_events (incident_id, user_id, from_status, to_status) "
        "VALUES (%s, %s, 'open', 'reviewed')", (incident, user),
    )
    db.execute(
        "INSERT INTO notifications (incident_id, user_id, channel) VALUES (%s, %s, 'email')",
        (incident, user),
    )
    with pytest.raises(psycopg.errors.ForeignKeyViolation):
        db.execute("DELETE FROM users WHERE id = %s", (user,))
    with pytest.raises(psycopg.errors.ForeignKeyViolation):
        db.execute("DELETE FROM cameras WHERE id = 'camara-01'")
    with pytest.raises(psycopg.errors.CheckViolation):
        db.execute("UPDATE notifications SET attempts = -1")
    with pytest.raises(psycopg.errors.CheckViolation):
        db.execute("UPDATE incident_events SET to_status = 'otro'")
    db.execute("DELETE FROM incidents WHERE id = %s", (incident,))
    assert db.execute("SELECT count(*) FROM incident_events").fetchone()[0] == 0
    assert db.execute("SELECT count(*) FROM notifications").fetchone()[0] == 0


def test_borrar_camara_sin_incidentes_desasigna_balizas(postgres_db):
    postgres_db.execute("DELETE FROM cameras WHERE id = 'camara-01'")
    assert postgres_db.execute("SELECT count(*) FROM zones WHERE camera_id = 'camara-01'").fetchone()[0] == 0
    assert postgres_db.execute("SELECT zone_id FROM beacons").fetchall() == [(None,), (None,)]
