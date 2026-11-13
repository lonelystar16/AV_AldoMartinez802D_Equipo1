"""Aviso por correo al prevencionista (tarea 4.20, RF-12, CU-05).

Un servidor SMTP falso reemplaza a smtplib: ninguna prueba envía correos. Las
pruebas con PostgreSQL se saltan sin CASCOVISION_TEST_POSTGRES=1.
"""

import asyncio
import re
import sys
import uuid
from pathlib import Path

import httpx
import pytest

PROYECTO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROYECTO / "src" / "api"))

from app import almacen, main, notificar  # noqa: E402

EDGE = {"Authorization": "Bearer token-edge"}
PREVENCIONISTA = "d2000000-0000-4000-8000-000000000102"  # del seed, inactivo
INCIDENTE = {
    "camera_id": "camara-01", "zone_id": "zona-norte",
    "detected_at": "2026-11-05T17:32:00Z", "violation_type": "missing_helmet",
    "violation_types": ["missing_helmet", "missing_reflective_vest"],
    "confidence": 0.9, "evidence_path": "incidents/2026/11/05/a.jpg",
    "face_blurred": True, "beacon_alert": {"status": "failed", "latency_ms": None},
}


class ServidorFalso:
    """Imita smtplib.SMTP y guarda lo que recibe."""

    enviados: list = []
    fallos = 0
    tls = True

    def __init__(self, host, puerto, timeout=None):
        self.usuario = None
        self.cifrado = False

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def ehlo(self):
        pass

    def has_extn(self, nombre):
        return nombre == "starttls" and ServidorFalso.tls

    def starttls(self, context=None):
        self.cifrado = True

    def login(self, usuario, clave):
        self.usuario = usuario

    def send_message(self, mensaje):
        if ServidorFalso.fallos:
            ServidorFalso.fallos -= 1
            raise OSError("conexión rechazada")
        ServidorFalso.enviados.append((mensaje, self.cifrado, self.usuario))


@pytest.fixture(autouse=True)
def smtp(monkeypatch, tmp_path):
    ServidorFalso.enviados, ServidorFalso.fallos, ServidorFalso.tls = [], 0, True
    monkeypatch.setattr(notificar.smtplib, "SMTP", ServidorFalso)
    monkeypatch.setenv("SMTP_HOST", "smtp.example.test")
    monkeypatch.setenv("SMTP_PORT", "587")
    monkeypatch.delenv("SMTP_USER", raising=False)
    imagen = tmp_path / "incidents" / "2026" / "11" / "05" / "a.jpg"
    imagen.parent.mkdir(parents=True)
    imagen.write_bytes(b"\xff\xd8 jpg difuminado")
    monkeypatch.setattr(main, "RAIZ_EVIDENCIA", tmp_path)
    return tmp_path


class AlmacenFalso:
    def __init__(self, destinatarios=None, repetido=False):
        self.destinatarios = destinatarios if destinatarios is not None else [
            {"id": "u1", "email": "prev@example.test", "phone": None}]
        self.repetido = repetido
        self.cerrados = []

    def destinatarios_avisos(self):
        return self.destinatarios

    def listar_zonas(self):
        return [{"id": "zona-norte", "name": "Zona Norte"}]

    def registrar_aviso(self, incident_id, user_id, canal, destino):
        return None if self.repetido else 7

    def cerrar_aviso(self, aviso_id, error, intentos):
        self.cerrados.append((aviso_id, error, intentos))


def _incidente(**cambios):
    return {"id": "i1", **INCIDENTE, **cambios}


# ---------- mensaje ----------

def test_correo_con_zona_hora_local_baliza_e_imagen(smtp) -> None:
    store = AlmacenFalso()
    notificar.notificar(store, _incidente(), smtp)

    mensaje, cifrado, _ = ServidorFalso.enviados[0]
    assert mensaje["To"] == "prev@example.test"
    assert mensaje["Subject"] == "CascoVision: sin casco en Zona Norte"
    texto = mensaje.get_body(("plain",)).get_content()
    assert "sin casco y sin chaleco en Zona Norte (camara-01)" in texto
    assert "14:32 del 05-11-2026" in texto  # 17:32 UTC en Santiago (verano)
    assert "la baliza NO sonó" in texto  # CU-04 2a: se destaca
    adjuntos = list(mensaje.iter_attachments())
    assert adjuntos[0].get_filename() == "evidencia.jpg"
    assert adjuntos[0].get_content() == b"\xff\xd8 jpg difuminado"
    assert cifrado  # usa STARTTLS si el servidor lo ofrece
    assert store.cerrados == [(7, None, 1)]


def test_sin_difuminar_no_adjunta_la_imagen(smtp) -> None:
    notificar.notificar(AlmacenFalso(), _incidente(face_blurred=False), smtp)
    mensaje = ServidorFalso.enviados[0][0]
    assert list(mensaje.iter_attachments()) == []  # RNF-08


def test_ruta_fuera_de_la_evidencia_no_se_adjunta(smtp) -> None:
    (smtp / "secreto.jpg").write_bytes(b"x")
    notificar.notificar(AlmacenFalso(), _incidente(evidence_path="incidents/../secreto.jpg"), smtp)
    assert list(ServidorFalso.enviados[0][0].iter_attachments()) == []


