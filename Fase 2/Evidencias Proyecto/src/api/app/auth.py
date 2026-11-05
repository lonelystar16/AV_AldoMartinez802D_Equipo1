"""Autenticación de usuarios del dashboard con JWT (RF-16, RF-17, tarea 4.16).

El usuario inicia sesión con correo y contraseña en ``POST /auth/login`` y
recibe un token firmado con ``JWT_SECRET`` (HS256) que dura un turno. Cada
ruta protegida exige ese token en ``Authorization: Bearer``. El agente Edge no
usa esto: sigue con su propio ``EDGE_API_TOKEN``.

La contraseña nunca pasa por Python más allá de la consulta: con PostgreSQL se
compara con ``crypt()`` de pgcrypto contra el hash bcrypt de ``users``.
"""

import os
from datetime import datetime, timedelta, timezone

import jwt
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

ROLES = ("admin", "prevencionista", "supervisor")
DURACION = timedelta(hours=8)  # un turno
ALGORITMO = "HS256"

bearer = HTTPBearer(auto_error=False)


def _secreto() -> str:
    secreto = os.getenv("JWT_SECRET", "")
    # HS256 con un secreto corto se puede adivinar por fuerza bruta.
    if len(secreto) < 32:
        raise HTTPException(status_code=503, detail="JWT_SECRET is not configured")
    return secreto


def emitir_token(usuario: dict) -> tuple[str, datetime]:
    """Firma el token del usuario y devuelve también cuándo vence."""
    vence = datetime.now(timezone.utc) + DURACION
    token = jwt.encode(
        {
            "sub": str(usuario["id"]),
            "email": usuario["email"],
            "name": usuario["full_name"],
            "role": usuario["role"],
            "exp": vence,
        },
        _secreto(),
        algorithm=ALGORITMO,
    )
    return token, vence


def usuario_actual(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
) -> dict:
    """Dependencia de las rutas protegidas: valida el token y devuelve el usuario."""
    no_autorizado = HTTPException(
        status_code=401,
        detail="Invalid or missing bearer token",
        headers={"WWW-Authenticate": "Bearer"},
    )
    if credentials is None:
        raise no_autorizado
    try:
        datos = jwt.decode(
            credentials.credentials,
            _secreto(),
            algorithms=[ALGORITMO],
            options={"require": ["exp", "sub", "role"]},
        )
    except jwt.PyJWTError as exc:
        raise no_autorizado from exc
    if datos["role"] not in ROLES:
        raise no_autorizado
    return {
        "id": datos["sub"],
        "email": datos.get("email"),
        "full_name": datos.get("name"),
        "role": datos["role"],
    }


def requiere_rol(*roles: str):
    """Dependencia que además exige uno de los roles indicados (RF-16)."""

    def dependencia(usuario: dict = Depends(usuario_actual)) -> dict:
        if usuario["role"] not in roles:
            raise HTTPException(status_code=403, detail="Insufficient role")
        return usuario

    return dependencia
