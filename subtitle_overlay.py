from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

import numpy as np
import pyglet

from config import ConfigStore
from models import TranscriptEvent, VisualEvent


ColorRGB = Tuple[int, int, int]


@dataclass
class SubtitleToken:
    text: str
    word_index: int
    is_stopword: bool = False
    active_color: ColorRGB = (255, 255, 255)
    blend: float = 0.0
    active_until: float = 0.0

    label: Optional[pyglet.text.Label] = None
    width: float = 0.0
    x_offset: float = 0.0


@dataclass
class SubtitleRow:
    row_id: str
    utterance_id: str
    tokens: List[SubtitleToken]
    created_at: float
    remove_at: Optional[float] = None
    removing: bool = False
    dead: bool = False

    current_y: float = 0.0
    target_y: float = 0.0

    current_alpha: float = 0.0
    target_alpha: float = 0.0

    current_scale: float = 1.0
    target_scale: float = 1.0

    initialized: bool = False

    layout_dirty: bool = True
    cached_font_name: str = ""
    cached_font_size: float = 0.0
    cached_window_width: int = 0
    cached_space_width: float = 0.0
    cached_total_width: float = 0.0

    @property
    def has_content_word(self) -> bool:
        return any(not token.is_stopword for token in self.tokens)


class SubtitleOverlay:
    def __init__(self, config: ConfigStore, window):
        self.config = config
        self.window = window

        self.rows: List[SubtitleRow] = []

        self.preview_text: str = ""
        self.preview_rows: List[List[str]] = []
        self.preview_labels: List[List[pyglet.text.Label]] = []
        self.preview_layout_dirty: bool = True
        self.preview_cached_font_name: str = ""
        self.preview_cached_base_font_size: float = 0.0
        self.preview_cached_window_width: int = 0

        self.time = time.perf_counter()

    def _cfg(self) -> dict:
        merged = {
            "subtitles_enabled": True,
            "subtitle_preview_enabled": True,
            "subtitle_max_rows": 6,
            "subtitle_max_chars_per_line": 42,
            "subtitle_top_margin": 80,
            "subtitle_line_gap": 8,
            "subtitle_row_gap": 14,
            "subtitle_base_font_size": 28,
            "subtitle_depth_scale": 0.88,
            "subtitle_depth_alpha": 0.78,
            "subtitle_neutral_color": [225, 228, 236],
            "subtitle_attack": 10.0,
            "subtitle_release": 6.0,
            "subtitle_stopword_only_timeout": 2.0,
            "subtitle_move_speed": 8.0,
            "subtitle_fade_speed": 8.0,
            "subtitle_font_name": "Arial",
            "subtitle_shadow_enabled": True,
            "subtitle_shadow_dx": 2,
            "subtitle_shadow_dy": -2,
            "subtitle_shadow_alpha": 0.35,
            "subtitle_glow_enabled": True,
            "subtitle_glow_alpha": 0.18,
            "subtitle_glow_size": 2,
        }
        current = self.config.get("visual", {}) or {}
        merged.update(current)
        return merged

    @staticmethod
    def _to_rgb255(color) -> ColorRGB:
        if color is None:
            return (255, 255, 255)

        values = list(color[:3])
        if not values:
            return (255, 255, 255)

        if max(values) <= 1.0:
            values = [int(np.clip(v, 0.0, 1.0) * 255) for v in values]
        else:
            values = [int(np.clip(v, 0.0, 255.0)) for v in values]

        return (values[0], values[1], values[2])

    @staticmethod
    def _mix_rgb(a: ColorRGB, b: ColorRGB, t: float) -> ColorRGB:
        t = float(np.clip(t, 0.0, 1.0))
        return (
            int(round(a[0] + (b[0] - a[0]) * t)),
            int(round(a[1] + (b[1] - a[1]) * t)),
            int(round(a[2] + (b[2] - a[2]) * t)),
        )

    @staticmethod
    def _wrap_words(words: List[str], max_chars: int) -> List[List[str]]:
        rows: List[List[str]] = []
        current: List[str] = []
        current_len = 0

        for word in words:
            add_len = len(word) if not current else len(word) + 1

            if current and current_len + add_len > max_chars:
                rows.append(current)
                current = [word]
                current_len = len(word)
            else:
                current.append(word)
                current_len += add_len

        if current:
            rows.append(current)

        return rows

    @staticmethod
    def _wrap_token_groups(tokens: List[SubtitleToken], max_chars: int) -> List[List[SubtitleToken]]:
        rows: List[List[SubtitleToken]] = []
        current: List[SubtitleToken] = []
        current_len = 0

        for token in tokens:
            add_len = len(token.text) if not current else len(token.text) + 1

            if current and current_len + add_len > max_chars:
                rows.append(current)
                current = [token]
                current_len = len(token.text)
            else:
                current.append(token)
                current_len += add_len

        if current:
            rows.append(current)

        return rows

    def _make_label(self, text: str, font_name: str, font_size: float) -> pyglet.text.Label:
        return pyglet.text.Label(
            text,
            x=0,
            y=0,
            font_name=font_name,
            font_size=font_size,
            anchor_x="left",
            anchor_y="baseline",
            color=(255, 255, 255, 255),
        )

    def _measure_label_width(self, label: pyglet.text.Label) -> float:
        return float(label.content_width)

    def _ensure_row_layout(self, row: SubtitleRow, font_name: str, font_size: float) -> None:
        if (
            not row.layout_dirty
            and row.cached_font_name == font_name
            and abs(row.cached_font_size - font_size) < 0.01
            and row.cached_window_width == self.window.width
        ):
            return

        row.cached_font_name = font_name
        row.cached_font_size = font_size
        row.cached_window_width = self.window.width

        space_label = self._make_label(" ", font_name, font_size)
        row.cached_space_width = self._measure_label_width(space_label)

        total_width = 0.0
        for token in row.tokens:
            if token.label is None:
                token.label = self._make_label(token.text, font_name, font_size)
            else:
                token.label.font_name = font_name
                token.label.font_size = font_size
                token.label.text = token.text

            token.width = self._measure_label_width(token.label)
            total_width += token.width

        total_width += max(0, len(row.tokens) - 1) * row.cached_space_width
        row.cached_total_width = total_width

        x = (self.window.width - total_width) * 0.5
        for token in row.tokens:
            token.x_offset = x
            x += token.width + row.cached_space_width

        row.layout_dirty = False

    def _ensure_preview_layout(self, font_name: str, base_font_size: float) -> None:
        if (
            not self.preview_layout_dirty
            and self.preview_cached_font_name == font_name
            and abs(self.preview_cached_base_font_size - base_font_size) < 0.01
            and self.preview_cached_window_width == self.window.width
        ):
            return

        self.preview_cached_font_name = font_name
        self.preview_cached_base_font_size = base_font_size
        self.preview_cached_window_width = self.window.width

        new_rows: List[List[pyglet.text.Label]] = []

        for row_words in self.preview_rows:
            row_labels: List[pyglet.text.Label] = []
            for word in row_words:
                row_labels.append(self._make_label(word, font_name, base_font_size))
            new_rows.append(row_labels)

        self.preview_labels = new_rows
        self.preview_layout_dirty = False

    def handle_transcript(self, event: TranscriptEvent) -> None:
        cfg = self._cfg()
        if not bool(cfg["subtitles_enabled"]):
            return

        if event.kind == "partial":
            if bool(cfg["subtitle_preview_enabled"]):
                self.preview_text = event.text.strip()
                self.preview_rows = self._wrap_words(
                    self.preview_text.split(),
                    int(cfg["subtitle_max_chars_per_line"]),
                )
                self.preview_layout_dirty = True
            return

        if event.kind == "partial_clear":
            self.preview_text = ""
            self.preview_rows = []
            self.preview_labels = []
            self.preview_layout_dirty = True
            return

        if event.kind != "final":
            return

        self.preview_text = ""
        self.preview_rows = []
        self.preview_labels = []
        self.preview_layout_dirty = True

        utterance_id = event.utterance_id or f"utt-{int(self.time * 1000)}"

        tokens: List[SubtitleToken] = []
        for i, word in enumerate(event.words):
            word_index = int(word.meta.get("word_index", i))
            is_stopword = bool(word.meta.get("is_stopword", False))
            tokens.append(
                SubtitleToken(
                    text=word.text,
                    word_index=word_index,
                    is_stopword=is_stopword,
                )
            )

        if not tokens:
            return

        wrapped = self._wrap_token_groups(tokens, int(cfg["subtitle_max_chars_per_line"]))
        timeout = float(cfg["subtitle_stopword_only_timeout"])

        for row_idx, row_tokens in enumerate(wrapped):
            row = SubtitleRow(
                row_id=f"{utterance_id}:{row_idx}",
                utterance_id=utterance_id,
                tokens=row_tokens,
                created_at=self.time,
            )

            if not row.has_content_word:
                row.remove_at = self.time + timeout

            self.rows.append(row)

    def handle_visual_event(self, event: VisualEvent) -> None:
        cfg = self._cfg()
        if not bool(cfg["subtitles_enabled"]):
            return

        utterance_id = event.meta.get("utterance_id")
        word_index = event.meta.get("word_index")

        if utterance_id is None or word_index is None:
            return

        found_any = False

        for row in self.rows:
            if row.utterance_id != utterance_id:
                continue

            for token in row.tokens:
                if token.word_index == int(word_index):
                    token.active_color = self._to_rgb255(event.color)
                    token.active_until = max(token.active_until, self.time + max(0.01, float(event.duration)))
                    found_any = True

        if found_any and bool(event.meta.get("is_last_in_utterance", False)):
            remove_time = self.time + max(0.01, float(event.duration))
            for row in self.rows:
                if row.utterance_id == utterance_id:
                    row.remove_at = remove_time

    def _visible_rows(self) -> List[SubtitleRow]:
        cfg = self._cfg()
        max_rows = int(cfg["subtitle_max_rows"])
        visible = [row for row in self.rows if not row.dead]
        if max_rows > 0:
            visible = visible[:max_rows]
        return visible

    def update(self, dt: float) -> None:
        cfg = self._cfg()
        self.time += dt

        attack = float(cfg["subtitle_attack"])
        release = float(cfg["subtitle_release"])
        move_speed = float(cfg["subtitle_move_speed"])
        fade_speed = float(cfg["subtitle_fade_speed"])

        visible_rows = self._visible_rows()

        for row in visible_rows:
            if row.remove_at is not None and self.time >= row.remove_at:
                row.removing = True

        layout_rows = [row for row in visible_rows if not row.removing]

        y_cursor = self.window.height - float(cfg["subtitle_top_margin"])

        for depth, row in enumerate(layout_rows):
            row_scale = float(cfg["subtitle_depth_scale"]) ** depth
            row_alpha = float(cfg["subtitle_depth_alpha"]) ** depth
            font_size = max(10.0, float(cfg["subtitle_base_font_size"]) * row_scale)
            row_height = font_size + float(cfg["subtitle_line_gap"])

            row.target_scale = row_scale
            row.target_y = y_cursor - row_height
            row.target_alpha = row_alpha

            y_cursor = row.target_y - float(cfg["subtitle_row_gap"])

        visible_ids = {row.row_id for row in visible_rows}
        layout_ids = {row.row_id for row in layout_rows}

        for row in self.rows:
            for token in row.tokens:
                if self.time <= token.active_until:
                    token.blend += (1.0 - token.blend) * min(1.0, attack * dt)
                else:
                    token.blend += (0.0 - token.blend) * min(1.0, release * dt)

            if row.row_id not in visible_ids:
                row.target_alpha = 0.0

            if row.row_id in visible_ids and row.row_id not in layout_ids:
                row.target_alpha = 0.0

            if not row.initialized:
                row.current_y = row.target_y
                row.current_alpha = row.target_alpha
                row.current_scale = row.target_scale
                row.initialized = True
                row.layout_dirty = True
            else:
                old_scale = row.current_scale
                row.current_y += (row.target_y - row.current_y) * min(1.0, move_speed * dt)
                row.current_alpha += (row.target_alpha - row.current_alpha) * min(1.0, fade_speed * dt)
                row.current_scale += (row.target_scale - row.current_scale) * min(1.0, move_speed * dt)

                target_font_size = max(10.0, float(cfg["subtitle_base_font_size"]) * row.current_scale)
                # if abs(target_font_size - row.cached_font_size) > 0.001:
                row.layout_dirty = True

            if row.removing and row.current_alpha <= 0.01:
                row.dead = True

        self.rows = [row for row in self.rows if not row.dead]

    @staticmethod
    def move_toward(current: float, target: float, max_step: float) -> float:
        if current < target:
            return min(current + max_step, target)
        if current > target:
            return max(current - max_step, target)
        return current

    def _draw_row(self, row: SubtitleRow, font_name: str, base_font_size: float, neutral_rgb: ColorRGB) -> None:
        font_size = max(10.0, base_font_size * row.current_scale)
        self._ensure_row_layout(row, font_name, font_size)

        alpha = int(np.clip(row.current_alpha * 255, 0, 255))
        y = row.current_y

        for token in row.tokens:
            if token.label is None:
                continue

            rgb = self._mix_rgb(neutral_rgb, token.active_color, token.blend)
            token.label.x = token.x_offset
            token.label.y = y
            token.label.color = (rgb[0], rgb[1], rgb[2], alpha)
            token.label.draw()

    def _draw_preview(self, font_name: str, base_font_size: float, neutral_rgb: ColorRGB) -> None:
        cfg = self._cfg()

        if not bool(cfg["subtitle_preview_enabled"]) or not self.preview_rows:
            return

        self._ensure_preview_layout(font_name, base_font_size)

        depth = len(self._visible_rows())
        y = self.window.height - float(cfg["subtitle_top_margin"])

        for row_words, row_labels in zip(self.preview_rows, self.preview_labels):
            scale = float(cfg["subtitle_depth_scale"]) ** depth
            alpha_scale = float(cfg["subtitle_depth_alpha"]) ** depth
            font_size = max(10.0, base_font_size * scale)
            row_height = font_size + float(cfg["subtitle_line_gap"])
            y -= row_height

            space_label = self._make_label(" ", font_name, font_size)
            space_width = self._measure_label_width(space_label)

            total_width = 0.0
            widths = []
            for label in row_labels:
                label.font_name = font_name
                label.font_size = font_size
                width = self._measure_label_width(label)
                widths.append(width)
                total_width += width

            total_width += max(0, len(row_labels) - 1) * space_width
            x = (self.window.width - total_width) * 0.5

            for label, width in zip(row_labels, widths):
                label.x = int(round(x))
                label.y = int(round(y))
                label.color = (
                    neutral_rgb[0],
                    neutral_rgb[1],
                    neutral_rgb[2],
                    int(np.clip(180 * alpha_scale, 0, 255)),
                )
                label.draw()
                x += width + space_width

            y -= float(cfg["subtitle_row_gap"])
            depth += 1

    def draw(self) -> None:
        cfg = self._cfg()
        if not bool(cfg["subtitles_enabled"]):
            return

        font_name = str(cfg["subtitle_font_name"])
        base_font_size = float(cfg["subtitle_base_font_size"])
        neutral_rgb = self._to_rgb255(cfg["subtitle_neutral_color"])

        for row in self._visible_rows():
            if row.current_alpha <= 0.01:
                continue
            self._draw_row(row, font_name, base_font_size, neutral_rgb)

        self._draw_preview(font_name, base_font_size, neutral_rgb)