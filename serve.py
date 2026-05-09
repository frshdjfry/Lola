#!/usr/bin/env python3
import argparse
import csv
import json
import signal
import threading
import bisect
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pyglet

from echorus import UtteranceShuffler
from fireflight import DustScene
import mimetypes
from pathlib import Path
from urllib.parse import urlparse

HOST = "127.0.0.1"
PORT = 8000
BASE_DIR = Path(__file__).parent
STATIC_DIR = Path("./static")

CONFIG = {
    "midi_out_only": False,
    "midi_osc_host": "127.0.0.1",
    "midi_osc_port": 9001,
    "midi_osc_address": "/midi",
    "glasgow_csv": str(BASE_DIR / "glasgow.csv"),
}

WORD_NORMS = {}


def load_glasgow_norms(csv_path: Path) -> dict:
    """
    Load Glasgow word norms CSV into a dict keyed by lowercase word.
    Expected columns:
      word, arousal_mean, valence_mean, dominance_mean, concreteness_mean,
      imageability_mean, familiarity_mean, age_of_acquisition_mean,
      size_mean, gender_mean
    """
    norms = {}

    if not csv_path.exists():
        print(f"[NORMS] CSV not found: {csv_path}")
        return norms

    with csv_path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)

        for row in reader:
            word = (row.get("word") or "").strip().lower()
            if not word:
                continue

            parsed = {"word": word}
            for key, value in row.items():
                if key == "word":
                    continue
                if value is None or value == "":
                    parsed[key] = None
                    continue
                try:
                    parsed[key] = float(value)
                except ValueError:
                    parsed[key] = None

            norms[word] = parsed

    norms = add_percentiles(norms)

    print(f"[NORMS] Loaded {len(norms)} words from {csv_path}")
    return norms


def add_percentiles(norms: dict) -> dict:
    """
    Adds percentile fields for each numeric Glasgow column.
    Percentiles are in [0, 1].
    """
    if not norms:
        return norms

    numeric_columns = [
        "arousal_mean",
        "valence_mean",
        "dominance_mean",
        "concreteness_mean",
        "imageability_mean",
        "familiarity_mean",
        "age_of_acquisition_mean",
        "size_mean",
        "gender_mean",
    ]

    sorted_values_by_col = {}
    for col in numeric_columns:
        vals = [
            row[col]
            for row in norms.values()
            if row.get(col) is not None
        ]
        vals.sort()
        sorted_values_by_col[col] = vals

    for row in norms.values():
        for col in numeric_columns:
            value = row.get(col)
            pct_key = col.replace("_mean", "_pct")

            vals = sorted_values_by_col[col]
            if value is None or not vals:
                row[pct_key] = None
                continue

            # percentile rank using midpoint of ties
            left = bisect.bisect_left(vals, value)
            right = bisect.bisect_right(vals, value)
            rank = (left + right) / 2.0

            if len(vals) == 1:
                pct = 0.5
            else:
                pct = rank / len(vals)

            row[pct_key] = int(min(1.0, max(0.0, pct))*100)

    return norms


class AppState:
    def __init__(self):
        self.lock = threading.Lock()
        self.running = True
        self.speech_started = False
        self.visual_started = False
        self.http_started = False

    def snapshot(self):
        with self.lock:
            return {
                "running": self.running,
                "speech_started": self.speech_started,
                "visual_started": self.visual_started,
                "http_started": self.http_started,
                "midi_out_only": CONFIG["midi_out_only"],
                "midi_osc_host": CONFIG["midi_osc_host"],
                "midi_osc_port": CONFIG["midi_osc_port"],
                "midi_osc_address": CONFIG["midi_osc_address"],
                "glasgow_csv": CONFIG["glasgow_csv"],
                "glasgow_words_loaded": len(WORD_NORMS),
            }


STATE = AppState()
SPEECH_APP = None
VISUAL_APP = None
HTTPD = None


class RequestHandler(BaseHTTPRequestHandler):
    def _send_json(self, status_code: int, payload: dict):
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_file(self, file_path: Path):
        try:
            safe_root = BASE_DIR.resolve()
            file_path = file_path.resolve()

            if safe_root not in file_path.parents and file_path != safe_root:
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

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path

        if path == "/":
            self._send_file(BASE_DIR / "index.html")
            return

        if path == "/panel":
            self._send_file(BASE_DIR / "index.html")
            return

        if path in ["/static/styles.css", "/static/app.js"]:
            self._send_file(BASE_DIR / path.lstrip("/"))
            return

        if path == "/health":
            self._send_json(200, {"ok": True})
            return

        if path == "/status":
            self._send_json(200, STATE.snapshot())
            return

        self._send_json(404, {"error": "not found"})

    def do_POST(self):
        global HTTPD

        if self.path == "/stop":
            self._send_json(200, {"stopping": True})
            shutdown_all()
            return

        self._send_json(404, {"error": "not found"})

    def log_message(self, format, *args):
        print(f"[HTTP] {self.address_string()} - {format % args}")


