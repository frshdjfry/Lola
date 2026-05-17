from __future__ import annotations

import math
import queue
from typing import Any, Dict, Optional

import moderngl
import numpy as np
import pyglet
from pyglet.window import mouse

from config import ConfigStore
from models import VisualEvent



VERTEX_SHADER = """
#version 330

in vec3 in_pos;
in float in_size;
in float in_alpha;
in float in_phase;
in vec3 in_color;

uniform mat4 u_proj;
uniform mat4 u_view;
uniform float u_time;
uniform float u_size_scale;
uniform float u_max_point_size;

out float v_alpha;
out float v_phase;
out float v_depth;
out vec3 v_color;

void main() {
    vec4 view_pos = u_view * vec4(in_pos, 1.0);
    gl_Position = u_proj * view_pos;

    float dist = length(view_pos.xyz);
    gl_PointSize = clamp(in_size * u_size_scale / max(1.0, dist), 1.0, u_max_point_size);

    v_alpha = in_alpha;
    v_phase = in_phase;
    v_depth = dist;
    v_color = in_color;
}
"""

FRAGMENT_SHADER = """
#version 330

in float v_alpha;
in float v_phase;
in float v_depth;
in vec3 v_color;

uniform float u_time;
uniform float u_glow_power;
uniform float u_twinkle_amount;

out vec4 f_color;

void main() {
    vec2 p = gl_PointCoord - vec2(0.5);
    float r = length(p);

    if (r > 0.5) {
        discard;
    }

    float glow = pow(1.0 - smoothstep(0.0, 0.5, r), u_glow_power);
    float twinkle = 1.0 + u_twinkle_amount * sin(u_time * 0.8 + v_phase);
    float depth_fade = clamp(1.4 / (0.4 + v_depth * 0.08), 0.20, 1.0);

    float alpha = v_alpha * glow * twinkle * depth_fade;
    f_color = vec4(v_color, alpha);
}
"""


DEFAULTS = {
    "fireflight": {
        "width": 1280,
        "height": 720,
        "camera_distance": -17.0,
        "source_plane_z": 0.0,
        "max_trail_points": 250000,
        "trail_sample_distance": 1.0055,
        "camera_dolly_speed": 0.2,
        "spawn_forward_distance": 10.5,
        "spawn_ground_height": 1.15,
        "spawn_x_scale": 1.5,
        "spawn_y_scale": 1.35,
        "spawn_z_scale": 0.8,
        "video_path": "Lola-background.mp4",
        "video_muted": True,
        "update_hz": 120.0,
    }
}


def perspective(fovy_deg, aspect, near, far):
    f = 1.0 / math.tan(math.radians(fovy_deg) * 0.5)
    m = np.zeros((4, 4), dtype="f4")
    m[0, 0] = f / aspect
    m[1, 1] = f
    m[2, 2] = (far + near) / (near - far)
    m[2, 3] = (2.0 * far * near) / (near - far)
    m[3, 2] = -1.0
    return m


def look_at(eye, target, up):
    forward = target - eye
    forward /= np.linalg.norm(forward)

    right = np.cross(forward, up)
    right /= np.linalg.norm(right)

    true_up = np.cross(right, forward)

    view = np.eye(4, dtype="f4")
    view[0, :3] = right
    view[1, :3] = true_up
    view[2, :3] = -forward
    view[0, 3] = -np.dot(right, eye)
    view[1, 3] = -np.dot(true_up, eye)
    view[2, 3] = np.dot(forward, eye)
    return view


def cubic_bezier(p0, p1, p2, p3, t):
    omt = 1.0 - t
    return (
        (omt ** 3) * p0
        + 3.0 * (omt ** 2) * t * p1
        + 3.0 * omt * (t ** 2) * p2
        + (t ** 3) * p3
    )


def cubic_bezier_tangent(p0, p1, p2, p3, t):
    omt = 1.0 - t
    d = (
        3.0 * (omt ** 2) * (p1 - p0)
        + 6.0 * omt * t * (p2 - p1)
        + 3.0 * (t ** 2) * (p3 - p2)
    )
    n = np.linalg.norm(d)
    if n < 1e-6:
        return np.array([0.0, 1.0, 0.0], dtype="f4")
    return (d / n).astype("f4")


