#!/usr/bin/env python3
from __future__ import annotations

import queue
import threading
import time
from typing import Any, Dict, List, Optional

import numpy as np
import sounddevice as sd
from pythonosc.udp_client import SimpleUDPClient

from comms import Comms, TOPIC_NOTE_EVENT
from config import ConfigStore
from models import NoteEvent


DEFAULTS: Dict[str, Any] = {
    "playback": {
        "sample_rate": 16000,
        "device_out": None,
        "block_size": 1024,
        "master_gain": 0.35,
        "fade_ms": 10,
        "queue_size": 256,
        "midi_out_only": True,
        "osc_midi_enabled": True,
        "osc_midi_host": "127.0.0.1",
        "osc_midi_port": 5001,
        "osc_midi_address": "/midi",
    }
}


class PlaybackEngine:
    def __init__(self, config: ConfigStore, comms: Comms):
        self.config = config
        self.comms = comms

        self.stop_event = threading.Event()
        self.thread: Optional[threading.Thread] = None
        self.note_queue: Optional[queue.Queue] = None

        self._voices_lock = threading.RLock()
        self._voices: List[Dict[str, Any]] = []

        self._osc_client: Optional[SimpleUDPClient] = None
        self._osc_host: Optional[str] = None
        self._osc_port: Optional[int] = None

    def _cfg(self) -> Dict[str, Any]:
        merged = dict(DEFAULTS["playback"])
        current = self.config.get("playback", {}) or {}
        merged.update(current)
        return merged

    def start(self) -> None:
        if self.thread is not None and self.thread.is_alive():
            return

        cfg = self._cfg()
        self.note_queue = self.comms.open_queue(
            TOPIC_NOTE_EVENT,
            maxsize=int(cfg["queue_size"]),
        )

        self.stop_event.clear()
        self.thread = threading.Thread(target=self.run, daemon=True)
        self.thread.start()

    def stop(self) -> None:
        self.stop_event.set()

    def close(self) -> None:
        if self.note_queue is not None:
            self.comms.close_queue(TOPIC_NOTE_EVENT, self.note_queue)
            self.note_queue = None

    def _ensure_osc_client(self) -> Optional[SimpleUDPClient]:
        cfg = self._cfg()

        if not bool(cfg["osc_midi_enabled"]):
            self._osc_client = None
            self._osc_host = None
            self._osc_port = None
            return None

        host = str(cfg["osc_midi_host"])
        port = int(cfg["osc_midi_port"])

        if self._osc_client is None or host != self._osc_host or port != self._osc_port:
            self._osc_client = SimpleUDPClient(host, port)
            self._osc_host = host
            self._osc_port = port

        return self._osc_client

    @staticmethod
    def midi_to_hz(note: int) -> float:
        return 440.0 * (2.0 ** ((int(note) - 69) / 12.0))

    def synth_note(self, note: int, velocity: int, duration: float) -> np.ndarray:
        cfg = self._cfg()
        sample_rate = int(cfg["sample_rate"])
        master_gain = float(cfg["master_gain"])
        fade_ms = int(cfg["fade_ms"])

        duration = max(0.02, float(duration))
        velocity = int(np.clip(int(velocity), 1, 127))
        freq_hz = self.midi_to_hz(note)

        length = max(1, int(duration * sample_rate))
        t = np.arange(length, dtype=np.float32) / sample_rate

        amp = master_gain * (velocity / 127.0)
        wave = amp * np.sin(2.0 * np.pi * freq_hz * t)

        fade_samples = min(int(sample_rate * fade_ms / 1000), length // 2)
        if fade_samples > 0:
            env = np.ones(length, dtype=np.float32)
            env[:fade_samples] *= np.linspace(0.0, 1.0, fade_samples)
            env[-fade_samples:] *= np.linspace(1.0, 0.0, fade_samples)
            wave *= env

        return wave.astype(np.float32)

    def add_voice(self, audio: np.ndarray) -> None:
        if len(audio) == 0:
            return

        with self._voices_lock:
            self._voices.append(
                {
                    "audio": audio,
                    "index": 0,
                }
            )

    def audio_callback(self, outdata, frames, time_info, status) -> None:
        if status:
            print(f"[PLAYBACK STATUS] {status}")

        out = np.zeros(frames, dtype=np.float32)

        with self._voices_lock:
            remaining_voices: List[Dict[str, Any]] = []

            for voice in self._voices:
                audio = voice["audio"]
                index = int(voice["index"])

                if index >= len(audio):
                    continue

                n = min(frames, len(audio) - index)
                out[:n] += audio[index:index + n]
                voice["index"] = index + n

                if voice["index"] < len(audio):
                    remaining_voices.append(voice)

            self._voices = remaining_voices

        peak = float(np.max(np.abs(out))) if len(out) else 0.0
        if peak > 1.0:
            out /= peak

        outdata[:, 0] = out

    def send_osc_midi(self, event: NoteEvent) -> None:
        client = self._ensure_osc_client()
        if client is None:
            return

        cfg = self._cfg()
        address = str(cfg["osc_midi_address"])

        channel = int(event.channel if event.channel is not None else (event.voice or 1))
        note = int(event.note)
        velocity = int(np.clip(event.velocity, 1, 127))
        duration = float(max(0.01, event.duration))

        payload = [channel, note, velocity, duration]

        try:
            client.send_message(address, payload)
            print(
                f"[MIDI OSC] ch={channel} note={note} velocity={velocity} "
                f"duration={duration:.3f}s word={event.word.text}"
            )
        except Exception as e:
            print(f"[MIDI OSC ERROR] {e}")

    def handle_note_event(self, event: NoteEvent) -> None:
        cfg = self._cfg()

        if bool(cfg["osc_midi_enabled"]):
            self.send_osc_midi(event)

        if bool(cfg["midi_out_only"]):
            return

        audio = self.synth_note(
            note=event.note,
            velocity=event.velocity,
            duration=event.duration,
        )
        self.add_voice(audio)

        print(
            f"[PLAYBACK] note={event.note} velocity={event.velocity} "
            f"duration={event.duration:.3f}s word={event.word.text}"
        )

    def _run_midi_only(self) -> None:
        print("[PLAYBACK] Running in MIDI-out-only mode...")

        while not self.stop_event.is_set():
            if self.note_queue is None:
                time.sleep(0.05)
                continue

            try:
                event = self.note_queue.get(timeout=0.05)
            except queue.Empty:
                continue

            if not isinstance(event, NoteEvent):
                continue

            self.handle_note_event(event)

    def _run_with_audio(self) -> None:
        cfg = self._cfg()

        with sd.OutputStream(
            samplerate=int(cfg["sample_rate"]),
            blocksize=int(cfg["block_size"]),
            device=cfg["device_out"],
            channels=1,
            dtype="float32",
            callback=self.audio_callback,
        ):
            print("[PLAYBACK] Running...")

            while not self.stop_event.is_set():
                if self.note_queue is None:
                    time.sleep(0.05)
                    continue

                try:
                    event = self.note_queue.get(timeout=0.05)
                except queue.Empty:
                    continue

                if not isinstance(event, NoteEvent):
                    continue

                self.handle_note_event(event)

    def run(self) -> None:
        try:
            if bool(self._cfg()["midi_out_only"]):
                self._run_midi_only()
            else:
                self._run_with_audio()
        finally:
            self.close()
            sd.stop()
            with self._voices_lock:
                self._voices.clear()
            print("[PLAYBACK] Stopped.")