"""Crea el primer usuario admin sin escribir la contraseña en el repositorio."""

from getpass import getpass
from pathlib import Path
import sys
from uuid import uuid4

import psycopg

PROJECT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT / "src" / "api"))
from app.almacen import postgres_config


def main() -> None:
    email = input("Correo del administrador: ").strip().lower()
    name = input("Nombre completo: ").strip()
    password = getpass("Contrasena nueva: ")
    if not email or not name or len(password) < 12:
        raise SystemExit("Correo y nombre son obligatorios; use una contrasena de 12+ caracteres.")
    config = postgres_config()
    config["user"] = input("PostgreSQL schema owner: ").strip()
    config["password"] = getpass("Password: ")
    with psycopg.connect(**config) as db:
        db.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")
        db.execute(
            "INSERT INTO users (id, email, full_name, password_hash, role, active) "
            "VALUES (%s, %s, %s, crypt(%s, gen_salt('bf', 12)), 'admin', TRUE)",
            (uuid4(), email, name, password),
        )
    print("Usuario admin creado.")


if __name__ == "__main__":
    main()
