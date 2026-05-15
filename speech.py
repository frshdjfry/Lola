#!/usr/bin/env python3
from __future__ import annotations

import csv
import json
import queue
import threading
import time
import bisect
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np
import sounddevice as sd
from vosk import KaldiRecognizer, Model

from comms import Comms, TOPIC_UTTERANCE, TOPIC_STATE_UPDATE
from config import ConfigStore
from models import StateUpdate, Utterance, Word

from nltk.corpus import stopwords as nltk_stopwords

STOP_WORDS = set(nltk_stopwords.words("english") + ["hm"])


DEFAULTS: Dict[str, Any] = {
    "speech": {
        "model_path": "./vosk-model/vosk-model",
        "sample_rate": 16000,
        "channels": 1,
        "dtype": "int16",
        "block_size": 4000,
        "device_in": None,
        "min_partial_chars": 1,
        "short_pause_sec": 0.005,
        "audio_queue_max_chunks": 256,
        "glasgow_csv": "./glasgow.csv",
    }
}


def add_percentiles(norms: Dict[str, Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
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

    sorted_values_by_col: Dict[str, List[float]] = {}
    for col in numeric_columns:
        vals = [row[col] for row in norms.values() if row.get(col) is not None]
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

            left = bisect.bisect_left(vals, value)
            right = bisect.bisect_right(vals, value)
            rank = (left + right) / 2.0

            if len(vals) == 1:
                pct = 0.5
            else:
                pct = rank / len(vals)

            row[pct_key] = round(float(min(1.0, max(0.0, pct))), 3)

    return norms


def load_glasgow_norms(csv_path: str | Path) -> Dict[str, Dict[str, Any]]:
    path = Path(csv_path)
    norms: Dict[str, Dict[str, Any]] = {}

    if not path.exists():
        print(f"[NORMS] CSV not found: {path}")
        return norms

    with path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)

        for row in reader:
            word = (row.get("word") or "").strip().lower()
            if not word:
                continue

            parsed: Dict[str, Any] = {"word": word}
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

    add_percentiles(norms)
    print(f"[NORMS] Loaded {len(norms)} words from {path}")
    return norms


class SpeechDetector:
    def __init__(self, config: ConfigStore, comms: Comms):
        self.config = config
        self.comms = comms

        cfg = self._cfg()
        self.sample_rate = int(cfg["sample_rate"])
        self.channels = int(cfg["channels"])
        self.dtype = str(cfg["dtype"])
        self.block_size = int(cfg["block_size"])
        self.device_in = cfg["device_in"]
        self.min_partial_chars = int(cfg["min_partial_chars"])
        self.short_pause_sec = float(cfg["short_pause_sec"])

        self.audio_queue: queue.Queue[bytes] = queue.Queue(
            maxsize=int(cfg["audio_queue_max_chunks"])
        )
        self.stop_event = threading.Event()
        self.thread: Optional[threading.Thread] = None

        self.word_norms = load_glasgow_norms(cfg["glasgow_csv"])
        self.model = Model(str(cfg["model_path"]))

        self.global_utterance_count = 0
        self.global_arousal_sum = 0.0
        self.global_valence_sum = 0.0
        self.global_dominance_sum = 0.0

    def _cfg(self) -> Dict[str, Any]:
        merged = dict(DEFAULTS["speech"])
        current = self.config.get("speech", {}) or {}
        merged.update(current)
        return merged

    def start(self) -> None:
        if self.thread is not None and self.thread.is_alive():
            return

        self.stop_event.clear()
        self.thread = threading.Thread(target=self.run, daemon=True)
        self.thread.start()

    def stop(self) -> None:
        self.stop_event.set()

    def audio_callback(self, indata, frames, time_info, status) -> None:
        if status:
            print(status)

        if self.stop_event.is_set():
            return

        try:
            self.audio_queue.put_nowait(bytes(indata))
        except queue.Full:
            try:
                _ = self.audio_queue.get_nowait()
            except queue.Empty:
                pass

            try:
                self.audio_queue.put_nowait(bytes(indata))
            except queue.Full:
                pass

    def new_recognizer(self) -> KaldiRecognizer:
        rec = KaldiRecognizer(self.model, self.sample_rate)
        rec.SetWords(True)
        return rec

    def wait_for_utterance(self) -> Optional[tuple[np.ndarray, list]]:
        recognizer = self.new_recognizer()

        utterance_started = False
        buffered_chunks: List[bytes] = []
        last_partial = ""
        last_speech_time: Optional[float] = None

        while not self.stop_event.is_set():
            try:
                data = self.audio_queue.get(timeout=0.05)
            except queue.Empty:
                data = None

            now = time.perf_counter()

            if data is not None:
                buffered_chunks.append(data)
                recognizer.AcceptWaveform(data)

                partial_result = json.loads(recognizer.PartialResult())
                partial = partial_result.get("partial", "").strip()

                if partial and len(partial) >= self.min_partial_chars:
                    if not utterance_started:
                        utterance_started = True
                        print(f"\n[UTTERANCE START] {partial}")
                    elif partial != last_partial:
                        print(f"\r[LISTENING] {partial}", end="", flush=True)

                    last_speech_time = now

                last_partial = partial

            if utterance_started and last_speech_time is not None:
                if now - last_speech_time >= self.short_pause_sec:
                    full_audio_bytes = b"".join(buffered_chunks)
                    audio = np.frombuffer(full_audio_bytes, dtype=np.int16).copy()

                    result = json.loads(recognizer.FinalResult())
                    words = result.get("result", [])
                    text = result.get("text", "").strip()

                    if text and words:
                        print(f"\n[UTTERANCE END] {text}")
                        return audio, words

                    recognizer = self.new_recognizer()
                    utterance_started = False
                    buffered_chunks = []
                    last_partial = ""
                    last_speech_time = None

        return None

    def get_word_norms(self, word: str) -> Optional[Dict[str, Any]]:
        return self.word_norms.get(word.lower())

    def get_word_feature_pct(self, word: str, feature: str, default: float = 0.5) -> float:
        norms = self.get_word_norms(word)
        if norms is None:
            return default

        for key in (f"{feature}_pct", feature):
            value = norms.get(key)
            if value is not None:
                return float(np.clip(value, 0.0, 1.0))

        return default

    def enrich_words(self, raw_words: list) -> List[Word]:
        words: List[Word] = []

        for item in raw_words:
            text = (item.get("word") or "").strip()
            if not text:
                continue

            features = self.get_word_norms(text) or {}

            words.append(
                Word(
                    text=text,
                    features=dict(features),
                )
            )

        return words

    def update_state(self, words: List[Word]) -> Optional[StateUpdate]:
        filtered = []
        for word in words:
            text = word.text.strip().lower()
            if not text or text in STOP_WORDS:
                continue
            filtered.append(text)

        if not filtered:
            return None

        arousal_vals = []
        valence_vals = []
        dominance_vals = []

        for text in filtered:
            if self.get_word_norms(text) is None:
                continue

            arousal_vals.append(self.get_word_feature_pct(text, "arousal"))
            valence_vals.append(self.get_word_feature_pct(text, "valence"))
            dominance_vals.append(self.get_word_feature_pct(text, "dominance"))

        if not arousal_vals and not valence_vals and not dominance_vals:
            return None

        utterance_arousal = float(np.mean(arousal_vals)) if arousal_vals else self.get_global_arousal()
        utterance_valence = float(np.mean(valence_vals)) if valence_vals else self.get_global_valence()
        utterance_dominance = float(np.mean(dominance_vals)) if dominance_vals else self.get_global_dominance()

        self.global_utterance_count += 1
        self.global_arousal_sum += utterance_arousal
        self.global_valence_sum += utterance_valence
        self.global_dominance_sum += utterance_dominance

        return StateUpdate(
            values={
                "global_arousal": self.get_global_arousal(),
                "global_valence": self.get_global_valence(),
                "global_dominance": self.get_global_dominance(),
            },
            source="speech",
        )

    def get_global_arousal(self) -> float:
        if self.global_utterance_count <= 0:
            return 0.5
        return float(np.clip(self.global_arousal_sum / self.global_utterance_count, 0.0, 1.0))

    def get_global_valence(self) -> float:
        if self.global_utterance_count <= 0:
            return 0.5
        return float(np.clip(self.global_valence_sum / self.global_utterance_count, 0.0, 1.0))

    def get_global_dominance(self) -> float:
        if self.global_utterance_count <= 0:
            return 0.5
        return float(np.clip(self.global_dominance_sum / self.global_utterance_count, 0.0, 1.0))

    def run(self) -> None:
        print("[SPEECH] Loading model...")
        print("[SPEECH] Running...")

        try:
            with sd.RawInputStream(
                samplerate=self.sample_rate,
                blocksize=self.block_size,
                dtype=self.dtype,
                channels=self.channels,
                callback=self.audio_callback,
                device=self.device_in,
            ):
                while not self.stop_event.is_set():
                    result = self.wait_for_utterance()
                    if result is None:
                        continue

                    utterance_audio, raw_words = result
                    words = self.enrich_words(raw_words)
                    if not words:
                        continue

                    utterance_text = " ".join(word.text for word in words)

                    utterance = Utterance(
                        text=utterance_text,
                        words=words,
                        audio=utterance_audio,
                    )
                    self.comms.send(TOPIC_UTTERANCE, utterance)

                    state_update = self.update_state(words)
                    if state_update is not None:
                        self.comms.send(TOPIC_STATE_UPDATE, state_update)

        except KeyboardInterrupt:
            self.stop_event.set()
        finally:
            sd.stop()
            print("[SPEECH] Stopped.")
