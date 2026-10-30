# Plan de cierre de tareas de base de datos 4.8–4.13

La implementación conserva intactas las migraciones 001–005. `face_blurred`
significa que la aplicación terminó el difuminado y guardó la imagen; la base
no puede inspeccionar píxeles para certificar que el rostro quedó irreconocible.

1. **Reportería (4.11 / RF-15):** `db/migrations/007_vistas_reporteria.sql` crea
   vistas por zona, turno y hora. Los turnos se calculan en `America/Santiago`,
   incluido el turno nocturno que cruza medianoche. `db/views/README.md` señala
   la migración como fuente única.
2. **Respaldo/recuperación (4.13):** `db/backup.ps1`, `db/restore.ps1` y
   `db/README.md` documentan dumps custom y restauración confirmada. El equipo
   debe definir el volumen persistente y la política de retención/cifrado.
3. **Evidencia difuminada (4.8 / RNF-09):** migración 006 agrega
   `incidents.face_blurred`. Edge marca `TRUE` después de difuminar a todas las
   personas del frame y guardar la imagen. Las filas anteriores quedan sin
   certificación (`FALSE`) y requieren verificación de archivos para demostrar
   cobertura histórica del 100 %.
4. **Primer administrador (RF-16/17):** `db/create_admin.py` solicita la clave
   de forma oculta y guarda solo bcrypt generado por `pgcrypto`. La API aún no
   implementa inicio de sesión; crear la fila no completa RF-17.
5. **Cámara-zona:** migración 006 agrega unicidad compuesta en `zones` y una FK
   compuesta en `incidents`. Si hay pares incompatibles, falla sin borrar filas.
6. **Notificaciones (RNF-03):** migración 006 agrega `created_at`, destino usado
   y unicidad por incidente/usuario/canal. Requiere resolver destinos ausentes o
   duplicados históricos antes de aplicar.
7. **Historial de estados:** migración 006 prohíbe cambios al mismo estado y
   exige comentario para cerrar o marcar falso positivo.
8. **Incidentes:** migración 006 valida tipos y tiempos de episodio, agrega
   `updated_at` y lo actualiza automáticamente al modificar una fila.
9. **Roles SQL:** `db/roles.sql` define `cascovision` para la API,
   `auditoria_admin` (alineado al usuario de aplicación `admin`) y
   `prevencion_mantencion` (alineado a `prevencionista`). El rol `supervisor`
   permanece en `users`; los GRANT de PostgreSQL no se derivan de esa columna.
   La API conecta como `cascovision`; no se debe compartir ese login humano.
10. **Seguimiento/reversión:** `db/apply_migrations.py` registra migración,
    checksum y fecha en `schema_migrations`. Es forward-only; se revierte con
    una migración compensatoria revisada para evitar pérdida de datos.
11. **Decisiones documentadas en `MODELO_DATOS.md` §6:** retención sugerida de
    evidencias por 90 días y limpieza controlada; mantener una baliza por zona
    para el alcance actual; limitar zonas de supervisor solo cuando exista una
    asignación de frentes confirmada. No se implementan limpieza automática ni
    `user_zones`.
12. **Pruebas:** `tests/test_db.py` cubre restricciones y vistas nuevas. Se
    omiten sin `CASCOVISION_TEST_POSTGRES=1`. En este checkout no se encontró un
    workflow de CI que habilite PostgreSQL; `db/README.md` deja explícita esa
    limitación. Las pruebas deben apuntar a una base exclusiva.
13. **Documentación/diagrama:** `docs/MODELO_DATOS.md` y
    `docs/diagramas/diagrama_er.py` reflejan las columnas de 002/003 y 006,
    además del nuevo modelo de notificaciones y reportería.

## Límites pendientes

- El esquema actual no contiene una columna `event = 'fin'` sin `ended_at` ni
  notificaciones de demo. Antes de ejecutar 006 en otra base, resuelva los
  conflictos históricos que la migración detecte con datos verificados.
- `incident_events.incident_id` conserva `ON DELETE CASCADE`; la protección de
  borrado en `roles.sql` evita que `auditoria_admin` borre incidentes, pero un
  propietario de tablas aún puede eliminar el historial al borrar un incidente.
- La base marca `face_blurred`, pero solo la aplicación y una revisión de las
  imágenes pueden probar que el difuminado fue correcto.