class Fireflight:
    def __init__(self, config: ConfigStore | None = None):
        self.config_store = config
        self.window = None
        self.ctx = None
        self.program = None

        self.state_values: Dict[str, float] = {
            "global_arousal": 0.5,
            "global_valence": 0.5,
            "global_dominance": 0.5,
        }
        self.event_queue: queue.Queue[VisualEvent] = queue.Queue()

        cfg = self._cfg()

        self.camera_distance = float(cfg["camera_distance"])
        self.source_plane_z = float(cfg["source_plane_z"])
        self.max_trail_points = int(cfg["max_trail_points"])
        self.trail_sample_distance = float(cfg["trail_sample_distance"])
        self.camera_dolly_speed = float(cfg["camera_dolly_speed"])
        self.spawn_forward_distance = float(cfg["spawn_forward_distance"])
        self.spawn_ground_height = float(cfg["spawn_ground_height"])
        self.spawn_x_scale = float(cfg["spawn_x_scale"])
        self.spawn_y_scale = float(cfg["spawn_y_scale"])
        self.spawn_z_scale = float(cfg["spawn_z_scale"])

        self.rng = np.random.default_rng(4)
        self.wave_palette = np.array(
            [
                [0.45, 0.95, 1.00],
                [0.62, 0.72, 1.00],
                [0.86, 0.55, 1.00],
                [1.00, 0.58, 0.78],
                [1.00, 0.72, 0.42],
                [0.52, 1.00, 0.78],
            ],
            dtype="f4",
        )

        self.time = 0.0
        self.proj_mat = np.eye(4, dtype="f4")

        self.active_flyers = []
        self.head_data = np.zeros((0, 9), dtype="f4")

        self.trail_points = []
        self.trail_data = np.zeros((0, 9), dtype="f4")
        self.trail_vbo = None
        self.trail_vao = None
        self.trail_dirty = False

        self.head_vbo = None
        self.head_vao = None

    def _cfg(self) -> Dict[str, Any]:
        merged = dict(DEFAULTS["fireflight"])
        if self.config_store is not None:
            current = self.config_store.get("fireflight", {}) or {}
            merged.update(current)
        return merged

    def get_window_size(self) -> tuple[int, int]:
        cfg = self._cfg()
        return int(cfg["width"]), int(cfg["height"])

    def init_gl(self, ctx, window) -> None:
        self.ctx = ctx
        self.window = window

        self.program = self.ctx.program(
            vertex_shader=VERTEX_SHADER,
            fragment_shader=FRAGMENT_SHADER,
        )

        self.resize(window.width, window.height)

    def stop(self) -> None:
        pass

    def set_state(self, values: Dict[str, float]) -> None:
        for key, value in values.items():
            try:
                self.state_values[key] = float(value)
            except (TypeError, ValueError):
                continue

    def handle_event(self, event: VisualEvent) -> None:
        try:
            self.event_queue.put_nowait(event)
        except queue.Full:
            pass

    def random_wave_color(self):
        base = self.wave_palette[self.rng.integers(0, len(self.wave_palette))].copy()
        soft_white = np.array([1.0, 1.0, 1.0], dtype="f4")
        return np.clip(base * 0.82 + soft_white * 0.18, 0.0, 1.0).astype("f4")


    def rebuild_trail_buffer(self):
        if len(self.trail_points) == 0:
            self.trail_data = np.zeros((0, 9), dtype="f4")
            self.trail_vbo = None
            self.trail_vao = None
            self.trail_dirty = False
            return

        self.trail_data = np.asarray(self.trail_points, dtype="f4")
        self.trail_vbo = self.ctx.buffer(self.trail_data.tobytes())
        self.trail_vao = self.ctx.vertex_array(
            self.program,
            [(self.trail_vbo, "3f 1f 1f 1f 3f", "in_pos", "in_size", "in_alpha", "in_phase", "in_color")],
        )
        self.trail_dirty = False

    def rebuild_head_buffer(self):
        if len(self.head_data) == 0:
            self.head_vbo = None
            self.head_vao = None
            return

        head_array = np.asarray(self.head_data, dtype="f4")
        self.head_vbo = self.ctx.buffer(head_array.tobytes())
        self.head_vao = self.ctx.vertex_array(
            self.program,
            [(self.head_vbo, "3f 1f 1f 1f 3f", "in_pos", "in_size", "in_alpha", "in_phase", "in_color")],
        )

    def resize(self, width, height):
        if self.ctx is None or self.program is None:
            return
        self.ctx.viewport = (0, 0, width, height)
        self.proj_mat = perspective(55.0, width / max(1, height), 0.1, 200.0)
        self.program["u_proj"].write(self.proj_mat.T.tobytes())

    def get_camera_state(self):
        eye = np.array(
            [
                0.35 * math.sin(self.time * 0.06),
                2.2,
                self.camera_distance - self.time * self.camera_dolly_speed,
            ],
            dtype="f4",
        )
        target = np.array([0.0, 2.1, eye[2] + 6.0], dtype="f4")
        up_hint = np.array([0.0, 1.0, 0.0], dtype="f4")

        forward = target - eye
        forward /= np.linalg.norm(forward)

        right = np.cross(forward, up_hint)
        right /= np.linalg.norm(right)

        up = np.cross(right, forward)
        up /= np.linalg.norm(up)

        return eye, target, up, forward, right, up

    def get_view_matrix(self):
        eye, target, up, _, _, _ = self.get_camera_state()
        return look_at(eye, target, up)

    def signal_to_camera_spawn_world(self, signal_coords):
        eye, _, _, forward, _, _ = self.get_camera_state()
        x, y, z = signal_coords

        world_up = np.array([0.0, 1.0, 0.0], dtype="f4")

        ground_forward = np.array([forward[0], 0.0, forward[2]], dtype="f4")
        n = np.linalg.norm(ground_forward)
        if n < 1e-6:
            ground_forward = np.array([0.0, 0.0, 1.0], dtype="f4")
        else:
            ground_forward /= n

        ground_right = np.cross(ground_forward, world_up)
        ground_right /= np.linalg.norm(ground_right)

        spawn_center = np.array(
            [
                eye[0],
                self.spawn_ground_height,
                eye[2],
            ],
            dtype="f4",
        ) + ground_forward * self.spawn_forward_distance

        world = (
            spawn_center
            + ground_right * (x * self.spawn_x_scale)
            + world_up * (y * self.spawn_y_scale)
            + ground_forward * (z * self.spawn_z_scale)
        )
        return world.astype("f4")

    def screen_to_world_on_camera_plane(self, x, y, forward_distance=None):
        x = float(np.clip(x, 0, self.window.width))
        y = float(np.clip(y, 0, self.window.height))

        if forward_distance is None:
            forward_distance = self.spawn_forward_distance

        x_ndc = (2.0 * x / self.window.width) - 1.0
        y_ndc = (2.0 * y / self.window.height) - 1.0

        eye, _, _, forward, _, _ = self.get_camera_state()
        plane_point = eye + forward * forward_distance
        plane_normal = forward

        view = self.get_view_matrix()
        inv_vp = np.linalg.inv(self.proj_mat @ view)

        near = inv_vp @ np.array([x_ndc, y_ndc, -1.0, 1.0], dtype="f4")
        far = inv_vp @ np.array([x_ndc, y_ndc, 1.0, 1.0], dtype="f4")
        near /= near[3]
        far /= far[3]

        ray_origin = near[:3]
        ray_dir = far[:3] - near[:3]
        ray_dir /= np.linalg.norm(ray_dir)

        denom = float(np.dot(ray_dir, plane_normal))
        if abs(denom) < 1e-5:
            return None

        t = float(np.dot(plane_point - ray_origin, plane_normal) / denom)
        if t < 0.0:
            return None

        hit = ray_origin + ray_dir * t
        return hit.astype("f4")

    def spawn_flyer(self, origin, color, duration, intensity=1.0, size=None):
        d = float(np.clip(duration, 0.03, 2.5))
        strength = min(1.0, d / 1.4)
        intensity = float(np.clip(intensity, 0.0, 2.0))

        start = origin.astype("f4").copy()
        start += np.array(
            [
                self.rng.uniform(-0.28, 0.28),
                self.rng.uniform(-0.08, 0.10),
                self.rng.uniform(-0.28, 0.28),
            ],
            dtype="f4",
        )

        lateral_angle = self.rng.uniform(0.0, math.tau)
        lateral = np.array(
            [math.cos(lateral_angle), 0.0, math.sin(lateral_angle)],
            dtype="f4",
        )
        lateral /= np.linalg.norm(lateral)

        lateral2 = np.array([-lateral[2], 0.0, lateral[0]], dtype="f4")
        if np.linalg.norm(lateral2) < 1e-6:
            lateral2 = np.array([1.0, 0.0, 0.0], dtype="f4")

        height = 1.8 + 5.8 * strength + self.rng.uniform(0.0, 0.8)
        drift1 = lateral * self.rng.uniform(0.18, 0.65)
        drift2 = lateral * self.rng.uniform(0.55, 1.35) + lateral2 * self.rng.uniform(-0.35, 0.35)
        drift3 = lateral * self.rng.uniform(0.8, 1.6) + lateral2 * self.rng.uniform(-0.55, 0.55)

        base_size = 1.6 + self.rng.uniform(0.0, 0.7)
        top_size = 6.0 + 6.0 * strength + self.rng.uniform(0.0, 1.5)
        head_size = 9.0 + 6.0 * strength

        if size is not None:
            try:
                size_value = float(size)
                base_size *= max(0.2, size_value)
                top_size *= max(0.2, size_value)
                head_size *= max(0.2, size_value)
            except (TypeError, ValueError):
                pass

        p0 = start
        p1 = start + drift1 + np.array([0.0, height * 0.20, 0.0], dtype="f4")
        p2 = start + drift2 + np.array([0.0, height * 0.68, 0.0], dtype="f4")
        p3 = start + drift3 + np.array([0.0, height, 0.0], dtype="f4")

        flyer = {
            "start_time": self.time,
            "lifetime": (0.9 + 1.8 * strength + self.rng.uniform(0.0, 0.4)) * max(0.25, intensity),
            "p0": p0.astype("f4"),
            "p1": p1.astype("f4"),
            "p2": p2.astype("f4"),
            "p3": p3.astype("f4"),
            "color": np.clip(color, 0.0, 1.0).astype("f4"),
            "base_size": base_size,
            "top_size": top_size,
            "head_size": head_size * max(0.35, intensity),
            "swirl_amp": (0.10 + 0.28 * strength) * max(0.35, intensity),
            "swirl_freq": self.rng.uniform(1.2, 2.4),
            "swirl_phase": self.rng.uniform(0.0, math.tau),
            "last_pos": None,
            "last_t": -1.0,
        }
        self.active_flyers.append(flyer)

    def append_trail_point(self, pos, color, progress, phase):
        white = np.array([1.0, 1.0, 1.0], dtype="f4")
        mixed = np.clip(
            color * (0.78 + 0.12 * progress) + white * (0.10 + 0.25 * progress),
            0.0,
            1.0,
        )
        size = 1.3 + 2.4 * (progress ** 1.4) + 6.0 * (progress ** 3.0)
        alpha = 0.10 + 0.28 * (progress ** 0.8) + 0.42 * (progress ** 2.0)

        self.trail_points.append([
            pos[0], pos[1], pos[2],
            size, min(1.0, alpha), phase,
            mixed[0], mixed[1], mixed[2],
        ])

        if len(self.trail_points) > self.max_trail_points:
            drop = len(self.trail_points) - self.max_trail_points
            del self.trail_points[:drop]

        self.trail_dirty = True

    def flyer_position(self, flyer, t):
        base = cubic_bezier(flyer["p0"], flyer["p1"], flyer["p2"], flyer["p3"], t)
        tangent = cubic_bezier_tangent(flyer["p0"], flyer["p1"], flyer["p2"], flyer["p3"], t)

        side = np.cross(np.array([0.0, 1.0, 0.0], dtype="f4"), tangent)
        side_norm = np.linalg.norm(side)
        if side_norm < 1e-6:
            side = np.array([1.0, 0.0, 0.0], dtype="f4")
        else:
            side = side / side_norm

        flourish = flyer["swirl_amp"] * (math.sin(math.pi * t) ** 1.45) * math.sin(
            flyer["swirl_phase"] + flyer["swirl_freq"] * math.pi * t
        )
        lift = 0.18 * flyer["swirl_amp"] * (t ** 2.0)

        return (base + side * flourish + np.array([0.0, lift, 0.0], dtype="f4")).astype("f4")

    def update_flyers(self):
        new_flyers = []
        heads = []

        for flyer in self.active_flyers:
            age = self.time - flyer["start_time"]
            t = age / flyer["lifetime"]
            if t < 0.0:
                new_flyers.append(flyer)
                continue

            t = min(1.0, t)
            eased_t = 1.0 - ((1.0 - t) ** 2.3)
            pos = self.flyer_position(flyer, eased_t)

            need_sample = False
            if flyer["last_pos"] is None:
                need_sample = True
            else:
                if np.linalg.norm(pos - flyer["last_pos"]) >= self.trail_sample_distance:
                    need_sample = True
                elif eased_t >= 1.0 and flyer["last_t"] < 1.0:
                    need_sample = True

            if need_sample:
                self.append_trail_point(pos, flyer["color"], eased_t, flyer["swirl_phase"])
                flyer["last_pos"] = pos
                flyer["last_t"] = eased_t

            head_progress = eased_t
            white = np.array([1.0, 1.0, 1.0], dtype="f4")
            head_color = np.clip(flyer["color"] * 0.82 + white * 0.24, 0.0, 1.0)
            head_alpha = min(1.0, 0.55 + 0.35 * (0.4 + 0.6 * head_progress))
            head_size = flyer["head_size"] * (0.72 + 0.28 * (head_progress ** 1.7))

            heads.append([
                pos[0], pos[1], pos[2],
                head_size, head_alpha, flyer["swirl_phase"],
                head_color[0], head_color[1], head_color[2],
            ])

            if t < 1.0:
                new_flyers.append(flyer)

        self.active_flyers = new_flyers
        self.head_data = np.asarray(heads, dtype="f4") if len(heads) else np.zeros((0, 9), dtype="f4")

    def process_event_queue(self, max_messages=64):
        for _ in range(max_messages):
            try:
                event = self.event_queue.get_nowait()
            except queue.Empty:
                break

            if not isinstance(event, VisualEvent):
                continue

            position = event.position or [0.0, 0.0, 0.0]
            color = event.color or self.random_wave_color().tolist()
            duration = max(0.03, float(event.duration))
            intensity = max(0.0, float(event.intensity))
            size = event.size

            signal_coords = np.array(position[:3], dtype="f4")
            origin = self.signal_to_camera_spawn_world(signal_coords)
            self.spawn_flyer(
                origin=origin,
                color=np.array(color[:3], dtype="f4"),
                duration=duration,
                intensity=intensity,
                size=size,
            )

    def on_mouse_press(self, x, y, button, modifiers):
        if button != mouse.LEFT:
            return

        hit = self.screen_to_world_on_camera_plane(x, y)
        if hit is None:
            return

        self.spawn_flyer(hit, self.random_wave_color(), 0.35)

    def update(self, dt):
        self.time += dt
        self.process_event_queue()
        self.update_flyers()

        if self.trail_dirty:
            self.rebuild_trail_buffer()
        self.rebuild_head_buffer()

    def apply_config(self, cfg):
        self.camera_distance = float(cfg.get("camera_distance", self.camera_distance))
        self.camera_dolly_speed = float(cfg.get("camera_dolly_speed", self.camera_dolly_speed))
        self.spawn_forward_distance = float(cfg.get("spawn_forward_distance", self.spawn_forward_distance))
        self.spawn_ground_height = float(cfg.get("spawn_ground_height", self.spawn_ground_height))
        self.spawn_x_scale = float(cfg.get("spawn_x_scale", self.spawn_x_scale))
        self.spawn_y_scale = float(cfg.get("spawn_y_scale", self.spawn_y_scale))
        self.spawn_z_scale = float(cfg.get("spawn_z_scale", self.spawn_z_scale))
        self.trail_sample_distance = float(cfg.get("trail_sample_distance", self.trail_sample_distance))
        self.max_trail_points = int(cfg.get("max_trail_points", self.max_trail_points))

    def draw_points(self, vao, size_scale, max_size, glow_power, twinkle_amount):
        self.program["u_size_scale"].value = size_scale
        self.program["u_max_point_size"].value = max_size
        self.program["u_glow_power"].value = glow_power
        self.program["u_twinkle_amount"].value = twinkle_amount
        vao.render(mode=moderngl.POINTS)

    def draw(self):
        self.ctx.viewport = (0, 0, self.window.width, self.window.height)
        self.ctx.enable_only(moderngl.BLEND | moderngl.PROGRAM_POINT_SIZE)
        self.ctx.blend_func = moderngl.SRC_ALPHA, moderngl.ONE

        self.program["u_view"].write(self.get_view_matrix().T.tobytes())
        self.program["u_time"].value = self.time

        if self.trail_vao is not None:
            self.draw_points(
                self.trail_vao,
                size_scale=20.0,
                max_size=20.0,
                glow_power=0.28,
                twinkle_amount=0.0,
            )

        if self.head_vao is not None:
            self.draw_points(
                self.head_vao,
                size_scale=24.0,
                max_size=24.0,
                glow_power=0.45,
                twinkle_amount=0.08,
            )