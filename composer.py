#!/usr/bin/env python3
from __future__ import annotations

import math
import queue
import random
import threading
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import numpy as np
from music_creatingrhythms import Rhythms

from comms import (
    Comms,
    TOPIC_NOTE_EVENT,
    TOPIC_STATE_UPDATE,
    TOPIC_UTTERANCE,
    TOPIC_VISUAL_EVENT,
)
from config import ConfigStore
from models import NoteEvent, StateUpdate, Utterance, VisualEvent, Word
from nltk.corpus import stopwords as nltk_stopwords

STOP_WORDS = set(nltk_stopwords.words("english") + ["hm"])


MODE_INTERVALS = {
    "ionian":     [0, 2, 4, 5, 7, 9, 11, 12],
    "dorian":     [0, 2, 3, 5, 7, 9, 10, 12],
    "phrygian":   [0, 1, 3, 5, 7, 8, 10, 12],
    "lydian":     [0, 2, 4, 6, 7, 9, 11, 12],
    "mixolydian": [0, 2, 4, 5, 7, 9, 10, 12],
    "aeolian":    [0, 2, 3, 5, 7, 8, 10, 12],
    "locrian":    [0, 1, 3, 5, 6, 8, 10, 12],
}

MODE_NAMES = list(MODE_INTERVALS.keys())

DEFAULTS: Dict[str, Any] = {
    "composer": {
        "bpm": 120,
        "bar_beats": 4,
        "max_voices": 4,
        "rotate_patterns": True,
        "step_size_choices": [2, 4, 6],
        "decay_per_hit": 0.50,
        "min_gain": 0.05,
        "visual_x_range": [-6.0, 6.0],
        "visual_y_range": [-1.0, 1.0],
        "visual_z_range": [-1.5, 1.5],
        "event_duration_scale": 0.9,
        "event_min_duration": 0.05,
        "default_word_duration": 0.2,
        "replacements_per_bar": 2,
        "tonic_midi": 57,
    }
}

MODE_NAMES = list(MODE_INTERVALS.keys())

@dataclass
class WordSlice:
    word: Word
    duration: float
    midi_note: Optional[int] = None
    mode_name: Optional[str] = None


