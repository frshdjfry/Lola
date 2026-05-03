#!/usr/bin/env python3
"""
Real-time microphone transcription in English using Vosk.
Continuously listens, turns utterances into rhythmic sine-tone playback,
and plays queued results without blocking future utterance analysis.

Install:
    pip install vosk sounddevice numpy music-creatingrhythms python-osc nltk

If NLTK stopwords are not installed yet, run once:
    import nltk
    nltk.download("stopwords")
"""

import json
import queue
import random
import sys
import threading
import time
import math
from dataclasses import dataclass
from typing import List, Optional

import numpy as np
import sounddevice as sd
from vosk import KaldiRecognizer, Model
from music_creatingrhythms import Rhythms
from pythonosc.udp_client import SimpleUDPClient

from nltk.corpus import stopwords

stop_words = set(stopwords.words("english")+['hm'])

# -----------------------------
# Configuration
# -----------------------------

MODEL_PATH = "./vosk-model/vosk-model"

# Word slicing / cleanup
MIN_PARTIAL_CHARS = 1
MIN_WORD_DURATION_SEC = 0.05
WORD_TRAIL_MS = 40
FADE_MS = 8

# Audio I/O
SAMPLE_RATE = 16000
CHANNELS = 1
DTYPE = "int16"
BLOCK_SIZE = 4000
DEVICE_IN = None
DEVICE_OUT = None

# Repetition fade within each bar/voice
DECAY_PER_HIT = 0.50
MIN_GAIN = 0.05

# Rhythm control
BPM = 60
MAX_VOICES = 4
ROTATE_PATTERNS = True
RHYTHM_TYPE = "debruijn"   # "euclidian" | "christoffel" | "debruijn"
STEP_SIZE_CHOICES = [4, 6, 8]

# OSC output
OSC_ENABLED = True
OSC_HOST = "127.0.0.1"
OSC_PORT = 9000
OSC_ADDRESS = "/wave"

MIDI_OSC_ENABLED = True
MIDI_OSC_HOST = "127.0.0.1"
MIDI_OSC_PORT = 9001
MIDI_OSC_ADDRESS = "/midi"


OSC_X_RANGE = (-6.0, 6.0)
OSC_Y_RANGE = (-1.0, 1.0)
OSC_Z_RANGE = (-1.5, 1.5)

OSC_DURATION_SCALE = 0.9
OSC_MIN_DURATION = 0.05

# Sine synthesis
PITCH_CHOICES_HZ = [220.0, 246.94, 261.63, 293.66, 329.63, 392.0, 440.0, 523.25]


# A Ionian: A B C# D E F# G# A
PITCH_CHOICES_IONIAN_HZ = [
    220.00, 246.94, 277.18, 293.66, 329.63, 369.99, 415.30, 440.00
]

# A Lydian: A B C# D# E F# G# A
PITCH_CHOICES_LYDIAN_HZ = [
    220.00, 246.94, 277.18, 311.13, 329.63, 369.99, 415.30, 440.00
]

# A Locrian: A Bb C D Eb F G A
PITCH_CHOICES_LOCRIAN_HZ = [
    220.00, 233.08, 261.63, 293.66, 311.13, 349.23, 392.00, 440.00
]

MODES_CHOICES = [
    PITCH_CHOICES_IONIAN_HZ,
    PITCH_CHOICES_LYDIAN_HZ,
    PITCH_CHOICES_LOCRIAN_HZ
]

SINE_AMP = 0.35

# Queue behavior
MAX_AUDIO_QUEUE_CHUNKS = 256
MAX_PLAYBACK_QUEUE = 32


@dataclass
class WordSlice:
    word: str
    start_sec: float
    end_sec: float
    audio: np.ndarray
    pitch_hz: Optional[float] = None


@dataclass
class OscEvent:
    time_sec: float
    address: str
    values: List[float]
    bar: int
    voice: int
    word: str


@dataclass
class MidiOscEvent:
    time_sec: float
    address: str
    values: List[float]
    bar: int
    voice: int
    word: str
    note: int


