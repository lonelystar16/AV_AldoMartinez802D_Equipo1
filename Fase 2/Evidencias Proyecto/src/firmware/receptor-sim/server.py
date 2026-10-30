"""Receptor HTTP simulado del protocolo de baliza CascoVision."""

import hmac
import json
import os
import random
import time
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Lock
from urllib.parse import urlsplit
from uuid import UUID

MAX_BODY = 1024
VIOLATIONS = {"missing_helmet", "missing_reflective_vest"}


class Receptor:
    def __init__(self, token, zone_id, zone_name, beacon_id, log_path,
                 delay_ms=0, fail_rate=0.0, battery_pct=87):
        if not token or len(token) < 32:
            raise ValueError("BALIZA_TOKEN debe tener al menos 32 caracteres")
        if delay_ms < 0 or not 0 <= fail_rate <= 1 or not 0 <= battery_pct <= 100:
            raise ValueError("Configuración de simulación fuera de rango")
        self.token = token
        self.zone_id = zone_id
        self.zone_name = zone_name[:20]
        self.beacon_id = beacon_id
        self.log_path = Path(log_path)
        self.delay_ms = delay_ms
        self.fail_rate = fail_rate
        self.battery_pct = battery_pct
        self.started = time.monotonic()
        self.lock = Lock()
        self.alerts = {}
        self.active_until = 0.0

    @classmethod
    def from_env(cls):
        try:
            return cls(
                os.getenv("BALIZA_TOKEN", ""),
                os.getenv("SIM_ZONE_ID", "zona-norte"),
                os.getenv("SIM_ZONE_NAME", "Zona Norte"),
                os.getenv("SIM_BEACON_ID", "baliza-01"),
                os.getenv("SIM_LOG_PATH", str(Path(__file__).with_name("alerts.jsonl"))),
                int(os.getenv("SIM_DELAY_MS", "0")),
                float(os.getenv("SIM_FAIL_RATE", "0")),
                int(os.getenv("SIM_BATTERY_PCT", "87")),
            )
        except ValueError as exc:
            raise ValueError(f"Configuración inválida del receptor: {exc}") from exc


class Handler(BaseHTTPRequestHandler):
    server_version = "CascoVisionBeacon/1.0"

    def log_message(self, *_):
        pass

    def _reply(self, code, payload=None):
        body = b"" if payload is None else json.dumps(payload).encode("utf-8")
        self.send_response(code)
        if payload is not None:
            self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        if body:
            self.wfile.write(body)

    def _simulate_response(self, receptor):
        if receptor.delay_ms:
            time.sleep(receptor.delay_ms / 1000)
        if receptor.fail_rate and random.random() < receptor.fail_rate:
            self.close_connection = True
            return True
        return False

    def do_GET(self):
        if urlsplit(self.path).path != "/health":
            return self._reply(404, {"error": "not_found"})
        r = self.server.receptor
        with r.lock:
            alerting = time.monotonic() < r.active_until
        health = {
            "status": "low_battery" if r.battery_pct < 15 else "ok",
            "protocol": "1",
            "beacon_id": r.beacon_id,
            "zone_id": r.zone_id,
            "firmware": "1.0.0",
            "battery_pct": r.battery_pct,
            "charging": False,
            "uptime_s": int(time.monotonic() - r.started),
            "rssi_dbm": -61,
            "alerting": alerting,
        }
        if not self._simulate_response(r):
            self._reply(200, health)

    def do_POST(self):
        if urlsplit(self.path).path != "/alert":
            return self._reply(404, {"error": "not_found"})
        try:
            size = int(self.headers.get("Content-Length", "-1"))
        except ValueError:
            return self._reply(400, {"error": "invalid_field", "field": "body"})
        if size < 0:
            return self._reply(400, {"error": "invalid_field", "field": "body"})
        if size > MAX_BODY:
            self.close_connection = True
            return self._reply(413)

        r = self.server.receptor
        authorization = self.headers.get("Authorization", "")
        if not authorization.startswith("Bearer ") or not hmac.compare_digest(
            authorization[7:], r.token
        ):
            return self._reply(401, {"error": "unauthorized"})
        if self.headers.get_content_type() != "application/json":
            return self._reply(400, {"error": "invalid_field", "field": "body"})
        try:
            order = json.loads(self.rfile.read(size))
        except (json.JSONDecodeError, UnicodeDecodeError):
            return self._reply(400, {"error": "invalid_field", "field": "body"})
        if not isinstance(order, dict):
            return self._reply(400, {"error": "invalid_field", "field": "body"})

        invalid = self._invalid_field(order)
        if invalid:
            return self._reply(400, {"error": "invalid_field", "field": invalid})
        if order["zone_id"] != r.zone_id:
            return self._reply(409, {"error": "wrong_zone", "zone_id": r.zone_id})

        now = time.monotonic()
        received = datetime.now().astimezone().isoformat()
        with r.lock:
            duplicate = order["alert_id"] in r.alerts
            r.alerts[order["alert_id"]] = True
            if not duplicate:
                r.active_until = now + order["duration_s"]
            r.log_path.parent.mkdir(parents=True, exist_ok=True)
            with r.log_path.open("a", encoding="utf-8") as log:
                log.write(json.dumps({"received_at": received, "order": order}, ensure_ascii=False) + "\n")
        if not self._simulate_response(r):
            self._reply(200, {"status": "alerting", "alert_id": order["alert_id"], "duplicate": duplicate})

    @staticmethod
    def _invalid_field(order):
        required = ("alert_id", "zone_id", "zone_name", "violations", "duration_s", "sent_at")
        if any(field not in order for field in required):
            return next(field for field in required if field not in order)
        try:
            UUID(order["alert_id"])
        except (ValueError, TypeError, AttributeError):
            return "alert_id"
        if not isinstance(order["zone_id"], str) or not order["zone_id"].strip():
            return "zone_id"
        if not isinstance(order["zone_name"], str) or len(order["zone_name"]) > 20:
            return "zone_name"
        violations = order["violations"]
        if (not isinstance(violations, list) or not 1 <= len(violations) <= 2
                or any(not isinstance(v, str) or v not in VIOLATIONS for v in violations)):
            return "violations"
        duration = order["duration_s"]
        if isinstance(duration, bool) or not isinstance(duration, int) or not 1 <= duration <= 30:
            return "duration_s"
        sound = order.get("sound", "siren")
        if not isinstance(sound, str) or sound not in {"siren", "voice", "beep"}:
            return "sound"
        if "message" in order and (not isinstance(order["message"], str) or len(order["message"]) > 40):
            return "message"
        if not isinstance(order["sent_at"], str):
            return "sent_at"
        try:
            sent_at = datetime.fromisoformat(order["sent_at"].replace("Z", "+00:00"))
        except ValueError:
            return "sent_at"
        if sent_at.utcoffset() is None:
            return "sent_at"
        return None


def crear_servidor(host=None, port=None, receptor=None):
    server = ThreadingHTTPServer(
        (host or os.getenv("SIM_HOST", "127.0.0.1"),
         int(port if port is not None else os.getenv("SIM_PORT", "8081"))),
        Handler,
    )
    server.receptor = receptor or Receptor.from_env()
    return server


if __name__ == "__main__":
    servidor = crear_servidor()
    print(f"Receptor simulado en http://{servidor.server_address[0]}:{servidor.server_address[1]}")
    try:
        servidor.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        servidor.server_close()
