#!/usr/bin/env python3
from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Callable, Dict, Optional
from urllib.parse import urlparse
import mimetypes

from config import ConfigStore


class HttpServer:
    def __init__(
        self,
        config_store: ConfigStore,
        *,
        host: str = "127.0.0.1",
        port: int = 8000,
        status_provider: Optional[Callable[[], Dict[str, Any]]] = None,
        stop_callback: Optional[Callable[[], None]] = None,
        presets_dir: str | Path | None = None,
        base_dir: str | Path | None = None,
        utterance_callback: Optional[Callable[[str], None]] = None,
    ):
        self.config_store = config_store
        self.host = host
        self.port = int(port)
        self.status_provider = status_provider or (lambda: {"ok": True})
        self.stop_callback = stop_callback
        self.presets_dir = Path(presets_dir).expanduser().resolve() if presets_dir else None
        self.utterance_callback = utterance_callback
        self.base_dir = Path(base_dir).expanduser().resolve() if base_dir else Path.cwd().resolve()
        self.index_file = self.base_dir / 'html' / "index.html"
        self.static_dir = self.base_dir / "static"

        self._httpd: Optional[ThreadingHTTPServer] = None

        if self.presets_dir is not None:
            self.config_store.set_presets_dir(self.presets_dir)

    def start(self) -> None:
        if self._httpd is not None:
            return

        server = self

        class RequestHandler(BaseHTTPRequestHandler):
            def _read_json(self) -> Dict[str, Any]:
                length = int(self.headers.get("Content-Length", "0"))
                if length <= 0:
                    return {}

                raw = self.rfile.read(length)
                if not raw:
                    return {}

                try:
                    data = json.loads(raw.decode("utf-8"))
                except json.JSONDecodeError as e:
                    raise ValueError(f"Invalid JSON body: {e}") from e

                if data is None:
                    return {}
                if not isinstance(data, dict):
                    raise ValueError("JSON body must be an object")

                return data

            def _send_json(self, status_code: int, payload: Dict[str, Any]) -> None:
                body = json.dumps(payload, indent=2, ensure_ascii=False).encode("utf-8")
                self.send_response(status_code)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def _send_file(self, file_path: Path) -> None:
                try:
                    file_path = file_path.resolve()
                    base_dir = server.base_dir.resolve()

                    if base_dir not in file_path.parents and file_path != base_dir:
                        self._send_json(403, {"error": "forbidden"})
                        return

                    if not file_path.is_file():
                        self._send_json(404, {"error": "file not found"})
                        return

                    body = file_path.read_bytes()
                    content_type = mimetypes.guess_type(str(file_path))[0] or "application/octet-stream"

                    self.send_response(200)
                    self.send_header("Content-Type", content_type)
                    self.send_header("Content-Length", str(len(body)))
                    self.end_headers()
                    self.wfile.write(body)

                except Exception as e:
                    self._send_json(500, {"error": str(e)})

            def _not_found(self) -> None:
                self._send_json(404, {"error": "not found"})

            def _ok(self, payload: Optional[Dict[str, Any]] = None) -> None:
                self._send_json(200, payload or {"ok": True})

            def do_GET(self) -> None:
                parsed = urlparse(self.path)
                path = parsed.path

                try:
                    if path in ("/", "/panel"):
                        self._send_file(server.index_file)
                        return

                    if path.startswith("/static/"):
                        rel_path = path.removeprefix("/static/")
                        self._send_file(server.static_dir / rel_path)
                        return

                    if path == "/health":
                        self._ok({"ok": True})
                        return

                    if path == "/status":
                        self._ok(server.status_provider())
                        return

                    if path == "/config":
                        self._ok(
                            {
                                "config": server.config_store.snapshot(),
                                "info": server.config_store.info(),
                            }
                        )
                        return

                    if path == "/presets":
                        self._ok({"presets": server.config_store.list_presets()})
                        return

                    if path == "/writer":
                        self._send_file(server.base_dir / 'html' /"writer.html")
                        return

                    self._not_found()

                except Exception as e:
                    self._send_json(500, {"error": str(e)})

            def do_POST(self) -> None:
                parsed = urlparse(self.path)
                path = parsed.path

                try:
                    if path == "/stop":
                        if server.stop_callback is not None:
                            server.stop_callback()
                        self._ok({"stopping": True})
                        return

                    if path == "/config/set":
                        data = self._read_json()
                        key = data.get("key")
                        value = data.get("value")

                        if not isinstance(key, str) or not key.strip():
                            self._send_json(400, {"error": "Body must include non-empty string key"})
                            return

                        server.config_store.set(key, value)
                        self._ok({"config": server.config_store.snapshot()})
                        return

                    if path == "/config/update":
                        data = self._read_json()
                        values = data.get("values", data)
                        merge = bool(data.get("merge", True))

                        if not isinstance(values, dict):
                            self._send_json(400, {"error": "Body must include object values"})
                            return

                        server.config_store.update(values, merge=merge)
                        self._ok({"config": server.config_store.snapshot()})
                        return

                    if path == "/config/save":
                        data = self._read_json()
                        path_value = data.get("path")
                        saved_path = server.config_store.save(path_value)
                        self._ok({"saved_to": str(saved_path)})
                        return

                    if path == "/preset/save":
                        data = self._read_json()
                        name = data.get("name")
                        if not isinstance(name, str) or not name.strip():
                            self._send_json(400, {"error": "Body must include non-empty preset name"})
                            return

                        saved_path = server.config_store.save_preset(name)
                        self._ok({"saved_to": str(saved_path), "preset": name})
                        return


                    if path == "/preset/load":
                        data = self._read_json()
                        name = data.get("name")
                        if not isinstance(name, str) or not name.strip():
                            self._send_json(400, {"error": "Body must include non-empty preset name"})
                            return

                        server.config_store.load_preset(name)

                        self._ok({
                            "preset": name,
                            "config": server.config_store.snapshot(),
                            "info": server.config_store.info(),
                        })
                        return

                    if path == "/preset/save-current":
                        saved_path = server.config_store.save_to_current_preset()
                        self._ok({"saved_to": str(saved_path)})
                        return

                    if path == "/utterance":
                        data = self._read_json()
                        text = (data.get("text") or "").strip()

                        if not text:
                            self._send_json(400, {"error": "Body must include non-empty text"})
                            return

                        if server.utterance_callback is None:
                            self._send_json(500, {"error": "utterance callback not configured"})
                            return

                        server.utterance_callback(text)
                        self._ok({"ok": True, "text": text})
                        return
                    self._not_found()

                except ValueError as e:
                    self._send_json(400, {"error": str(e)})
                except Exception as e:
                    self._send_json(500, {"error": str(e)})

            def log_message(self, format: str, *args: Any) -> None:
                print(f"[HTTP] {self.address_string()} - {format % args}")

        self._httpd = ThreadingHTTPServer((self.host, self.port), RequestHandler)
        print(f"[HTTP] Listening on http://{self.host}:{self.port}")

    def serve_forever(self) -> None:
        if self._httpd is None:
            self.start()
        assert self._httpd is not None
        self._httpd.serve_forever()

    def stop(self) -> None:
        if self._httpd is None:
            return

        try:
            self._httpd.shutdown()
            self._httpd.server_close()
        finally:
            self._httpd = None