@dataclass
class PlaybackJob:
    audio: np.ndarray
    arrangement: List[dict]
    osc_events: List[OscEvent]
    midi_events: List[MidiOscEvent]
    source_words: List[str]


class UtteranceShuffler:
    def __init__(
        self,
        midi_out_only: bool = False,
        midi_osc_host: str = MIDI_OSC_HOST,
        midi_osc_port: int = MIDI_OSC_PORT,
        midi_osc_address: str = MIDI_OSC_ADDRESS,
    ):
        self.model = Model(MODEL_PATH)
        self.audio_queue = queue.Queue(maxsize=MAX_AUDIO_QUEUE_CHUNKS)
        self.playback_queue = queue.Queue(maxsize=MAX_PLAYBACK_QUEUE)
        self.stop_event = threading.Event()
        self.osc_client = SimpleUDPClient(OSC_HOST, OSC_PORT) if OSC_ENABLED else None

        self.midi_out_only = midi_out_only
        self.midi_osc_address = midi_osc_address
        self.midi_osc_client = (
            SimpleUDPClient(midi_osc_host, midi_osc_port)
            if MIDI_OSC_ENABLED
            else None
        )

        self.recognition_thread: Optional[threading.Thread] = None
        self.playback_thread: Optional[threading.Thread] = None

        self.gate_open = True

        if self.midi_out_only:
            print(
                "[MIDI OSC] Local audio disabled. "
                f"Sending notes to osc://{midi_osc_host}:{midi_osc_port}{midi_osc_address}"
            )
    # -----------------------------
    # Audio input
    # -----------------------------
    def audio_callback(self, indata, frames, time_info, status):
        if status:
            print(status, file=sys.stderr)

        if self.stop_event.is_set():
            return

        try:
            self.audio_queue.put_nowait(bytes(indata))
        except queue.Full:
            # Drop oldest chunk to keep system responsive
            try:
                _ = self.audio_queue.get_nowait()
            except queue.Empty:
                pass
            try:
                self.audio_queue.put_nowait(bytes(indata))
            except queue.Full:
                pass

    def new_recognizer(self) -> KaldiRecognizer:
        rec = KaldiRecognizer(self.model, SAMPLE_RATE)
        rec.SetWords(True)
        return rec

    # -----------------------------
    # Recognition
    # -----------------------------
    def wait_for_utterance(self) -> Optional[tuple[np.ndarray, list]]:
        """
        Continuously consume mic audio until one utterance is finalized.
        Returns:
            (utterance_audio_int16, word_timestamps)
        """
        recognizer = self.new_recognizer()
        utterance_started = False
        buffered_chunks = []
        last_partial = ""

        while not self.stop_event.is_set():
            try:
                data = self.audio_queue.get(timeout=0.1)
            except queue.Empty:
                continue

            buffered_chunks.append(data)
            accepted = recognizer.AcceptWaveform(data)

            if accepted:
                result = json.loads(recognizer.Result())
                text = result.get("text", "").strip()
                words = result.get("result", [])

                if utterance_started and text and words:
                    full_audio_bytes = b"".join(buffered_chunks)
                    audio = np.frombuffer(full_audio_bytes, dtype=np.int16).copy()
                    print(f"\n[UTTERANCE END] {text}")
                    return audio, words

                buffered_chunks = []
                utterance_started = False
                last_partial = ""
                continue

            partial_result = json.loads(recognizer.PartialResult())
            partial = partial_result.get("partial", "").strip()

            if partial and len(partial) >= MIN_PARTIAL_CHARS:
                if not utterance_started:
                    utterance_started = True
                    print(f"\n[UTTERANCE START] {partial}")
                elif partial != last_partial:
                    print(f"\r[LISTENING] {partial}", end="", flush=True)

            last_partial = partial

        return None

    @staticmethod
    def hz_to_midi_note(freq_hz: float) -> int:
        if freq_hz <= 0:
            return 60

        note = round(69 + 12 * math.log2(freq_hz / 440.0))
        return int(np.clip(note, 0, 127))

    # -----------------------------
    # Word processing
    # -----------------------------
    @staticmethod
    def apply_fade(chunk: np.ndarray, fade_ms: int = 8) -> np.ndarray:
        fade_samples = int(SAMPLE_RATE * fade_ms / 1000)
        fade_samples = min(fade_samples, len(chunk) // 2)

        if fade_samples <= 0:
            return chunk

        x = chunk.astype(np.float32)
        x[:fade_samples] *= np.linspace(0.0, 1.0, fade_samples)
        x[-fade_samples:] *= np.linspace(1.0, 0.0, fade_samples)
        return np.clip(x, -32768, 32767).astype(np.int16)

    def extract_word_slices(self, utterance_audio: np.ndarray, words: list) -> List[WordSlice]:
        word_slices = []
        total_samples = len(utterance_audio)
        trail_samples = int(SAMPLE_RATE * WORD_TRAIL_MS / 1000)

        for item in words:
            word = item.get("word", "").strip()
            start_sec = float(item.get("start", 0.0))
            end_sec = float(item.get("end", 0.0))

            if not word:
                continue
            if end_sec <= start_sec:
                continue
            if (end_sec - start_sec) < MIN_WORD_DURATION_SEC:
                continue

            start_idx = max(0, int(start_sec * SAMPLE_RATE) - trail_samples)
            end_idx = min(total_samples, int(end_sec * SAMPLE_RATE) + trail_samples)

            if end_idx <= start_idx:
                continue

            chunk = utterance_audio[start_idx:end_idx].copy()
            chunk = self.apply_fade(chunk, fade_ms=FADE_MS)

            if len(chunk) == 0:
                continue

            word_slices.append(
                WordSlice(
                    word=word,
                    start_sec=start_sec,
                    end_sec=end_sec,
                    audio=chunk,
                )
            )

        return word_slices

    @staticmethod
    def synth_sine(duration_samples: int, freq_hz: float, amp: float = SINE_AMP) -> np.ndarray:
        if duration_samples <= 0:
            return np.array([], dtype=np.int16)

        t = np.arange(duration_samples, dtype=np.float32) / SAMPLE_RATE
        wave = amp * np.sin(2.0 * np.pi * freq_hz * t)

        fade_samples = min(int(0.01 * SAMPLE_RATE), duration_samples // 2)
        if fade_samples > 0:
            env = np.ones(duration_samples, dtype=np.float32)
            env[:fade_samples] *= np.linspace(0.0, 1.0, fade_samples)
            env[-fade_samples:] *= np.linspace(1.0, 0.0, fade_samples)
            wave *= env

        return np.clip(wave * 32767.0, -32768, 32767).astype(np.int16)

    @staticmethod
    def synth_electro_bass(duration_samples: int, freq_hz: float, amp: float = SINE_AMP) -> np.ndarray:
        if duration_samples <= 0:
            return np.array([], dtype=np.int16)

        # keep it low and stable
        f = max(35.0, min(freq_hz, 180.0))
        t = np.arange(duration_samples, dtype=np.float32) / SAMPLE_RATE

        sub = np.sin(2.0 * np.pi * f * t)
        body = 0.45 * np.sin(2.0 * np.pi * (2.0 * f) * t)
        click = 0.12 * np.sin(2.0 * np.pi * (6.0 * f) * t) * np.exp(-25.0 * t)

        # mild amplitude envelope
        attack_s = min(0.01, duration_samples / SAMPLE_RATE / 4)
        release_s = min(0.06, duration_samples / SAMPLE_RATE / 3)

        env = np.ones(duration_samples, dtype=np.float32)
        a = int(attack_s * SAMPLE_RATE)
        r = int(release_s * SAMPLE_RATE)

        if a > 0:
            env[:a] = np.linspace(0.0, 1.0, a)
        if r > 0:
            env[-r:] *= np.linspace(1.0, 0.0, r)

        wave = amp * (0.75 * sub + body + click) * env
        return np.clip(wave * 32767.0, -32768, 32767).astype(np.int16)
    @staticmethod
    def synth_glitch(duration_samples: int, freq_hz: float, amp: float = SINE_AMP) -> np.ndarray:
        if duration_samples <= 0:
            return np.array([], dtype=np.int16)

        t = np.arange(duration_samples, dtype=np.float32) / SAMPLE_RATE

        # carrier with slight harshness
        carrier = (
                0.6 * np.sin(2.0 * np.pi * freq_hz * t) +
                0.25 * np.sign(np.sin(2.0 * np.pi * (freq_hz * 2.01) * t)) +
                0.15 * np.random.randn(duration_samples).astype(np.float32)
        )

        # random gate blocks for glitching
        block = max(8, int(0.008 * SAMPLE_RATE))
        n_blocks = (duration_samples + block - 1) // block
        gate_vals = np.random.choice([0.0, 0.35, 1.0], size=n_blocks, p=[0.15, 0.25, 0.60]).astype(np.float32)
        gate = np.repeat(gate_vals, block)[:duration_samples]

        # short decay envelope
        env = np.exp(-8.0 * t).astype(np.float32)

        wave = amp * carrier * gate * env

        fade_samples = min(int(0.005 * SAMPLE_RATE), duration_samples // 2)
        if fade_samples > 0:
            wave[:fade_samples] *= np.linspace(0.0, 1.0, fade_samples)
            wave[-fade_samples:] *= np.linspace(1.0, 0.0, fade_samples)

        return np.clip(wave * 32767.0, -32768, 32767).astype(np.int16)
    @staticmethod
    def synth_click(duration_samples: int, freq_hz: float, amp: float = SINE_AMP) -> np.ndarray:
        if duration_samples <= 0:
            return np.array([], dtype=np.int16)

        t = np.arange(duration_samples, dtype=np.float32) / SAMPLE_RATE

        # Fast-decay sine + a bit of noise
        env = np.exp(-60.0 * t)
        tone = np.sin(2.0 * np.pi * freq_hz * t)
        noise = np.random.randn(duration_samples).astype(np.float32) * 0.15

        wave = amp * env * (0.8 * tone + 0.2 * noise)

        fade_samples = min(int(0.003 * SAMPLE_RATE), duration_samples // 2)
        if fade_samples > 0:
            wave[:fade_samples] *= np.linspace(0.0, 1.0, fade_samples)
            wave[-fade_samples:] *= np.linspace(1.0, 0.0, fade_samples)

        return np.clip(wave * 32767.0, -32768, 32767).astype(np.int16)

    @staticmethod
    def synth_bass(duration_samples: int, freq_hz: float, amp: float = SINE_AMP) -> np.ndarray:
        if duration_samples <= 0:
            return np.array([], dtype=np.int16)

        t = np.arange(duration_samples, dtype=np.float32) / SAMPLE_RATE

        # Slight pitch drop for punch
        pitch_env = np.exp(-12.0 * t)
        phase = 2.0 * np.pi * (freq_hz * (1.0 + 0.08 * pitch_env)) * t

        sine = np.sin(phase)
        sub = np.sin(2.0 * np.pi * (freq_hz * 0.5) * t) * 0.35

        # Soft envelope
        attack = min(int(0.005 * SAMPLE_RATE), duration_samples)
        release = min(int(0.03 * SAMPLE_RATE), duration_samples)
        env = np.ones(duration_samples, dtype=np.float32)

        if attack > 0:
            env[:attack] *= np.linspace(0.0, 1.0, attack)
        if release > 0:
            env[-release:] *= np.linspace(1.0, 0.0, release)

        body = np.tanh(1.8 * (sine + sub))
        wave = amp * env * body

        return np.clip(wave * 32767.0, -32768, 32767).astype(np.int16)

    @staticmethod
    def synth_hat(duration_samples: int, freq_hz: float, amp: float = SINE_AMP) -> np.ndarray:
        if duration_samples <= 0:
            return np.array([], dtype=np.int16)

        noise = np.random.randn(duration_samples).astype(np.float32)

        # crude high-pass-ish effect
        filtered = noise.copy()
        filtered[1:] = noise[1:] - 0.95 * noise[:-1]

        t = np.arange(duration_samples, dtype=np.float32) / SAMPLE_RATE
        env = np.exp(-80.0 * t)

        wave = amp * filtered * env * 0.7

        fade_samples = min(int(0.002 * SAMPLE_RATE), duration_samples // 2)
        if fade_samples > 0:
            wave[:fade_samples] *= np.linspace(0.0, 1.0, fade_samples)
            wave[-fade_samples:] *= np.linspace(1.0, 0.0, fade_samples)

        return np.clip(wave * 32767.0, -32768, 32767).astype(np.int16)

    @staticmethod
    def synth_bitcrush_lead(duration_samples: int, freq_hz: float, amp: float = SINE_AMP) -> np.ndarray:
        if duration_samples <= 0:
            return np.array([], dtype=np.int16)

        t = np.arange(duration_samples, dtype=np.float32) / SAMPLE_RATE

        wave = (
                0.7 * np.sign(np.sin(2.0 * np.pi * freq_hz * t)) +
                0.3 * np.sin(2.0 * np.pi * freq_hz * 0.5 * t)
        )

        # simple sample-rate reduction
        hold = max(1, int(SAMPLE_RATE / 4000))
        crushed = wave.copy()
        for i in range(0, duration_samples, hold):
            crushed[i:i + hold] = crushed[i]

        # bit depth reduction
        levels = 24.0
        crushed = np.round(crushed * levels) / levels

        env = np.ones(duration_samples, dtype=np.float32)
        fade_samples = min(int(0.008 * SAMPLE_RATE), duration_samples // 2)
        if fade_samples > 0:
            env[:fade_samples] = np.linspace(0.0, 1.0, fade_samples)
            env[-fade_samples:] *= np.linspace(1.0, 0.0, fade_samples)

        wave = amp * crushed * env
        return np.clip(wave * 32767.0, -32768, 32767).astype(np.int16)

    def assign_random_pitches_to_word_slices(self, word_slices: List[WordSlice]) -> List[WordSlice]:
        pitched = []
        pitch_choices = MODES_CHOICES[random.randint(0, 2)]

        for ws in word_slices:
            freq = random.choice(pitch_choices)
            new_audio = self.synth_sine(len(ws.audio), freq_hz=freq, amp=SINE_AMP)

            pitched.append(
                WordSlice(
                    word=ws.word,
                    start_sec=ws.start_sec,
                    end_sec=ws.end_sec,
                    audio=new_audio,
                    pitch_hz=freq,
                )
            )

            print(f"[PITCH] {ws.word} freq={freq:.2f}Hz duration_samples={len(new_audio)}")

        return pitched


    # -----------------------------
    # Rhythm / arrangement
    # -----------------------------
    @staticmethod
    def assign_words_evolving_bars(words, max_voices):
        if not words:
            return []

        first_bar = words[:max_voices]
        bars = [first_bar[:]]

        remaining = words[max_voices:]
        for ws in remaining:
            prev = bars[-1][:]
            replace_idx = random.randrange(len(prev))
            prev[replace_idx] = ws
            bars.append(prev)

        return bars

    @staticmethod
    def random_osc_origin():
        return [
            random.uniform(*OSC_X_RANGE),
            random.uniform(*OSC_Y_RANGE),
            random.uniform(*OSC_Z_RANGE),
        ]

    @staticmethod
    def random_osc_color():
        return [
            random.uniform(0.1, 1.0),
            random.uniform(0.1, 1.0),
            random.uniform(0.1, 1.0),
        ]

    @staticmethod
    def apply_edge_fade(audio: np.ndarray, fade_ms: int = 25) -> np.ndarray:
        if len(audio) == 0:
            return audio

        fade_samples = int(SAMPLE_RATE * fade_ms / 1000)
        fade_samples = min(fade_samples, len(audio) // 2)

        if fade_samples <= 0:
            return audio

        out = audio.astype(np.float32).copy()

        fade_in = np.linspace(0.0, 1.0, fade_samples, endpoint=True)
        fade_out = np.linspace(1.0, 0.0, fade_samples, endpoint=True)

        out[:fade_samples] *= fade_in
        out[-fade_samples:] *= fade_out

        return np.clip(out, -32768, 32767).astype(np.int16)

    def build_rhythm_playback(
            self,
            word_slices: List[WordSlice],
    ) -> tuple[np.ndarray, List[dict], List[OscEvent], List[MidiOscEvent]]:
        if not word_slices:
            return np.array([], dtype=np.int16), [], [], []

        r = Rhythms()
        words = word_slices[:]
        random.shuffle(words)

        bars_words = self.assign_words_evolving_bars(words, MAX_VOICES)
        bars = len(bars_words)

        voice_configs = {}
        for voice in range(MAX_VOICES):
            if RHYTHM_TYPE == "euclidian":
                steps = random.choice(STEP_SIZE_CHOICES)
                hits = random.randint(1, max(1, steps // 2))
                pattern = r.euclid(hits, steps)

            elif RHYTHM_TYPE == "christoffel":
                p = random.randint(1, 6)
                q = random.randint(1, 6)
                pattern = r.chsequl("l", p, q)
                steps = p + q

            elif RHYTHM_TYPE == "debruijn":
                order = random.randint(2, 4)
                pattern = r.de_bruijn(order)
                steps = 2 ** order
            else:
                raise ValueError(f"Unknown RHYTHM_TYPE: {RHYTHM_TYPE}")

            if ROTATE_PATTERNS:
                rotation = random.randint(0, steps - 1)
                pattern = r.rotate_n(rotation, pattern)
            else:
                rotation = 0

            voice_configs[voice] = {
                "steps": steps,
                "rotation": rotation,
                "pattern": pattern,
            }

        master_steps = max(cfg["steps"] for cfg in voice_configs.values()) if voice_configs else 1
        base_step_duration = 60 / BPM / 4
        total_duration = bars * master_steps * base_step_duration
        audio = np.zeros(int(total_duration * SAMPLE_RATE), dtype=np.float32)

        arrangement = []
        osc_events = []
        midi_events = []

        bar_word_visuals = {}

        for bar_idx, bar_words in enumerate(bars_words):
            for voice_idx, ws in enumerate(bar_words):
                cfg = voice_configs[voice_idx]
                pattern = cfg["pattern"]
                pattern_steps = cfg["steps"]

                arrangement.append({
                    "bar": bar_idx,
                    "voice": voice_idx,
                    "word": ws.word,
                    "steps": pattern_steps,
                    "rotation": cfg["rotation"],
                    "pattern": pattern,
                    "repeats_in_bar": master_steps // pattern_steps if pattern_steps > 0 else 0,
                })

                visual_key = (bar_idx, ws.word)
                if visual_key not in bar_word_visuals:
                    bar_word_visuals[visual_key] = {
                        "origin": self.random_osc_origin(),
                        "color": self.random_osc_color(),
                    }

                visual = bar_word_visuals[visual_key]
                hit_count_in_bar = 0

                for j in range(master_steps):
                    if pattern[j % pattern_steps]:
                        gain = max(MIN_GAIN, DECAY_PER_HIT ** hit_count_in_bar)

                        global_step = bar_idx * master_steps + j
                        start = int(global_step * base_step_duration * SAMPLE_RATE)
                        end = min(start + len(ws.audio), len(audio))

                        chunk = ws.audio[:end - start].astype(np.float32) / 32768.0
                        audio[start:end] += chunk * gain

                        onset_sec = global_step * base_step_duration
                        osc_duration = max(OSC_MIN_DURATION, base_step_duration * OSC_DURATION_SCALE)

                        osc_values = [
                            visual["origin"][0],
                            visual["origin"][1],
                            visual["origin"][2],
                            visual["color"][0],
                            visual["color"][1],
                            visual["color"][2],
                            osc_duration,
                        ]

                        osc_events.append(
                            OscEvent(
                                time_sec=onset_sec,
                                address=OSC_ADDRESS,
                                values=osc_values,
                                bar=bar_idx,
                                voice=voice_idx,
                                word=ws.word,
                            )
                        )


                        # MIDI events

                        pitch_hz = ws.pitch_hz if ws.pitch_hz is not None else 440.0
                        midi_note = self.hz_to_midi_note(pitch_hz)
                        velocity = int(np.clip(round(127 * gain), 1, 127))

                        midi_events.append(
                            MidiOscEvent(
                                time_sec=onset_sec,
                                address=self.midi_osc_address,
                                values=[
                                    voice_idx + 1,
                                    midi_note,
                                    velocity,
                                    osc_duration,
                                ],
                                bar=bar_idx,
                                voice=voice_idx,
                                word=ws.word,
                                note=midi_note,
                            )
                        )



                        hit_count_in_bar += 1

        peak = np.max(np.abs(audio))
        if peak > 1e-6:
            audio /= peak

        playback_audio = np.clip(audio * 32767.0, -32768, 32767).astype(np.int16)

        playback_audio = self.apply_edge_fade(playback_audio, fade_ms=25)

        osc_events.sort(key=lambda e: e.time_sec)
        midi_events.sort(key=lambda e: e.time_sec)

        return playback_audio, arrangement, osc_events, midi_events

    # -----------------------------
    # Playback
    # -----------------------------
    def send_osc_events_during_playback(self, osc_events: List[OscEvent]):
        if not OSC_ENABLED or self.osc_client is None or not osc_events:
            return

        start_time = time.perf_counter()

        for event in osc_events:
            if self.stop_event.is_set():
                return

            target_time = start_time + event.time_sec
            while True:
                now = time.perf_counter()
                remaining = target_time - now
                if remaining <= 0:
                    break
                time.sleep(min(remaining, 0.002))

            try:
                self.osc_client.send_message(event.address, event.values)
                print(
                    f"[OSC] t={event.time_sec:.3f}s "
                    f"bar={event.bar + 1} voice={event.voice + 1} word={event.word}"
                )
            except Exception as e:
                print(f"[OSC ERROR] {e}", file=sys.stderr)

    def send_midi_events_during_playback(self, midi_events: List[MidiOscEvent]):
        if not MIDI_OSC_ENABLED or self.midi_osc_client is None or not midi_events:
            return

        start_time = time.perf_counter()

        for event in midi_events:
            if self.stop_event.is_set():
                return

            target_time = start_time + event.time_sec

            while True:
                now = time.perf_counter()
                remaining = target_time - now
                if remaining <= 0:
                    break
                time.sleep(min(remaining, 0.002))

            try:
                self.midi_osc_client.send_message(event.address, event.values)
                print(
                    f"[MIDI OSC] t={event.time_sec:.3f}s "
                    f"voice={event.voice + 1} "
                    f"note={event.note} "
                    f"velocity={int(event.values[2])} "
                    f"duration={event.values[3]:.3f}s "
                    f"bar={event.bar + 1} "
                    f"word={event.word}"
                )
            except Exception as e:
                print(f"[MIDI OSC ERROR] {e}", file=sys.stderr)

    def play_midi_out_only(self, job: PlaybackJob):
        """
        No local audio output.
        Sends note-style OSC events, while still sending visual OSC events.
        """
        self.gate_open = False

        visual_thread = None
        midi_thread = None

        try:
            print("\n[GATE CLOSED] MIDI/OSC-only playback...")

            if job.osc_events:
                visual_thread = threading.Thread(
                    target=self.send_osc_events_during_playback,
                    args=(job.osc_events,),
                    daemon=True,
                )
                visual_thread.start()

            if job.midi_events:
                midi_thread = threading.Thread(
                    target=self.send_midi_events_during_playback,
                    args=(job.midi_events,),
                    daemon=True,
                )
                midi_thread.start()

            if visual_thread is not None:
                visual_thread.join()

            if midi_thread is not None:
                midi_thread.join()

        finally:
            time.sleep(1)
            self.gate_open = True
            print("[MIDI OSC DONE] Gate reopened.")


    def play_audio(self, audio: np.ndarray, osc_events: Optional[List[OscEvent]] = None):
        """
        Gate stays closed while audio is playing.
        Uses sounddevice.OutputStream for steadier playback.
        OSC events are sent in sync with playback.
        """
        if len(audio) == 0:
            return

        self.gate_open = False
        osc_thread = None

        # Convert once to float32 mono in [-1, 1]
        audio_f32 = audio.astype(np.float32) / 32768.0
        playhead = 0
        finished = threading.Event()

        def callback(outdata, frames, time_info, status):
            nonlocal playhead

            if status:
                print(f"[AUDIO STATUS] {status}", file=sys.stderr)

            remaining = len(audio_f32) - playhead
            n = min(frames, remaining)

            if n > 0:
                outdata[:n, 0] = audio_f32[playhead:playhead + n]
                playhead += n

            if n < frames:
                outdata[n:, 0] = 0.0
                raise sd.CallbackStop()

        try:
            print("\n[GATE CLOSED] Playing rhythmic utterance...")

            if osc_events:
                osc_thread = threading.Thread(
                    target=self.send_osc_events_during_playback,
                    args=(osc_events,),
                    daemon=True,
                )
                osc_thread.start()

            with sd.OutputStream(
                    samplerate=SAMPLE_RATE,
                    blocksize=1024,
                    device=DEVICE_OUT,
                    channels=1,
                    dtype="float32",
                    callback=callback,
                    finished_callback=finished.set,
            ):
                finished.wait()

            if osc_thread is not None:
                osc_thread.join(timeout=0.25)

        finally:
            time.sleep(1)
            self.gate_open = True
            print("[PLAYBACK DONE] Gate reopened.")
    # -----------------------------
    # Worker threads
    # -----------------------------
    def recognition_loop(self):
        print("[RECOGNIZER] Running...")

        while not self.stop_event.is_set():
            result = self.wait_for_utterance()
            if result is None:
                continue

            utterance_audio, words = result
            word_slices = self.extract_word_slices(utterance_audio, words)
            word_slices = self.assign_random_pitches_to_word_slices(word_slices)

            if not word_slices:
                print("[SKIP] No valid word slices found.")
                continue

            original_words = [w.word for w in word_slices]
            print(f"[WORDS] {' '.join(original_words)}")

            word_slices = [w for w in word_slices if w.word not in stop_words]
            if not word_slices:
                print("[SKIP] No non-stopword slices left.")
                continue

            playback_audio, arrangement, osc_events, midi_events = self.build_rhythm_playback(word_slices)
            if len(playback_audio) == 0:
                print("[SKIP] Playback was empty.")
                continue

            for item in arrangement:
                print(
                    f"[BAR {item['bar'] + 1} VOICE {item['voice'] + 1}] "
                    f"{item['word']} pattern={item['pattern']}"
                )

            job = PlaybackJob(
                audio=playback_audio,
                arrangement=arrangement,
                osc_events=osc_events,
                midi_events=midi_events,
                source_words=original_words,
            )

            try:
                self.playback_queue.put(job, timeout=0.1)
                print(f"[QUEUE] enqueued playback job, pending={self.playback_queue.qsize()}")
            except queue.Full:
                print("[QUEUE] playback queue full, dropping oldest job")
                try:
                    _ = self.playback_queue.get_nowait()
                except queue.Empty:
                    pass
                try:
                    self.playback_queue.put_nowait(job)
                except queue.Full:
                    pass

    def playback_loop(self):
        print("[PLAYER] Running...")

        while not self.stop_event.is_set():
            try:
                job = self.playback_queue.get(timeout=0.1)
            except queue.Empty:
                continue

            if self.midi_out_only:
                self.play_midi_out_only(job)
            else:
                self.play_audio(job.audio, osc_events=job.osc_events)
    # -----------------------------
    # App lifecycle
    # -----------------------------
    def run(self):
        print("Loading model...")
        print("Press Ctrl+C to stop.")

        try:
            with sd.RawInputStream(
                samplerate=SAMPLE_RATE,
                blocksize=BLOCK_SIZE,
                dtype=DTYPE,
                channels=CHANNELS,
                callback=self.audio_callback,
                device=DEVICE_IN,
            ):
                self.recognition_thread = threading.Thread(target=self.recognition_loop, daemon=True)
                self.playback_thread = threading.Thread(target=self.playback_loop, daemon=True)

                self.recognition_thread.start()
                self.playback_thread.start()

                while not self.stop_event.is_set():
                    time.sleep(0.2)

        except KeyboardInterrupt:
            print("\nStopping...")
            self.stop_event.set()
        finally:
            sd.stop()
            print("Stopped.")


if __name__ == "__main__":
    app = UtteranceShuffler()
    app.run()