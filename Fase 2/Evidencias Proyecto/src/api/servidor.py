"""Arranque de la API REST de CascoVision con uv.

Punto de entrada único para levantar el servicio. Hace lo que hace falta
antes de arrancar y avisa con claridad si algo falta.

Uso:

    uv run python "Fase 2/Evidencias Proyecto/src/api/servidor.py"

Opciones:

    --host        Interfaz de escucha. Por defecto 127.0.0.1 (solo local).
    --port        Puerto. Por defecto 8000.
    --reload      Recarga automatica al cambiar codigo (desarrollo).
    --check       Solo verifica la configuracion y sale. No levanta el servidor.
    --requiere-token
                  Exige que EDGE_API_TOKEN este configurado. Sin el token,
                  `POST /incidents` responde 503, aunque el resto de la API
                  funciona.

Ejemplos:

    # Levantar en local para desarrollo
    uv run python "Fase 2/Evidencias Proyecto/src/api/servidor.py" --reload

    # Verificar la configuracion sin levantar nada
    uv run python "Fase 2/Evidencias Proyecto/src/api/servidor.py" --check

    # Exponer en la red local (la faena se conecta a esta IP)
    uv run python "Fase 2/Evidencias Proyecto/src/api/servidor.py" --host 0.0.0.0
"""

import argparse
import sys
from pathlib import Path

# El directorio de este archivo es 'src/api', que es el '--app-dir' de uvicorn.
API_DIR = Path(__file__).resolve().parent
if str(API_DIR) not in sys.path:
    sys.path.insert(0, str(API_DIR))

from app import config  # noqa: E402


def parse_args() -> argparse.Namespace:
    analizador = argparse.ArgumentParser(
        description="Arranque de la API REST de CascoVision")
    analizador.add_argument("--host", default="127.0.0.1",
                            help="Interfaz de escucha. '0.0.0.0' para la red local")
    analizador.add_argument("--port", type=int, default=8000)
    analizador.add_argument("--reload", action="store_true",
                            help="Recarga automatica al cambiar el codigo")
    analizador.add_argument("--check", action="store_true",
                            help="Solo verifica la configuracion y sale")
    analizador.add_argument("--requiere-token", action="store_true",
                            help="Falla si EDGE_API_TOKEN no esta configurado")
    return analizador.parse_args()


def verificar(args: argparse.Namespace) -> bool:
    """Comprueba la configuracion. Devuelve True si todo esta en orden."""
    config.cargar_env()
    estado = config.estado_configuracion()
    faltantes = config.faltantes_obligatorias()

    print("Configuracion de CascoVision")
    print("-" * 52)
    print(f"  Archivo .env      : {estado['archivo_env'] or 'no encontrado (se usa el entorno)'}")
    print(f"  Almacenamiento     : {estado['almacenamiento']}")
    print(f"  Token configurado : {'si' if estado['token_configurado'] else 'NO'}")
    if estado["variables_desconocidas"]:
        print(f"  Variables sin uso : {', '.join(estado['variables_desconocidas'])}")
    print()

    if faltantes:
        print("Faltan variables obligatorias: " + ", ".join(faltantes))
        print()
        print("Para configurarlas:")
        print(f"  1. Copia el ejemplo:  cp \"{config.RUTA_ENV.parent / '.env.example'}\" "
              f"\"{config.RUTA_ENV}\"")
        print("  2. Edita el archivo y cambia los valores 'cambiar_esto'")
        print("  3. Levanta de nuevo la API")
        if args.requiere_token:
            return False
        print()
        print("La API puede levantarse igualmente: las rutas de lectura no")
        print("necesitan el token, y las de escritura responderan 503.")
        return True

    print("Configuracion correcta.")
    return True


def main() -> None:
    args = parse_args()

    if not verificar(args):
        sys.exit(1)

    if args.check:
        return

    import uvicorn

    print()
    print(f"Levantando CascoVision API en http://{args.host}:{args.port}")
    print(f"  Documentacion: http://{args.host}:{args.port}/docs")
    print(f"  Estado:        http://{args.host}:{args.port}/health")
    print(f"  Configuracion: http://{args.host}:{args.port}/config")
    print()

    uvicorn.run("app.main:app", host=args.host, port=args.port,
                reload=args.reload, app_dir=str(API_DIR))


if __name__ == "__main__":
    main()