def run_http_server():
    global HTTPD

    HTTPD = ThreadingHTTPServer((HOST, PORT), RequestHandler)

    with STATE.lock:
        STATE.http_started = True

    print(f"[HTTP] Listening on http://{HOST}:{PORT}")
    HTTPD.serve_forever()


def run_speech_app():
    global SPEECH_APP

    SPEECH_APP = UtteranceShuffler(
        midi_out_only=CONFIG["midi_out_only"],
        midi_osc_host=CONFIG["midi_osc_host"],
        midi_osc_port=CONFIG["midi_osc_port"],
        midi_osc_address=CONFIG["midi_osc_address"],
        word_norms=WORD_NORMS,
    )

    with STATE.lock:
        STATE.speech_started = True

    print("[SPEECH] Starting speech app thread...")
    try:
        SPEECH_APP.run()
    except Exception as e:
        print(f"[SPEECH ERROR] {e}")
    finally:
        print("[SPEECH] Speech app stopped.")


def shutdown_all():
    global HTTPD, SPEECH_APP

    with STATE.lock:
        if not STATE.running:
            return
        STATE.running = False

    print("[MAIN] Shutting down...")

    if SPEECH_APP is not None:
        try:
            SPEECH_APP.stop_event.set()
            SPEECH_APP.gate_open = False
        except Exception as e:
            print(f"[MAIN] Error stopping speech app: {e}")

    if HTTPD is not None:
        try:
            threading.Thread(target=HTTPD.shutdown, daemon=True).start()
        except Exception as e:
            print(f"[MAIN] Error stopping HTTP server: {e}")

    try:
        pyglet.app.exit()
    except Exception as e:
        print(f"[MAIN] Error stopping pyglet: {e}")


def handle_signal(signum, frame):
    print(f"[MAIN] Received signal {signum}")
    shutdown_all()


def parse_args():
    parser = argparse.ArgumentParser(description="Lola audio-visual reactive installation")

    parser.add_argument(
        "--midi-out-only",
        action="store_true",
        help="Disable local audio playback and send generated notes over OSC only.",
    )

    parser.add_argument(
        "--midi-osc-host",
        default="127.0.0.1",
        help="OSC host for MIDI output.",
    )

    parser.add_argument(
        "--midi-osc-port",
        type=int,
        default=9001,
        help="OSC port for MIDI output.",
    )

    parser.add_argument(
        "--midi-osc-address",
        default="/midi",
        help="OSC address for MIDI output.",
    )

    parser.add_argument(
        "--glasgow-csv",
        default=str(BASE_DIR / "glasgow.csv"),
        help="Path to Glasgow norms CSV.",
    )

    return parser.parse_args()


def main():
    global VISUAL_APP, WORD_NORMS

    args = parse_args()

    CONFIG["midi_out_only"] = args.midi_out_only
    CONFIG["midi_osc_host"] = args.midi_osc_host
    CONFIG["midi_osc_port"] = args.midi_osc_port
    CONFIG["midi_osc_address"] = args.midi_osc_address
    CONFIG["glasgow_csv"] = args.glasgow_csv

    WORD_NORMS = load_glasgow_norms(Path(CONFIG["glasgow_csv"]))

    print("[CONFIG] midi_out_only =", CONFIG["midi_out_only"])
    print(
        "[CONFIG] midi OSC = "
        f"{CONFIG['midi_osc_host']}:{CONFIG['midi_osc_port']}"
        f"{CONFIG['midi_osc_address']}"
    )
    print("[CONFIG] glasgow_csv =", CONFIG["glasgow_csv"])
    print("[CONFIG] glasgow_words_loaded =", len(WORD_NORMS))

    signal.signal(signal.SIGINT, handle_signal)
    signal.signal(signal.SIGTERM, handle_signal)

    speech_thread = threading.Thread(target=run_speech_app, daemon=True)
    http_thread = threading.Thread(target=run_http_server, daemon=True)

    speech_thread.start()
    http_thread.start()

    print("[VISUAL] Starting DustScene on main thread...")
    VISUAL_APP = DustScene()

    with STATE.lock:
        STATE.visual_started = True

    pyglet.app.run()

    print("[VISUAL] Pyglet app exited.")
    shutdown_all()


if __name__ == "__main__":
    main()