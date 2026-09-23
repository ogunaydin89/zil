"""Local control-panel server.

Binds to 127.0.0.1 only. The page is just a view onto the engine - bells ring
whether or not it is open.

Mutating requests must carry the session token that the server injects into the
page at load time. Without it, any other page in the browser could POST to
localhost and ring the school bell.
"""
import json
import mimetypes
import os
import secrets
import threading
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from . import store

UI_DIR = os.path.join(store.ROOT, "ui")
TOKEN = secrets.token_urlsafe(24)


class Api:
    """Wired up by app.py; holds the live engine + scheduler."""
    engine = None
    scheduler = None
    settings = None
    schedule = None
    reload_cb = None
    in_app = False          # True when the UI is hosted in the native window


def _iso(dt):
    return dt.isoformat(timespec="seconds") if dt else None


class Handler(BaseHTTPRequestHandler):
    server_version = "Zil"

    def log_message(self, *args):
        pass                                        # keep the console quiet

    # ---- helpers -----------------------------------------------------

    def _send(self, code, body, ctype="application/json; charset=utf-8"):
        if isinstance(body, (dict, list)):
            body = json.dumps(body, ensure_ascii=False).encode("utf-8")
        elif isinstance(body, str):
            body = body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        try:
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionAbortedError):
            pass

    def _body(self):
        try:
            n = int(self.headers.get("Content-Length") or 0)
            return json.loads(self.rfile.read(n) or b"{}")
        except (ValueError, TypeError):
            return {}

    def _authorised(self):
        return secrets.compare_digest(self.headers.get("X-Zil-Token", ""), TOKEN)

    # ---- routes ------------------------------------------------------

    def do_GET(self):
        path = self.path.split("?", 1)[0]

        if path == "/" or path == "/index.html":
            return self._serve_index()
        if path == "/api/state":
            return self._send(200, self._state())
        if path == "/api/settings":
            return self._send(200, Api.settings)
        if path == "/api/schedule":
            return self._send(200, Api.schedule)
        if path == "/api/audio-files":
            return self._send(200, store.list_audio_files())
        if path == "/api/log":
            return self._send(200, store.read_log(300))
        return self._serve_static(path)

    def do_POST(self):
        path = self.path.split("?", 1)[0]
        if not self._authorised():
            return self._send(403, {"error": "bad or missing token"})

        body = self._body()

        if path == "/api/play":
            key = body.get("key", "")
            if key not in store.SOUND_KINDS:
                return self._send(400, {"error": "unknown sound key"})
            ok, msg = Api.engine.play(key, Api.settings, source="manual")
            return self._send(200, {"ok": ok, "message": msg, **self._state()})

        if path == "/api/stop":
            Api.engine.stop_all()
            return self._send(200, {"ok": True, **self._state()})

        if path == "/api/settings":
            merged = dict(Api.settings)
            merged.update(body or {})
            vols = merged.get("volumes") or {}
            merged["volumes"] = {k: store.clamp_volume(vols.get(k), 100)
                                 for k in ("bell", "ceremony", "emergency")}
            store.save_settings(merged)
            Api.reload_cb()
            return self._send(200, {"ok": True, "settings": Api.settings})

        if path == "/api/schedule":
            if not isinstance(body.get("weekly"), dict):
                return self._send(400, {"error": "schedule.weekly must be an object"})
            store.save_schedule(body)
            Api.reload_cb()
            return self._send(200, {"ok": True, "schedule": Api.schedule})

        return self._send(404, {"error": "no such endpoint"})

    # ---- payloads ----------------------------------------------------

    def _state(self):
        now = datetime.now()
        nxt = Api.scheduler.next_event(now) if Api.scheduler else None
        events = Api.scheduler.todays_events(now) if Api.scheduler else []
        sch = Api.schedule or {}
        holiday = None
        if Api.scheduler:
            from .scheduler import holiday_for
            holiday = holiday_for(sch, now.date())
        return {
            "now": _iso(now),
            "today": now.strftime("%A"),
            "audio": Api.engine.status() if Api.engine else {},
            "enabled": bool((Api.settings or {}).get("enabled", True)),
            "school_name": (Api.settings or {}).get("school_name", ""),
            "language": (Api.settings or {}).get("language", "tr"),
            "holiday": holiday,
            "next": ({"when": _iso(nxt["when"]), "time": nxt["time"],
                      "key": nxt["key"], "source": nxt["source"],
                      "name": nxt.get("name", "")} if nxt else None),
            "today_events": [{"time": e["time"], "key": e["key"],
                              "lesson": e.get("lesson"), "source": e["source"],
                              "past": e["when"] <= now}
                             for e in events],
            "last_tick": _iso(Api.scheduler.last_tick) if Api.scheduler else None,
        }

    def _serve_index(self):
        path = os.path.join(UI_DIR, "index.html")
        try:
            html = open(path, encoding="utf-8").read()
        except OSError:
            return self._send(500, "ui/index.html missing", "text/plain; charset=utf-8")
        html = html.replace("__ZIL_TOKEN__", TOKEN)
        html = html.replace("__ZIL_IN_APP__", "true" if Api.in_app else "false")
        return self._send(200, html, "text/html; charset=utf-8")

    def _serve_static(self, path):
        rel = path.lstrip("/").replace("\\", "/")
        full = os.path.normpath(os.path.join(UI_DIR, rel))
        if not full.startswith(os.path.normpath(UI_DIR)) or not os.path.isfile(full):
            return self._send(404, "not found", "text/plain; charset=utf-8")
        ctype = mimetypes.guess_type(full)[0] or "application/octet-stream"
        if ctype.startswith("text/") or ctype.endswith("javascript"):
            ctype += "; charset=utf-8"
        with open(full, "rb") as fh:
            return self._send(200, fh.read(), ctype)


def start(port):
    """Bind to loopback. Returns (httpd, actual_port)."""
    for candidate in [port] + [port + i for i in range(1, 20)]:
        try:
            httpd = ThreadingHTTPServer(("127.0.0.1", candidate), Handler)
        except OSError:
            continue
        threading.Thread(target=httpd.serve_forever, daemon=True,
                         name="zil-http").start()
        return httpd, candidate
    raise OSError("no free port near %d" % port)


def url(port):
    return "http://127.0.0.1:%d/?t=%s" % (port, TOKEN)
