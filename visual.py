from __future__ import annotations

import queue
from typing import Any, Callable, Dict, Optional

import moderngl
import pyglet
from pyglet import gl, shapes

from comms import TOPIC_STATE_UPDATE, TOPIC_VISUAL_EVENT, TOPIC_TRANSCRIPT
from config import ConfigStore
from models import StateUpdate, VisualEvent, TranscriptEvent
from pyglet.media.codecs.ffmpeg import FFmpegDecoder

from subtitle_overlay import SubtitleOverlay

ffmpeg_decoder = FFmpegDecoder()

DEFAULTS: Dict[str, Any] = {
    "visual": {
        "queue_size": 256,
        "active_generator": "dust",
        "switch_fade_sec": 0.35,
        "window_width": 1280,
        "window_height": 720,
        "caption": "Echorus Visual",
        "video_enabled": True,
        "video_path": "",
        "video_muted": True,
    }
}


class VisualWindow(pyglet.window.Window):
    def __init__(
            self,
            config: ConfigStore,
            visual_queue: queue.Queue,
            state_queue: queue.Queue,
            transcript_queue: queue.Queue,
            generator_factory: Callable[[str], Any],
    ):
        self.config_store = config
        self.visual_queue = visual_queue
        self.state_queue = state_queue
        self.transcript_queue = transcript_queue
        self.generator_factory = generator_factory

        cfg = self._cfg()

        config_gl = gl.Config(
            major_version=3,
            minor_version=3,
            double_buffer=True,
        )

        self.generator = None
        self.generator_name = None
        self.fade_overlay = None
        self.blackout = 0.0

        self.video_player = None
        self.video_texture = None
        self._video_path_applied = None
        self._video_muted_applied = None
        self._video_enabled_applied = None

        self.switch_phase: Optional[str] = None
        self.switch_target_name: Optional[str] = None
        self.switch_elapsed = 0.0

        self.switch_video_enabled: Optional[bool] = None
        self.switch_video_path: Optional[str] = None
        self.switch_video_muted: Optional[bool] = None

        super().__init__(
            int(cfg["window_width"]),
            int(cfg["window_height"]),
            caption=str(cfg["caption"]),
            resizable=True,
            vsync=True,
            config=config_gl,
        )

        self.switch_to()
        self.ctx = moderngl.create_context()
        self.ctx.enable_only(moderngl.BLEND | moderngl.PROGRAM_POINT_SIZE)
        self.ctx.blend_func = moderngl.SRC_ALPHA, moderngl.ONE

        self.state_values: Dict[str, float] = {
            "global_arousal": 0.5,
            "global_valence": 0.5,
            "global_dominance": 0.5,
        }

        self.generator = None
        self.generator_name: Optional[str] = None

        self.blackout = 0.0
        self.fade_overlay = shapes.Rectangle(0, 0, self.width, self.height, color=(0, 0, 0))
        self.fade_overlay.opacity = 0

        self.switch_phase: Optional[str] = None
        self.switch_target_name: Optional[str] = None
        self.switch_elapsed = 0.0

        self._set_generator(self._desired_generator_name())

        enabled, path, muted = self._desired_video_state()
        if enabled and path:
            self._open_video(path, muted)
        else:
            self._close_video()

        self._video_enabled_applied = enabled
        self._video_path_applied = path
        self._video_muted_applied = muted
        self.subtitle_overlay = SubtitleOverlay(self.config_store, self)

        pyglet.clock.schedule_interval(self.update, 1.0 / 60.0)

    def _cfg(self) -> Dict[str, Any]:
        merged = dict(DEFAULTS["visual"])
        current = self.config_store.get("visual", {}) or {}
        merged.update(current)
        return merged

    def _close_video(self) -> None:
        try:
            if self.video_player is not None:
                self.video_player.pause()
                self.video_player.delete()
        except Exception:
            pass
        self.video_player = None
        self.video_texture = None

    def _open_video(self, path: str, muted: bool) -> None:
        self._close_video()

        if not path:
            return

        try:
            player = pyglet.media.Player()
            source = pyglet.media.load(path, decoder=ffmpeg_decoder, streaming=True)
            player.queue(source)
            player.loop = True
            player.volume = 0.0 if muted else 1.0
            player.play()
            self.video_player = player
        except Exception as e:
            print(f"[VISUAL] Could not load video '{path}': {e}")
            self.video_player = None
            self.video_texture = None

    def _update_video_texture(self) -> None:
        if self.video_player is None:
            self.video_texture = None
            return

        tex = getattr(self.video_player, "texture", None)
        if tex is None and hasattr(self.video_player, "get_texture"):
            tex = self.video_player.get_texture()
        self.video_texture = tex

    def _desired_generator_name(self) -> str:
        return str(self.config_store.get("visual.active_generator", "dust")).lower()

    def _fade_duration(self) -> float:
        return max(0.01, float(self.config_store.get("visual.switch_fade_sec", 0.35)))

    def _set_blackout(self, amount: float) -> None:
        amount = max(0.0, min(1.0, float(amount)))
        self.blackout = amount
        self.fade_overlay.opacity = int(255 * amount)

    def _renderer_size(self, renderer) -> Optional[tuple[int, int]]:
        if hasattr(renderer, "get_window_size"):
            size = renderer.get_window_size()
            if size and len(size) == 2:
                return int(size[0]), int(size[1])
        return None

    def _set_generator(self, name: str) -> None:
        renderer = self.generator_factory(name)

        if self.generator is not None and hasattr(self.generator, "stop"):
            self.generator.stop()

        self.generator = renderer
        self.generator_name = name

        if hasattr(self.generator, "init_gl"):
            self.generator.init_gl(self.ctx, self)

        if hasattr(self.generator, "set_state"):
            self.generator.set_state(dict(self.state_values))

        size = self._renderer_size(self.generator)
        if size is not None and (size[0] != self.width or size[1] != self.height):
            self.set_size(*size)

        if hasattr(self.generator, "resize"):
            self.generator.resize(self.width, self.height)

    def _desired_video_state(self) -> tuple[bool, str, bool]:
        enabled = bool(self.config_store.get("visual.video_enabled", True))
        path = str(self.config_store.get("visual.video_path", "") or "").strip()
        muted = bool(self.config_store.get("visual.video_muted", True))
        return enabled, path, muted

    def _video_state_changed(self) -> bool:
        enabled, path, _ = self._desired_video_state()
        return (
                enabled != self._video_enabled_applied
                or path != self._video_path_applied
        )

    def _begin_switch(
            self,
            generator_name: Optional[str] = None,
            *,
            video_enabled: Optional[bool] = None,
            video_path: Optional[str] = None,
            video_muted: Optional[bool] = None,
    ) -> None:
        if self.switch_phase is not None:
            return

        self.switch_phase = "out"
        self.switch_elapsed = 0.0

        self.switch_target_name = generator_name if generator_name != self.generator_name else None
        self.switch_video_enabled = video_enabled
        self.switch_video_path = video_path
        self.switch_video_muted = video_muted

    def _advance_switch(self, dt: float) -> None:
        if self.switch_phase is None:
            return

        duration = self._fade_duration()
        self.switch_elapsed += dt
        progress = min(1.0, self.switch_elapsed / duration)

        if self.switch_phase == "out":
            self._set_blackout(progress)

            if progress >= 1.0:
                if self.switch_target_name is not None:
                    self._set_generator(self.switch_target_name)

                if self.switch_video_enabled is not None or self.switch_video_path is not None:
                    enabled = self.switch_video_enabled
                    path = self.switch_video_path or ""
                    muted = self.switch_video_muted if self.switch_video_muted is not None else True

                    if enabled and path:
                        self._open_video(path, muted)
                    else:
                        self._close_video()

                    self._video_enabled_applied = bool(enabled)
                    self._video_path_applied = path
                    self._video_muted_applied = bool(muted)

                self.switch_phase = "in"
                self.switch_elapsed = 0.0

            return

        if self.switch_phase == "in":
            self._set_blackout(1.0 - progress)

            if progress >= 1.0:
                self._set_blackout(0.0)
                self.switch_phase = None
                self.switch_target_name = None
                self.switch_video_enabled = None
                self.switch_video_path = None
                self.switch_video_muted = None
                self.switch_elapsed = 0.0

    def _drain_state_updates(self) -> None:
        changed = False

        while True:
            try:
                update = self.state_queue.get_nowait()
            except queue.Empty:
                break

            if not isinstance(update, StateUpdate):
                continue

            for key, value in update.values.items():
                try:
                    self.state_values[key] = float(value)
                    changed = True
                except (TypeError, ValueError):
                    continue

        if changed and self.generator is not None and hasattr(self.generator, "set_state"):
            self.generator.set_state(dict(self.state_values))

    def _drain_visual_events(self) -> None:
        while True:
            try:
                event = self.visual_queue.get_nowait()
            except queue.Empty:
                break

            if not isinstance(event, VisualEvent):
                continue

            self.subtitle_overlay.handle_visual_event(event)

            if self.generator is not None and hasattr(self.generator, "handle_event"):
                self.generator.handle_event(event)

    def _drain_transcript_updates(self) -> None:
        while True:
            try:
                event = self.transcript_queue.get_nowait()
            except queue.Empty:
                break

            if isinstance(event, TranscriptEvent):
                self.subtitle_overlay.handle_transcript(event)

    def _active_generator_config_section(self) -> str:
        if self.generator_name == "dust":
            return "dustscene"
        if self.generator_name == "waver":
            return "waver"
        return ""

    def update(self, dt: float) -> None:
        self._drain_state_updates()
        self._drain_transcript_updates()

        desired_name = self._desired_generator_name()
        video_enabled, video_path, video_muted = self._desired_video_state()

        muted_changed = video_muted != self._video_muted_applied
        if muted_changed and self.video_player is not None:
            self.video_player.volume = 0.0 if video_muted else 1.0
            self._video_muted_applied = video_muted

        need_generator_switch = desired_name != self.generator_name
        need_video_switch = self._video_state_changed()

        if self.switch_phase is None and (need_generator_switch or need_video_switch):
            self._begin_switch(
                desired_name if need_generator_switch else None,
                video_enabled=video_enabled if need_video_switch else None,
                video_path=video_path if need_video_switch else None,
                video_muted=video_muted if need_video_switch else None,
            )

        self._advance_switch(dt)
        self._update_video_texture()
        self._drain_visual_events()

        if self.generator is not None and hasattr(self.generator, "update"):
            self.generator.update(dt)

        section = self._active_generator_config_section()
        if section and self.generator is not None and hasattr(self.generator, "apply_config"):
            cfg = self.config_store.get(section, {}) or {}
            self.generator.apply_config(cfg)

        self.subtitle_overlay.update(dt)

    def on_draw(self) -> None:
        self.ctx.viewport = (0, 0, self.width, self.height)
        self.ctx.clear(0.0, 0.0, 0.0, 1.0)

        if self.video_texture is not None:
            self.video_texture.blit(
                0,
                0,
                width=self.width,
                height=self.height,
            )

        if self.generator is not None and hasattr(self.generator, "draw"):
            self.generator.draw()

        self.subtitle_overlay.draw()

        if self.blackout > 0.0:
            self.fade_overlay.draw()

    def on_resize(self, width, height):
        super().on_resize(width, height)

        if self.fade_overlay is not None:
            self.fade_overlay.x = 0
            self.fade_overlay.y = 0
            self.fade_overlay.width = width
            self.fade_overlay.height = height

        if self.generator is not None and hasattr(self.generator, "resize"):
            self.generator.resize(width, height)

    def on_mouse_press(self, x, y, button, modifiers):
        if self.generator is not None and hasattr(self.generator, "on_mouse_press"):
            self.generator.on_mouse_press(x, y, button, modifiers)

    def on_mouse_release(self, x, y, button, modifiers):
        if self.generator is not None and hasattr(self.generator, "on_mouse_release"):
            self.generator.on_mouse_release(x, y, button, modifiers)

    def on_close(self):
        try:
            pyglet.clock.unschedule(self.update)

            self._close_video()

            if self.generator is not None and hasattr(self.generator, "stop"):
                self.generator.stop()
        finally:
            super().on_close()

