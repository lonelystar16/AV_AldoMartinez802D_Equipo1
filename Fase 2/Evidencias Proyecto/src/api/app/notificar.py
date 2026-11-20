"""Aviso remoto al prevencionista por correo (RF-12, CU-05).

Corre como tarea de fondo después de responder al agente Edge, así que nunca
lanza excepciones: un correo que no sale queda como ``failed`` en la
tabla ``notifications`` con el motivo, y el incidente ya está guardado.

El aviso se activa solo si SMTP_HOST está en el entorno (RNF-10), junto con
SMTP_PORT, SMTP_USER, SMTP_PASSWORD y SMTP_FROM. El SMS (RF-11) quedó fuera
por decisión del equipo (05-11-2026); la tabla ya admite el canal ``sms``.
"""

import logging
import os
import smtplib
import ssl
from email.message import EmailMessage
from pathlib import Path
from typing import Any

from . import almacen

log = logging.getLogger("cascovision.avisos")

# RNF-03 pide el aviso en ≤ 30 s: dos intentos de 8 s por envío.
ESPERA_S = 8
INTENTOS = 2

INFRACCION = {"missing_helmet": "sin casco", "missing_reflective_vest": "sin chaleco"}
# CU-04 1a y 2a: si la baliza no sonó, el aviso lo destaca.
BALIZA = {
    "alerted": "La baliza sonó",
    "failed": "ATENCIÓN: la baliza NO sonó (falló)",
    "skipped_offline": "ATENCIÓN: la baliza está fuera de línea y no sonó",
}


def archivo_evidencia(raiz: Path, ruta_relativa: str) -> Path | None:
    """La imagen dentro de raiz/incidents, o None si no existe o se sale."""
    carpeta = (raiz / "incidents").resolve()
    archivo = (raiz / ruta_relativa).resolve()
    if not archivo.is_relative_to(carpeta) or not archivo.is_file():
        return None
    return archivo


def _texto(incidente: dict[str, Any], zona: str) -> str:
    tipos = incidente.get("violation_types") or [incidente["violation_type"]]
    falta = " y ".join(INFRACCION.get(t, t) for t in tipos)
    hora = almacen._instante(incidente["detected_at"]).astimezone(almacen.ZONA_LOCAL)
    baliza = BALIZA.get(incidente["beacon_alert"]["status"], "")
    return (f"CascoVision: persona {falta} en {zona} ({incidente['camera_id']}) "
            f"a las {hora:%H:%M} del {hora:%d-%m-%Y}. {baliza}.")


def _enviar_correo(destino: str, asunto: str, texto: str, imagen: Path | None) -> None:
    mensaje = EmailMessage()  # rechaza saltos de línea en las cabeceras
    mensaje["Subject"] = asunto
    mensaje["From"] = os.getenv("SMTP_FROM") or os.getenv("SMTP_USER") or "cascovision@localhost"
    mensaje["To"] = destino
    mensaje.set_content(texto + "\n\nLa imagen adjunta tiene los rostros difuminados.\n"
                        if imagen else texto + "\n")
    if imagen:
        mensaje.add_attachment(imagen.read_bytes(), maintype="image", subtype="jpeg",
                               filename="evidencia.jpg")

    host, puerto = os.environ["SMTP_HOST"], int(os.getenv("SMTP_PORT") or 587)
    usuario, clave = os.getenv("SMTP_USER"), os.getenv("SMTP_PASSWORD")
    contexto = ssl.create_default_context()
    if puerto == 465:
        servidor = smtplib.SMTP_SSL(host, puerto, timeout=ESPERA_S, context=contexto)
    else:
        servidor = smtplib.SMTP(host, puerto, timeout=ESPERA_S)
    with servidor:
        if puerto != 465:
            servidor.ehlo()
            if servidor.has_extn("starttls"):
                servidor.starttls(context=contexto)
                servidor.ehlo()
            elif usuario:
                raise RuntimeError("SMTP server does not offer TLS; refusing to send credentials")
        if usuario:
            servidor.login(usuario, clave or "")
        servidor.send_message(mensaje)


def notificar(store: almacen.Almacen, incidente: dict[str, Any], raiz_evidencia: Path) -> None:
    """Avisa a los prevencionistas activos de un incidente nuevo."""
    try:
        if not os.getenv("SMTP_HOST", "").strip():
            return
        destinatarios = store.destinatarios_avisos()
        if not destinatarios:
            return
        zona = next((z["name"] for z in store.listar_zonas()
                     if z["id"] == incidente["zone_id"]), incidente["zone_id"])
        texto = _texto(incidente, zona)
        asunto = (f"CascoVision: {INFRACCION.get(incidente['violation_type'], 'infracción')} "
                  f"en {zona}")
        # RNF-08: solo se adjunta la imagen si el agente la difuminó.
        imagen = (archivo_evidencia(raiz_evidencia, incidente["evidence_path"])
                  if incidente.get("face_blurred") else None)
    except Exception:
        log.exception("No se pudo preparar el aviso del incidente %s", incidente.get("id"))
        return

    for usuario in destinatarios:
        try:
            aviso = store.registrar_aviso(incidente["id"], usuario["id"], "email",
                                          usuario["email"])
            if aviso is None:  # ya avisado (reintento del agente)
                continue
            error, intento = None, 0
            for intento in range(1, INTENTOS + 1):
                try:
                    _enviar_correo(usuario["email"], asunto, texto, imagen)
                    error = None
                    break
                except Exception as exc:  # cualquier fallo de red o del servidor
                    error = f"{type(exc).__name__}: {exc}"[:300]
            store.cerrar_aviso(aviso, error, intento)
            if error:
                log.warning("Aviso a %s falló: %s", usuario["id"], error)
        except Exception:
            log.exception("No se pudo registrar el aviso del incidente %s", incidente.get("id"))
