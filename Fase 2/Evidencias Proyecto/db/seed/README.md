# Datos de prueba y migraciones D2 v1.0

Ejecutar únicamente en una base de desarrollo o de pruebas. Las migraciones se
aplican en orden y se pueden repetir sin recrear los objetos existentes. Los
dos seeds usan claves fijas y `ON CONFLICT (id) DO NOTHING`, sin borrar ni
actualizar registros existentes. Un conflicto con otra clave única detiene la
carga para su revisión.

Las tablas, columnas e índices usan `IF NOT EXISTS`; la función usa
`CREATE OR REPLACE FUNCTION`. Las FK de la 005 se agregan solo si no existe
su nombre en la tabla `incidents`. Esto permite repetir la instalación, pero
no compara ni corrige definiciones de objetos existentes: un cambio de tipo,
restricción o índice requiere un `ALTER` o una migración específica. El orden
y la comprobación de incidentes huérfanos siguen siendo obligatorios.

## Instalación desde cero

Desde `Fase 2/Evidencias Proyecto`, abrir `psql -X -d cascovision_dev` con un
usuario que pueda crear tablas y funciones. Ejecutar en este orden:

```sql
\set ON_ERROR_STOP on
\encoding UTF8
\i db/migrations/001_create_incidents.sql
\i db/migrations/002_add_tracking_fields.sql
\i db/migrations/003_add_episode_lifecycle.sql
\i db/migrations/004_modelo_completo.sql
\i db/seed/001_catalogos.sql
\i db/migrations/005_claves_incidentes.sql
\i db/seed/002_incidentes_demo.sql
```

La 003 parte de la versión existente en `main`, adaptada para poder repetirse.
La 004 crea las tablas nuevas;
la 005 agrega las FK de incidentes y los índices de §4 de `docs/MODELO_DATOS.md`,
sin duplicar el índice general por fecha creado en la 002. La 004, la 005 y
cada seed se ejecutan en una transacción.

## Base que ya contiene incidentes

Aplicar solo las migraciones pendientes y revisar los huérfanos antes de la 005:

```sql
SELECT i.id, i.camera_id, i.zone_id,
       c.id IS NULL AS falta_camara, z.id IS NULL AS falta_zona
FROM incidents i
LEFT JOIN cameras c ON c.id = i.camera_id
LEFT JOIN zones z ON z.id = i.zone_id
WHERE c.id IS NULL OR z.id IS NULL;
```

Si hay resultados, registrar las cámaras y zonas reales que faltan o corregir
sus referencias con información verificada. El catálogo demo solo cubre sus
propios identificadores. La 005 falla sin borrar incidentes si aún hay huérfanos.
No cargar datos ficticios en producción para resolver este requisito.

## Contenido y comprobación

- 2 cámaras desactivadas, 3 zonas desactivadas y 2 balizas fuera de línea.
  Las direcciones `192.0.2.x` son de ejemplo y no representan dispositivos reales.
- 3 usuarios ficticios deshabilitados, sin teléfonos y con hash bcrypt de ejemplo;
  no se proporciona un acceso de demostración.
- 3 turnos: 06–14, 14–22 y 22–06. Son horarios demo que deben ajustarse a la faena.
- 4 incidentes en distintas zonas y fechas UTC, con ambos tipos de infracción,
  los cuatro estados de gestión y episodios `inicio`, `ping` y `fin`.
- Las rutas de evidencia son ficticias; no se crean imágenes, notificaciones
  ni envíos de SMS/correo. El seed no activa cámaras, zonas ni balizas existentes.

```sql
SELECT zone_id, detected_at, status FROM incidents
WHERE zone_id = 'zona-norte'
  AND detected_at >= '2026-01-15T00:00:00Z'
  AND detected_at <  '2026-01-17T00:00:00Z'
ORDER BY detected_at DESC;

EXPLAIN (ANALYZE, BUFFERS)
SELECT * FROM incidents
WHERE zone_id = 'zona-norte'
  AND detected_at >= '2026-01-15T00:00:00Z'
  AND detected_at <  '2026-01-17T00:00:00Z'
ORDER BY detected_at DESC;
```

Con cuatro filas PostgreSQL puede elegir un recorrido secuencial; esto no
implica que falte el índice. Los rangos de fecha anteriores son consultas SQL:
esta tarea no agrega parámetros nuevos a la API.

## Pruebas automatizadas

Instalar `requirements.txt` y `requirements-dev.txt`. En PowerShell, configurar
una base exclusiva de pruebas (el usuario debe poder crear esquemas):

```powershell
$env:CASCOVISION_TEST_POSTGRES = '1'
$env:POSTGRES_HOST = 'localhost'
$env:POSTGRES_PORT = '5432'
$env:POSTGRES_DB = 'cascovision_test'
$env:POSTGRES_USER = 'cascovision_test'
$env:POSTGRES_PASSWORD = '<contraseña local>'
python -m pytest tests/test_db.py tests/test_incidents.py tests/test_health.py -q
```

Cada caso crea y elimina su propio esquema `test_cascovision_<uuid>`; no trunca
tablas de otros esquemas. Se comprueban instalación y repetición de migraciones
y seed, conservación de datos, índices, filtros, límites, FK, borrados y fallo
atómico de la 005 ante huérfanos.
Sin `CASCOVISION_TEST_POSTGRES=1`, las pruebas SQL se omiten y las de API usan JSON.