class VisualEngine:
    def __init__(
        self,
        config: ConfigStore,
        comms,
        generator_factory: Callable[[str], Any],
    ):
        self.config = config
        self.comms = comms
        self.generator_factory = generator_factory

        self.visual_queue: Optional[queue.Queue] = None
        self.state_queue: Optional[queue.Queue] = None
        self.transcript_queue: Optional[queue.Queue] = None
        self.window: Optional[VisualWindow] = None

    @property
    def generator_name(self) -> Optional[str]:
        if self.window is None:
            return None
        return self.window.generator_name

    def _cfg(self) -> Dict[str, Any]:
        merged = dict(DEFAULTS["visual"])
        current = self.config.get("visual", {}) or {}
        merged.update(current)
        return merged

    def start(self) -> None:
        if self.window is not None:
            return

        cfg = self._cfg()
        queue_size = int(cfg["queue_size"])

        self.visual_queue = self.comms.open_queue(TOPIC_VISUAL_EVENT, maxsize=queue_size)
        self.state_queue = self.comms.open_queue(TOPIC_STATE_UPDATE, maxsize=queue_size)
        self.transcript_queue = self.comms.open_queue(TOPIC_TRANSCRIPT, maxsize=queue_size)

        def create_window(dt=0.0):
            if self.window is None:
                self.window = VisualWindow(
                    self.config,
                    self.visual_queue,
                    self.state_queue,
                    self.transcript_queue,
                    self.generator_factory,
                )

        pyglet.clock.schedule_once(create_window, 0.0)

    def stop(self) -> None:
        def close_window(dt=0.0):
            if self.window is not None:
                try:
                    self.window.close()
                finally:
                    self.window = None

            if self.visual_queue is not None:
                self.comms.close_queue(TOPIC_VISUAL_EVENT, self.visual_queue)
                self.visual_queue = None

            if self.state_queue is not None:
                self.comms.close_queue(TOPIC_STATE_UPDATE, self.state_queue)
                self.state_queue = None

            if self.transcript_queue is not None:
                self.comms.close_queue(TOPIC_TRANSCRIPT, self.transcript_queue)
                self.transcript_queue = None

        pyglet.clock.schedule_once(close_window, 0.0)