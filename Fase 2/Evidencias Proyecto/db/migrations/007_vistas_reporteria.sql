BEGIN;

CREATE OR REPLACE VIEW incidentes_por_zona AS
SELECT z.id AS zone_id, z.name AS zone_name, count(i.id)::BIGINT AS total_incidentes,
       count(i.id) FILTER (WHERE i.status = 'open')::BIGINT AS alertas_activas
FROM zones z LEFT JOIN incidents i ON i.zone_id = z.id
GROUP BY z.id, z.name;

CREATE OR REPLACE VIEW incidentes_por_turno AS
WITH local_time AS (
    SELECT i.*, (i.detected_at AT TIME ZONE 'America/Santiago')::time AS hora_local
    FROM incidents i
), turnos AS (
    SELECT id, name, starts_at, ends_at FROM shifts
)
SELECT t.id AS shift_id, t.name AS shift_name, count(l.id)::BIGINT AS total_incidentes,
       count(l.id) FILTER (WHERE l.status = 'open')::BIGINT AS alertas_activas
FROM turnos t LEFT JOIN local_time l ON CASE
    WHEN t.starts_at < t.ends_at THEN l.hora_local >= t.starts_at AND l.hora_local < t.ends_at
    ELSE l.hora_local >= t.starts_at OR l.hora_local < t.ends_at
END
GROUP BY t.id, t.name;

CREATE OR REPLACE VIEW incidentes_por_hora AS
SELECT (detected_at AT TIME ZONE 'America/Santiago')::date AS fecha_local,
       date_part('hour', detected_at AT TIME ZONE 'America/Santiago')::smallint AS hora_local,
       count(*)::BIGINT AS total_incidentes,
       count(*) FILTER (WHERE status = 'open')::BIGINT AS alertas_activas
FROM incidents
GROUP BY 1, 2;

COMMIT;
