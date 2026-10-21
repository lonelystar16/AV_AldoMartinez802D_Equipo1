# Almacenamiento de incidentes

## La capa

`src/api/app/almacen.py` define el protocolo `Almacen` con tres operaciones:

```python
class Almacen(Protocol):
    def crear(self, registro: dict[str, Any]) -> None: ...
    def listar(self, filtros: dict[str, str], pagina: int, limite: int) -> list[dict[str, Any]]: ...
    def obtener(self, incident_id: str) -> dict[str, Any] | None: ...
```

La API depende del protocolo, no de una implementación. Elegir backend es
cambiar una línea en `obtener_almacen()`:

```python
def obtener_almacen() -> Almacen:
    tipo = os.getenv("CASCOVISION_STORAGE", "json").lower()
    if tipo == "postgres":
        return AlmacenPostgres()
    if tipo == "json":
        return AlmacenJSON(ARCHIVO)
    raise AlmacenNoDisponible(f"Unknown storage: {tipo}")
```

## Implementaciones

### `AlmacenJSON`

Archivo local, escritura atómica (escribe en `.tmp` y renombra). Pensado para
desarrollo y pruebas.

**No usar con varios procesos a la vez**: no hay bloqueo de archivo, así que dos
escrituras simultáneas pueden pisarse. La API es un proceso único por
definición, pero el agente Edge y otro proceso podrían escribir a la vez.

Si el JSON se corrompe, `_cargar()` devuelve una lista vacía en vez de fallar.
Silencioso, pero evita que la API se caiga.

### `AlmacenPostgres`

Conexión con `psycopg` (v3). Configuración por variables `POSTGRES_*`.

El esquema lo definen las migraciones de `db/migrations/`, que se aplican en
orden antes de usar este backend:

```bash
psql -d cascovision -f "Fase 2/Evidencias Proyecto/db/migrations/001_create_incidents.sql"
psql -d cascovision -f "Fase 2/Evidencias Proyecto/db/migrations/002_add_tracking_fields.sql"
```

Los errores de psycopg se traducen a `AlmacenNoDisponible`, que la API
convierte en `503`:

| Error de PostgreSQL | Significado | Mensaje al cliente |
| --- | --- | --- |
| `UndefinedTable` | Falta la migración 001 | "Incident schema is not initialized" |
| `UndefinedColumn` | Falta la migración 002 | "Incident schema is outdated" |
| `OperationalError` | No hay conexión | "PostgreSQL is unavailable" |

## Sincronía entre los dos backends

El contrato es el mismo, pero hay una diferencia de **formato de fecha** que
importa al añadir un campo:

- JSON guarda lo que le des. `main.py` serializa `created_at` como ISO 8601
  con `Z`.
- PostgreSQL devuelve `TIMESTAMPTZ` como `datetime`. `_desde_fila()` los
  convierte a UTC con `astimezone(timezone.utc)`.

Las respuestas de la API siempre van en UTC, en ambos backends.

## Añadir un campo

1. **Modelo Pydantic** en `src/api/app/main.py`: el campo en el modelo de
   entrada (`IncidentCreate`) y en el de salida (`Incident`).
2. **Migración SQL** nueva en `db/migrations/`, con numeración correlativa
   (`003_...sql`). No edites una migración ya aplicada: en la base de datos de
   alguien ya corrió.
3. **Ambas implementaciones** de `Almacen`:
   - `AlmacenJSON` no necesita cambios: guarda el diccionario tal cual.
   - `AlmacenPostgres`: añadir la columna a `COLUMNAS`, al `INSERT` de
     `crear()` y al `SELECT` de `listar()`/`obtener()`, más el desempaquetado de
     `_desde_fila()`.
4. **Prueba** en `tests/test_incidents.py`.
5. **Documentación** en `docs/API.md`: el campo y su validación.

## Añadir un backend nuevo

Implementa el protocolo `Almacen` con las tres operaciones y añade el caso en
`obtener_almacen()`. Los errores de conexión se señalan lanzando
`AlmacenNoDisponible`: `main.py` ya las traduce a `503`.