class Composer:
    def __init__(self, config: ConfigStore, comms: Comms):
        self.config = config
        self.comms = comms

        self.stop_event = threading.Event()
        self.thread: Optional[threading.Thread] = None

        self.utterance_queue: Optional[queue.Queue] = None
        self.state_queue: Optional[queue.Queue] = None

        self.state_values: Dict[str, float] = {
            "global_arousal": 0.5,
            "global_valence": 0.5,
            "global_dominance": 0.5,
        }

    def _cfg(self) -> Dict[str, Any]:
        merged = dict(DEFAULTS["composer"])
        current = self.config.get("composer", {}) or {}
        merged.update(current)
        return merged

    def start(self) -> None:
        if self.thread is not None and self.thread.is_alive():
            return

        self.stop_event.clear()
        self.utterance_queue = self.comms.open_queue(TOPIC_UTTERANCE, maxsize=32)
        self.state_queue = self.comms.open_queue(TOPIC_STATE_UPDATE, maxsize=128)
        self.thread = threading.Thread(target=self.run, daemon=True)
        self.thread.start()

    def stop(self) -> None:
        self.stop_event.set()

    def close(self) -> None:
        if self.utterance_queue is not None:
            self.comms.close_queue(TOPIC_UTTERANCE, self.utterance_queue)
            self.utterance_queue = None

        if self.state_queue is not None:
            self.comms.close_queue(TOPIC_STATE_UPDATE, self.state_queue)
            self.state_queue = None

    def run(self) -> None:
        print("[COMPOSER] Running...")

        try:
            while not self.stop_event.is_set():
                self._drain_state_updates()

                if self.utterance_queue is None:
                    time.sleep(0.05)
                    continue

                try:
                    utterance = self.utterance_queue.get(timeout=0.05)
                except queue.Empty:
                    continue

                if not isinstance(utterance, Utterance):
                    continue

                threading.Thread(
                    target=self.compose_and_emit,
                    args=(utterance,),
                    daemon=True,
                ).start()
        finally:
            self.close()
            print("[COMPOSER] Stopped.")

    def _drain_state_updates(self) -> None:
        if self.state_queue is None:
            return

        while True:
            try:
                update = self.state_queue.get_nowait()
            except queue.Empty:
                break

            if isinstance(update, StateUpdate):
                for key, value in update.values.items():
                    try:
                        self.state_values[key] = float(value)
                    except (TypeError, ValueError):
                        continue

    def compose_and_emit(self, utterance: Utterance) -> None:
        word_slices = self.prepare_word_slices(utterance)
        if not word_slices:
            return

        schedule = self.build_schedule(word_slices, utterance)

        started_at = time.perf_counter()
        for item in schedule:
            if self.stop_event.is_set():
                return

            target = started_at + item["offset_sec"]
            while True:
                now = time.perf_counter()
                remaining = target - now
                if remaining <= 0:
                    break
                time.sleep(min(remaining, 0.002))

            self.comms.send(TOPIC_VISUAL_EVENT, item["visual_event"])
            self.comms.send(TOPIC_NOTE_EVENT, item["note_event"])

    def build_mode_notes(self, tonic_midi: int, mode_name: str) -> List[int]:
        intervals = MODE_INTERVALS[mode_name]
        notes = [int(np.clip(tonic_midi + interval, 0, 127)) for interval in intervals]
        return notes

    def mode_name_from_valence(self, valence: float) -> str:
        valence = float(np.clip(valence, 0.0, 1.0))

        if valence < 0.15:
            return "locrian"
        if valence < 0.30:
            return "phrygian"
        if valence < 0.43:
            return "aeolian"
        if valence < 0.57:
            return "dorian"
        if valence < 0.70:
            return "mixolydian"
        if valence < 0.85:
            return "ionian"
        return "lydian"

    def prepare_word_slices(self, utterance: Utterance) -> List[WordSlice]:
        cfg = self._cfg()
        default_duration = float(cfg["default_word_duration"])
        tonic_midi = int(cfg["tonic_midi"])

        filtered_words = [word for word in utterance.words if word.text.lower() not in STOP_WORDS]
        if not filtered_words:
            return []

        slices: List[WordSlice] = []

        for word in filtered_words:
            duration = self.word_duration(word, default_duration)

            local_valence = self.get_word_feature_pct(word, "valence", default=0.5)
            mode_name = self.mode_name_from_valence(local_valence)
            pitch_choices = self.build_mode_notes(tonic_midi, mode_name)
            midi_note = random.choice(pitch_choices)

            slices.append(
                WordSlice(
                    word=word,
                    duration=duration,
                    midi_note=midi_note,
                    mode_name=mode_name,
                )
            )

        return slices

    def word_duration(self, word: Word, default: float) -> float:
        candidates = [
            word.meta.get("duration_sec"),
            word.meta.get("duration"),
            word.features.get("duration_sec"),
            word.features.get("duration"),
        ]

        for value in candidates:
            if value is None:
                continue
            try:
                return max(0.03, float(value))
            except (TypeError, ValueError):
                continue

        return default


    @staticmethod
    def assign_words_evolving_bars(words: List[WordSlice], max_voices: int, replacements_per_bar: int = 2) -> List[List[WordSlice]]:
        if not words:
            return []

        first_bar = words[:max_voices]
        bars = [first_bar[:]]

        remaining = words[max_voices:]
        idx = 0

        while idx < len(remaining):
            prev = bars[-1][:]
            replace_n = min(replacements_per_bar, len(prev), len(remaining) - idx)

            replace_indices = random.sample(range(len(prev)), replace_n)

            for slot in replace_indices:
                prev[slot] = remaining[idx]
                idx += 1

            bars.append(prev)

        return bars

    @staticmethod
    def normalize_pattern(raw_pattern) -> List[int]:
        if raw_pattern is None:
            return []

        out = []
        for value in list(raw_pattern):
            if isinstance(value, (bool, np.bool_)):
                out.append(1 if value else 0)
            elif isinstance(value, (int, np.integer, float, np.floating)):
                out.append(1 if int(value) != 0 else 0)
            elif isinstance(value, str):
                s = value.strip().lower()
                out.append(1 if s in {"1", "true", "t", "x", "l", "long", "on"} else 0)
            else:
                out.append(1 if bool(value) else 0)
        return out

    @staticmethod
    def fit_pattern_length(pattern: List[int], steps: int) -> List[int]:
        if steps <= 0:
            return []

        if not pattern:
            return [0] * steps

        if len(pattern) == steps:
            return pattern

        repeats = (steps + len(pattern) - 1) // len(pattern)
        return (pattern * repeats)[:steps]

    @staticmethod
    def rotate_pattern(pattern: List[int], rotation: int) -> List[int]:
        if not pattern:
            return pattern

        rotation = rotation % len(pattern)
        if rotation == 0:
            return pattern[:]

        return pattern[-rotation:] + pattern[:-rotation]

    @staticmethod
    def adjust_pattern_to_target_hits(pattern: List[int], target_hits: int) -> List[int]:
        if not pattern:
            return pattern

        target_hits = int(np.clip(target_hits, 0, len(pattern)))
        pattern = pattern[:]

        one_indices = [i for i, value in enumerate(pattern) if value == 1]
        zero_indices = [i for i, value in enumerate(pattern) if value == 0]

        current_hits = len(one_indices)
        if current_hits == target_hits:
            return pattern

        if current_hits < target_hits:
            add_n = min(target_hits - current_hits, len(zero_indices))
            if add_n > 0:
                for idx in random.sample(zero_indices, add_n):
                    pattern[idx] = 1
        else:
            remove_n = min(current_hits - target_hits, len(one_indices))
            if remove_n > 0:
                for idx in random.sample(one_indices, remove_n):
                    pattern[idx] = 0

        return pattern

    def rhythm_type_from_global_dominance(self, dominance: float) -> str:
        if dominance < 0.34:
            return "christoffel"
        if dominance < 0.67:
            return "debruijn"
        return "euclidian"

    def steps_from_global_arousal(self, arousal: float, rhythm_type: str) -> tuple[int, Optional[int]]:
        cfg = self._cfg()
        arousal = float(np.clip(arousal, 0.0, 1.0))

        if rhythm_type == "debruijn":
            orders = [2, 3, 4]
            idx = min(len(orders) - 1, int(arousal * len(orders)))
            order = orders[idx]
            return 2 ** order, order

        choices = sorted(int(x) for x in cfg["step_size_choices"])
        idx = min(len(choices) - 1, int(arousal * len(choices)))
        return choices[idx], None

    def local_arousal_to_hits(self, arousal: float, steps: int, rhythm_type: str) -> int:
        arousal = float(np.clip(arousal, 0.0, 1.0))

        if steps <= 1:
            return 1

        max_hits = steps if rhythm_type != "christoffel" else max(1, steps - 1)
        hits = 1 + int(round(arousal * (max_hits - 1)))
        return int(np.clip(hits, 1, max_hits))

    def build_word_pattern(
        self,
        rhythm_engine: Rhythms,
        rhythm_type: str,
        steps: int,
        local_arousal: float,
        rotation: int,
        rotate_patterns: bool,
        debruijn_order: Optional[int] = None,
    ) -> List[int]:
        hits = self.local_arousal_to_hits(local_arousal, steps, rhythm_type)

        if rhythm_type == "euclidian":
            pattern = self.normalize_pattern(rhythm_engine.euclid(hits, steps))
            pattern = self.fit_pattern_length(pattern, steps)

        elif rhythm_type == "christoffel":
            p = int(np.clip(hits, 1, steps - 1))
            q = max(1, steps - p)

            if p + q != steps:
                q = max(1, steps - p)
                p = steps - q

            raw_pattern = rhythm_engine.chsequl("l", p, q)
            pattern = self.normalize_pattern(raw_pattern)
            pattern = self.fit_pattern_length(pattern, steps)
            pattern = self.adjust_pattern_to_target_hits(pattern, hits)

        elif rhythm_type == "debruijn":
            order = debruijn_order if debruijn_order is not None else 2
            raw_pattern = rhythm_engine.de_bruijn(order)
            pattern = self.normalize_pattern(raw_pattern)
            pattern = self.fit_pattern_length(pattern, steps)
            pattern = self.adjust_pattern_to_target_hits(pattern, hits)

        else:
            raise ValueError(f"Unknown rhythm_type: {rhythm_type}")

        if rotate_patterns:
            pattern = self.rotate_pattern(pattern, rotation)

        return pattern

    def get_state_value(self, name: str, default: float = 0.5) -> float:
        try:
            return float(self.state_values.get(name, default))
        except (TypeError, ValueError):
            return float(default)

    def get_word_feature_pct(self, word: Word, feature: str, default: float = 0.5) -> float:
        value = word.features.get(f"{feature}_pct")
        if value is None:
            value = word.features.get(feature, default)

        try:
            return float(np.clip(float(value), 0.0, 1.0))
        except (TypeError, ValueError):
            return float(default)

    def random_position(self) -> List[float]:
        cfg = self._cfg()
        xr = cfg["visual_x_range"]
        yr = cfg["visual_y_range"]
        zr = cfg["visual_z_range"]

        return [
            random.uniform(float(xr[0]), float(xr[1])),
            random.uniform(float(yr[0]), float(yr[1])),
            random.uniform(float(zr[0]), float(zr[1])),
        ]

    @staticmethod
    def random_color() -> List[float]:
        return [
            random.uniform(0.1, 1.0),
            random.uniform(0.1, 1.0),
            random.uniform(0.1, 1.0),
        ]

    def build_schedule(self, word_slices: List[WordSlice], utterance: Utterance) -> List[Dict[str, Any]]:
        cfg = self._cfg()
        rhythm_engine = Rhythms()

        words = word_slices[:]
        random.shuffle(words)

        bars_words = self.assign_words_evolving_bars(
            words,
            int(cfg["max_voices"]),
            int(cfg["replacements_per_bar"]),
        )

        global_arousal = self.get_state_value("global_arousal", 0.5)
        global_dominance = self.get_state_value("global_dominance", 0.5)

        rhythm_type = self.rhythm_type_from_global_dominance(global_dominance)
        master_steps, debruijn_order = self.steps_from_global_arousal(global_arousal, rhythm_type)

        bar_duration_sec = (60.0 / float(cfg["bpm"])) * float(cfg["bar_beats"])
        base_step_duration = bar_duration_sec / master_steps

        voice_configs = {}
        for voice in range(int(cfg["max_voices"])):
            voice_configs[voice] = {
                "rotation": random.randint(0, max(0, master_steps - 1))
            }

        bar_word_visuals: Dict[tuple[int, str], Dict[str, Any]] = {}
        schedule: List[Dict[str, Any]] = []

        for bar_idx, bar_words in enumerate(bars_words):
            for voice_idx, ws in enumerate(bar_words):
                local_arousal = self.get_word_feature_pct(ws.word, "arousal", default=0.5)

                pattern = self.build_word_pattern(
                    rhythm_engine=rhythm_engine,
                    rhythm_type=rhythm_type,
                    steps=master_steps,
                    local_arousal=local_arousal,
                    rotation=voice_configs[voice_idx]["rotation"],
                    rotate_patterns=bool(cfg["rotate_patterns"]),
                    debruijn_order=debruijn_order,
                )

                visual_key = (bar_idx, ws.word.text)
                if visual_key not in bar_word_visuals:
                    bar_word_visuals[visual_key] = {
                        "position": self.random_position(),
                        "color": self.random_color(),
                    }

                visual = bar_word_visuals[visual_key]
                hit_count_in_bar = 0

                for step_idx in range(master_steps):
                    if not pattern[step_idx]:
                        continue

                    gain = max(
                        float(cfg["min_gain"]),
                        float(cfg["decay_per_hit"]) ** hit_count_in_bar,
                    )

                    offset_sec = (bar_idx * master_steps + step_idx) * base_step_duration
                    event_duration = max(
                        float(cfg["event_min_duration"]),
                        base_step_duration * float(cfg["event_duration_scale"]),
                    )

                    midi_note = int(ws.midi_note if ws.midi_note is not None else 60)
                    velocity = int(np.clip(round(127 * gain), 1, 127))

                    visual_event = VisualEvent(
                        word=ws.word,
                        duration=event_duration,
                        intensity=gain,
                        position=list(visual["position"]),
                        color=list(visual["color"]),
                        meta={
                            "utterance_id": utterance.utterance_id,
                            "bar": bar_idx,
                            "voice": voice_idx,
                            "step": step_idx,
                            "rhythm_type": rhythm_type,
                        },
                    )

                    note_event = NoteEvent(
                        word=ws.word,
                        note=midi_note,
                        velocity=velocity,
                        duration=event_duration,
                        voice=voice_idx + 1,
                        channel=voice_idx + 1,
                        meta={
                            "utterance_id": utterance.utterance_id,
                            "bar": bar_idx,
                            "voice": voice_idx,
                            "step": step_idx,
                            "rhythm_type": rhythm_type,
                        },
                    )

                    schedule.append(
                        {
                            "offset_sec": offset_sec,
                            "visual_event": visual_event,
                            "note_event": note_event,
                        }
                    )
                    hit_count_in_bar += 1

        schedule.sort(key=lambda item: item["offset_sec"])
        return schedule
