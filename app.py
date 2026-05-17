#!/usr/bin/env python3
from __future__ import annotations

import argparse
import signal
import threading
from pathlib import Path
from typing import Any, Dict, Optional

import pyglet

from comms import Comms, TOPIC_UTTERANCE, TOPIC_STATE_UPDATE, TOPIC_TRANSCRIPT
from composer import Composer
from config import ConfigStore
from fireflight import Fireflight
from http_server import HttpServer
from models import Utterance, TranscriptEvent
from playback import PlaybackEngine
from speech import SpeechDetector
from visual import VisualEngine
from waver import Waver


class App:
    def __init__(
        self,
        config_path: str | Path | None = None,
        *,
        presets_dir: str | Path | None = None,
        host: str = "127.0.0.1",
        port: int = 8000,
        defaults: Optional[Dict[str, Any]] = None,
    ):
        self.config = ConfigStore(
            config_path=config_path,
            defaults=defaults,
            presets_dir=presets_dir,
        )
        self.comms = Comms()

        self.speech = SpeechDetector(self.config, self.comms)
        self.composer = Composer(self.config, self.comms)
        self.playback = PlaybackEngine(self.config, self.comms)
        self.visual = VisualEngine(
            self.config,
            self.comms,
            generator_factory=self.build_visual_generator,
        )

        self.http = HttpServer(
            self.config,
            host=host,
            port=port,
            status_provider=self.snapshot_status,
            stop_callback=self.stop,
            presets_dir=presets_dir,
            base_dir=Path(__file__).parent,
            utterance_callback=self.submit_text_utterance
        )

        self._http_thread: Optional[threading.Thread] = None
        self._lock = threading.RLock()
        self._running = False
        self._started = {
            "http": False,
            "speech": False,
            "composer": False,
            "playback": False,
            "visual": False,
        }

    def submit_text_utterance(self, text: str) -> None:
        text = text.strip()
        lines = text.split('\n')
        for text in lines:
            if not text:
                continue

            raw_words = [{"word": token} for token in text.split()]
            words = self.speech.enrich_words(raw_words)
            if not words:
                continue

            utterance = Utterance(
                text=text,
                words=words,
                audio=None,
            )
            self.comms.send(TOPIC_UTTERANCE, utterance)
            self.comms.send(
                TOPIC_TRANSCRIPT,
                TranscriptEvent(
                    text=text,
                    kind="final",
                    utterance_id=utterance.utterance_id,
                    words=words,
                ),
            )

            state_update = self.speech.update_state(words)
            if state_update is not None:
                self.comms.send(TOPIC_STATE_UPDATE, state_update)

    def build_visual_generator(self, name: str):
        name = str(name).lower()

        if name == "fireflight":
            return Fireflight(self.config)

        if name == "waver":
            return Waver(self.config)

        raise ValueError(f"Unknown visual generator: {name}")

    def start(self) -> None:
        with self._lock:
            if self._running:
                return
            self._running = True

        self.visual.start()
        self._started["visual"] = True

        self.http.start()
        self._http_thread = threading.Thread(target=self.http.serve_forever, daemon=True)
        self._http_thread.start()
        self._started["http"] = True

        self.speech.start()
        self._started["speech"] = True

        self.composer.start()
        self._started["composer"] = True

        self.playback.start()
        self._started["playback"] = True

    def stop(self) -> None:
        with self._lock:
            if not self._running:
                return
            self._running = False

        try:
            self.speech.stop()
        except Exception as e:
            print(f"[APP] Error stopping speech: {e}")

        try:
            self.composer.stop()
        except Exception as e:
            print(f"[APP] Error stopping composer: {e}")

        try:
            self.playback.stop()
        except Exception as e:
            print(f"[APP] Error stopping playback: {e}")

        try:
            self.visual.stop()
        except Exception as e:
            print(f"[APP] Error stopping visual: {e}")

        try:
            self.http.stop()
        except Exception as e:
            print(f"[APP] Error stopping http: {e}")

        try:
            pyglet.app.exit()
        except Exception:
            pass

    def run(self) -> None:
        self.start()

        try:
            pyglet.app.run()
        finally:
            self.stop()

    def snapshot_status(self) -> Dict[str, Any]:
        return {
            "running": self._running,
            "started": dict(self._started),
            "config": self.config.info(),
            "comms": self.comms.snapshot(),
            "visual_generator": self.visual.generator_name,
        }


def parse_args():
    parser = argparse.ArgumentParser(description="Audio-visual system")
    parser.add_argument("--config", default='presets/fireflight.json', help="Path to config JSON file")
    parser.add_argument("--presets-dir", default='presets', help="Directory for preset JSON files")
    parser.add_argument("--host", default="127.0.0.1", help="HTTP host")
    parser.add_argument("--port", type=int, default=8000, help="HTTP port")
    return parser.parse_args()


def main():
    args = parse_args()

    app = App(
        config_path=args.config,
        presets_dir=args.presets_dir,
        host=args.host,
        port=args.port,
    )

    def handle_signal(signum, frame):
        print(f"[APP] Received signal {signum}")
        app.stop()

    signal.signal(signal.SIGINT, handle_signal)
    signal.signal(signal.SIGTERM, handle_signal)

    app.run()


if __name__ == "__main__":
    main()