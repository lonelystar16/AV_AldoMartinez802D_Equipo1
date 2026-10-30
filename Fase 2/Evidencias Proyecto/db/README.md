# Operación de PostgreSQL

## Migraciones

Configure `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_HOST` y
`POSTGRES_PORT` en el entorno local. Desde esta carpeta, ejecute
`python apply_migrations.py`. El script registra nombre, SHA-256 y fecha en
`schema_migrations`; si cambia un archivo ya aplicado, se detiene. Las
migraciones se consideran forward-only: para revertir un cambio de esquema se
prepara y revisa una migración compensatoria, evitando borrar datos con un
rollback genérico. Antes de aplicar 006, revise los incidentes con cámara-zona
incompatibles, duplicados de notificación y destinos SMS sin teléfono; la
migración falla y conserva los datos si encuentra alguno.

El ejecutor solicita el usuario propietario del esquema y su clave con entrada
oculta. En bases con incidentes existentes, cargue primero las cámaras y zonas
reales requeridas por 005; no aplique catálogos demo a producción.

## Roles de PostgreSQL

Después de migrar, ejecute `psql -X -d <bd> -v ON_ERROR_STOP=1 -f "Fase 2/Evidencias Proyecto/db/roles.sql"`
desde la raíz del repositorio con un administrador PostgreSQL. Asigne una clave
interactivamente por rol: `\password cascovision`, `\password auditoria_admin` y
`\password prevencion_mantencion`. No las incluya en SQL, `.env.example` ni comandos guardados.

## Usuario administrador inicial

Con las migraciones aplicadas y `pgcrypto` disponible, ejecute
`python create_admin.py`. Solicita correo, nombre y contraseña sin mostrar esta
última ni guardarla en el repositorio. El usuario queda `active = TRUE` y rol
`admin`. La API actual todavía no implementa login RF-17; la fila prepara el
usuario en la base, pero no habilita inicio de sesión hasta completar esa API.

## Respaldo y restauración

`backup.ps1 -Database <bd> -User <rol_con_SELECT> -Output <ruta>` crea un archivo custom de `pg_dump`.
Use un archivo de contraseñas PostgreSQL (`PGPASSFILE`) o el prompt de la
herramienta; no agregue secretos al comando ni al repositorio. Guarde el dump en
un volumen con acceso restringido y cifrado.

`restore.ps1 -Database <bd> -User <propietario> -Backup <ruta> -ConfirmReplace` ejecuta
`pg_restore --clean --if-exists`; puede reemplazar objetos y datos del destino.
Verifique el nombre de la base y pruebe primero en una base vacía o aislada.
Los scripts requieren `pg_dump` y `pg_restore` en `PATH`.

## Pruebas

Las pruebas SQL usan una base exclusiva indicada por `CASCOVISION_TEST_POSTGRES=1`
y las variables `POSTGRES_*`. En el checkout revisado no hay workflow de CI que
active esa variable; el equipo debe provisionar PostgreSQL de pruebas y activar
las pruebas SQL antes de afirmar que estas restricciones se ejecutaron en CI.