def test_reintenta_una_vez_y_registra_el_fallo(smtp) -> None:
    ServidorFalso.fallos = 1
    store = AlmacenFalso()
    notificar.notificar(store, _incidente(), smtp)
    assert store.cerrados == [(7, None, 2)]

    ServidorFalso.fallos = 5
    store = AlmacenFalso()
    notificar.notificar(store, _incidente(), smtp)
    assert store.cerrados[0][1].startswith("OSError: conexión rechazada")
    assert store.cerrados[0][2] == notificar.INTENTOS


def test_no_entrega_la_clave_sin_tls(smtp, monkeypatch) -> None:
    monkeypatch.setenv("SMTP_USER", "cuenta")
    ServidorFalso.tls = False
    store = AlmacenFalso()
    notificar.notificar(store, _incidente(), smtp)
    assert ServidorFalso.enviados == []
    assert "refusing to send credentials" in store.cerrados[0][1]


def test_sin_smtp_ni_repetidos_no_envia(smtp, monkeypatch) -> None:
    notificar.notificar(AlmacenFalso(repetido=True), _incidente(), smtp)
    monkeypatch.delenv("SMTP_HOST")
    notificar.notificar(AlmacenFalso(), _incidente(), smtp)
    assert ServidorFalso.enviados == []


def test_un_error_del_almacen_no_escapa(smtp) -> None:
    class Roto(AlmacenFalso):
        def destinatarios_avisos(self):
            raise almacen.AlmacenNoDisponible("caída")

    notificar.notificar(Roto(), _incidente(), smtp)  # no lanza


# ---------- PostgreSQL ----------

def _post(json: dict) -> httpx.Response:
    async def request():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=main.app),
                                     base_url="http://test") as cliente:
            return await cliente.post("/incidents", json=json, headers=EDGE)

    return asyncio.run(request())


@pytest.fixture
def pg(postgres_db, monkeypatch):
    monkeypatch.setenv("CASCOVISION_STORAGE", "postgres")
    monkeypatch.setenv("EDGE_API_TOKEN", "token-edge")
    postgres_db.execute("UPDATE users SET active = TRUE WHERE id = %s", (PREVENCIONISTA,))
    return postgres_db


def _avisos(db) -> list:
    return db.execute("SELECT incident_id::text, user_id::text, channel, destination, status, "
                      "attempts, sent_at IS NOT NULL FROM notifications ORDER BY id").fetchall()


def test_postgres_incidente_nuevo_avisa_al_prevencionista(pg) -> None:
    respuesta = _post(INCIDENTE)
    assert respuesta.status_code == 201
    incidente = respuesta.json()["id"]
    assert _avisos(pg) == [(incidente, PREVENCIONISTA, "email",
                            "prevencion@example.invalid", "sent", 1, True)]
    assert len(ServidorFalso.enviados) == 1  # admin y supervisor del seed no reciben

    # Un episodio que llega desde la cola del agente también avisa, una sola vez.
    episodio = str(uuid.uuid4())
    for evento in ("ping", "fin"):
        assert _post({**INCIDENTE, "event": evento, "episode_id": episodio}).status_code == 201
    assert len(_avisos(pg)) == 2 and len(ServidorFalso.enviados) == 2


def test_postgres_aviso_fallido_queda_registrado(pg) -> None:
    ServidorFalso.fallos = 5
    assert _post(INCIDENTE).status_code == 201  # el agente no se entera del fallo
    (_, _, _, _, estado, intentos, enviado), = _avisos(pg)
    assert (estado, intentos, enviado) == ("failed", 2, False)
    assert "conexión rechazada" in pg.execute("SELECT error FROM notifications").fetchone()[0]


def test_postgres_el_rol_de_la_api_registra_avisos(pg, monkeypatch) -> None:
    import os

    from psycopg import sql

    if not pg.execute("SELECT rolsuper FROM pg_roles WHERE rolname = current_user").fetchone()[0]:
        pytest.skip("Requiere un usuario PostgreSQL superusuario para cambiar de rol")
    sufijo = uuid.uuid4().hex[:10]
    nombres = {"cascovision": f"cv_api_{sufijo}", "auditoria_admin": f"cv_audit_{sufijo}",
               "prevencion_mantencion": f"cv_prev_{sufijo}"}
    fuente = (PROYECTO / "db" / "roles.sql").read_text(encoding="utf-8")
    for original, temporal in nombres.items():
        fuente = re.sub(rf"\b{original}\b", temporal, fuente)
    pg.execute(fuente, prepare=False)
    try:
        monkeypatch.setenv("PGOPTIONS", f"{os.getenv('PGOPTIONS', '')} -c role={nombres['cascovision']}")
        assert _post(INCIDENTE).status_code == 201
        assert [fila[4] for fila in _avisos(pg)] == ["sent"]
    finally:
        pg.execute(sql.SQL("DROP OWNED BY {}, {}, {}").format(*map(sql.Identifier, nombres.values())))
        pg.execute(sql.SQL("DROP ROLE {}, {}, {}").format(*map(sql.Identifier, nombres.values())))
