from __future__ import annotations

import math
import queue
import time
from typing import Any, Dict

import moderngl
import numpy as np
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
    float depth_fade = clamp(1.4 / (0.4 + v_depth * 0.12), 0.25, 1.0);

    float alpha = v_alpha * glow * twinkle * depth_fade;
    f_color = vec4(v_color, alpha);
}
"""


DEFAULTS = {
    "waver": {
        "width": 1280,
        "height": 720,
        "num_particles": 22000,
        "camera_distance": -5.0,
        "source_plane_z": 0.0,
        "stream_half_length": 4.0,
        "stream_half_width": 3.0,
        "stream_half_height": 2.0,
        "fade_distance": 5.0,
        "wind_speed": 0.15,
        "spawn_jitter": 1.0,
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


def smoothstep(edge0, edge1, x):
    t = np.clip((x - edge0) / max(1e-6, edge1 - edge0), 0.0, 1.0)
    return t * t * (3.0 - 2.0 * t)


class Waver:
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

        self.num_particles = int(cfg["num_particles"])
        self.camera_distance = float(cfg["camera_distance"])
        self.source_plane_z = float(cfg["source_plane_z"])
        self.stream_half_length = float(cfg["stream_half_length"])
        self.stream_half_width = float(cfg["stream_half_width"])
        self.stream_half_height = float(cfg["stream_half_height"])
        self.fade_distance = float(cfg["fade_distance"])
        self.wind_speed = float(cfg["wind_speed"])
        self.spawn_jitter = float(cfg["spawn_jitter"])

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

        self.stream_center = np.array([0.0, 0.0, 0.0], dtype="f4")
        self.wind_dir = np.array([1.0, 0.18, -0.07], dtype="f4")
        self.wind_dir /= np.linalg.norm(self.wind_dir)

        ref = np.array([0.0, 1.0, 0.0], dtype="f4")
        if abs(np.dot(ref, self.wind_dir)) > 0.95:
            ref = np.array([1.0, 0.0, 0.0], dtype="f4")

        self.stream_right = np.cross(ref, self.wind_dir)
        self.stream_right /= np.linalg.norm(self.stream_right)
        self.stream_up = np.cross(self.wind_dir, self.stream_right)
        self.stream_up /= np.linalg.norm(self.stream_up)

        self.base_positions = np.zeros((self.num_particles, 3), dtype="f4")
        self.base_velocities = np.zeros((self.num_particles, 3), dtype="f4")
        self.base_sizes = self.rng.uniform(1.0, 3.5, self.num_particles).astype("f4")
        self.base_alpha = self.rng.uniform(0.08, 0.30, self.num_particles).astype("f4")
        self.phase = self.rng.uniform(0.0, math.tau, self.num_particles).astype("f4")

        neutral = np.array([0.86, 0.90, 1.00], dtype="f4")
        self.base_colors = np.tile(neutral, (self.num_particles, 1)).astype("f4")

        self.render_positions = np.zeros((self.num_particles, 3), dtype="f4")
        self.render_sizes = self.base_sizes.copy()
        self.render_alpha = self.base_alpha.copy()
        self.render_colors = self.base_colors.copy()

        self.particle_data = np.empty((self.num_particles, 9), dtype="f4")

        self.source_active = False
        self.source_pos = np.zeros(3, dtype="f4")
        self.press_color = np.array([0.65, 0.78, 1.0], dtype="f4")
        self.source_flash_until = 0.0
        self.source_data = np.array(
            [[0.0, 0.0, self.source_plane_z, 18.0, 0.9, 0.0, 0.65, 0.78, 1.0]],
            dtype="f4",
        )
        self.source_vbo = None
        self.source_vao = None

        self.press_active = False
        self.press_start_time = 0.0
        self.press_origin = np.zeros(3, dtype="f4")

        self.waves = []

        self.time = 0.0
        self.proj_mat = np.eye(4, dtype="f4")
        self.scene_radius = math.sqrt(
            self.stream_half_length**2 + self.stream_half_width**2 + self.stream_half_height**2
        )

        self.vbo = None
        self.vao = None

    def _cfg(self) -> Dict[str, Any]:
        merged = dict(DEFAULTS["waver"])
        if self.config_store is not None:
            current = self.config_store.get("waver", {}) or {}
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

        self.spawn_particles(np.arange(self.num_particles), random_axis=True)
        self.rebuild_particle_data()

        self.vbo = self.ctx.buffer(self.particle_data.tobytes())
        self.vao = self.ctx.vertex_array(
            self.program,
            [(self.vbo, "3f 1f 1f 1f 3f", "in_pos", "in_size", "in_alpha", "in_phase", "in_color")],
        )

        self.source_vbo = self.ctx.buffer(self.source_data.tobytes())
        self.source_vao = self.ctx.vertex_array(
            self.program,
            [(self.source_vbo, "3f 1f 1f 1f 3f", "in_pos", "in_size", "in_alpha", "in_phase", "in_color")],
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

    def process_event_queue(self, max_messages=64):
        for _ in range(max_messages):
            try:
                event = self.event_queue.get_nowait()
            except queue.Empty:
                break

            if not isinstance(event, VisualEvent):
                continue

            position = event.position or [0.0, 0.0, self.source_plane_z]
            color = event.color or self.random_wave_color().tolist()
            duration = max(0.03, float(event.duration))
            intensity = max(0.0, float(event.intensity))
            size = event.size

            origin = np.array(position[:3], dtype="f4")
            self.emit_wave_packet(origin, duration, np.array(color[:3], dtype="f4"), intensity=intensity, size=size)
            self.start_source_flash(origin, np.array(color[:3], dtype="f4"), 0.08 + min(0.20, duration * 0.15))

    def start_source_flash(self, origin, color, flash_duration):
        self.source_active = True
        self.source_pos[:] = origin
        self.source_data[0, :3] = origin
        self.source_data[0, 6:9] = color
        self.source_flash_until = self.time + flash_duration
        self.source_vbo.write(self.source_data.tobytes())

    def random_wave_color(self):
        base = self.wave_palette[self.rng.integers(0, len(self.wave_palette))].copy()
        soft_white = np.array([1.0, 1.0, 1.0], dtype="f4")
        return np.clip(base * 0.82 + soft_white * 0.18, 0.0, 1.0).astype("f4")

    def rebuild_particle_data(self):
        self.particle_data[:, :3] = self.render_positions
        self.particle_data[:, 3] = self.render_sizes
        self.particle_data[:, 4] = self.render_alpha
        self.particle_data[:, 5] = self.phase
        self.particle_data[:, 6:9] = self.render_colors

    def stream_to_world(self, axis, side, up):
        return (
            self.stream_center[None, :]
            + axis[:, None] * self.wind_dir[None, :]
            + side[:, None] * self.stream_right[None, :]
            + up[:, None] * self.stream_up[None, :]
        ).astype("f4")

    def world_to_stream(self, positions):
        rel = positions - self.stream_center[None, :]
        axis = rel @ self.wind_dir
        side = rel @ self.stream_right
        up = rel @ self.stream_up
        return axis, side, up

    def spawn_particles(self, indices, random_axis=False):
        count = len(indices)
        if count == 0:
            return

        if random_axis:
            axis = self.rng.uniform(-self.stream_half_length, self.stream_half_length, count).astype("f4")
        else:
            axis = self.rng.uniform(
                -self.stream_half_length - self.spawn_jitter,
                -self.stream_half_length + self.spawn_jitter,
                count,
            ).astype("f4")

        side = self.rng.uniform(-self.stream_half_width, self.stream_half_width, count).astype("f4")
        up = self.rng.uniform(-self.stream_half_height, self.stream_half_height, count).astype("f4")

        self.base_positions[indices] = self.stream_to_world(axis, side, up)

        drift = self.rng.normal(0.0, 0.12, (count, 3)).astype("f4")
        drift[:, 1] *= 0.45
        drift[:, 2] *= 0.60
        self.base_velocities[indices] = drift

        self.base_sizes[indices] = self.rng.uniform(1.0, 3.5, count).astype("f4")
        self.base_alpha[indices] = self.rng.uniform(0.08, 0.30, count).astype("f4")
        self.phase[indices] = self.rng.uniform(0.0, math.tau, count).astype("f4")

        neutral = np.array([0.86, 0.90, 1.00], dtype="f4")
        tint = self.rng.uniform(0.94, 1.04, (count, 1)).astype("f4")
        self.base_colors[indices] = np.clip(neutral[None, :] * tint, 0.0, 1.0)

    def resize(self, width, height):
        if self.ctx is None or self.program is None:
            return
        self.ctx.viewport = (0, 0, width, height)
        self.proj_mat = perspective(55.0, width / max(1, height), 0.1, 100.0)
        self.program["u_proj"].write(self.proj_mat.T.tobytes())

    def get_view_matrix(self):
        eye = np.array(
            [
                0.8 * math.sin(self.time * 0.15),
                0.35 * math.cos(self.time * 0.11),
                self.camera_distance + 2 + math.sin(time.time() * 0.2),
            ],
            dtype="f4",
        )
        target = np.array([0.0, 0.0, 0.0], dtype="f4")
        up = np.array([0.0, 1.0, 0.0], dtype="f4")
        return look_at(eye, target, up)

    def screen_to_world_on_plane(self, x, y, plane_z=None):
        x = float(np.clip(x, 0, self.window.width))
        y = float(np.clip(y, 0, self.window.height))

        if plane_z is None:
            plane_z = self.source_plane_z

        x_ndc = (2.0 * x / self.window.width) - 1.0
        y_ndc = (2.0 * y / self.window.height) - 1.0

        view = self.get_view_matrix()
        inv_vp = np.linalg.inv(self.proj_mat @ view)

        near = inv_vp @ np.array([x_ndc, y_ndc, -1.0, 1.0], dtype="f4")
        far = inv_vp @ np.array([x_ndc, y_ndc, 1.0, 1.0], dtype="f4")
        near /= near[3]
        far /= far[3]

        ray_origin = near[:3]
        ray_dir = far[:3] - near[:3]
        ray_dir /= np.linalg.norm(ray_dir)

        if abs(ray_dir[2]) < 1e-5:
            return None

        t = (plane_z - ray_origin[2]) / ray_dir[2]
        if t < 0.0:
            return None

        hit = ray_origin + ray_dir * t
        return hit.astype("f4")

    def emit_wave_packet(self, origin, click_duration, color, intensity=1.0, size=None):
        d = float(np.clip(click_duration, 0.03, 1.4))
        strength = d / 1.4
        intensity = float(np.clip(intensity, 0.1, 3.0))

        packet_length = 1.2 + 6.2 * strength * intensity
        cycles = 1.2 + 6.0 * strength
        wavelength = packet_length / cycles

        amplitude = 0.018 + 0.70 * strength * intensity
        alpha_boost = (0.92 + 0.30 * strength) * intensity
        size_boost = 0.10 + 0.45 * strength * intensity
        color_boost = 9.65 + 1.30 * strength * intensity

        if size is not None:
            try:
                size_boost *= max(0.2, float(size))
            except (TypeError, ValueError):
                pass

        self.waves.append(
            {
                "origin": origin.astype("f4").copy(),
                "start_time": self.time,
                "speed": 3.0,
                "packet_length": packet_length,
                "wavelength": wavelength,
                "amplitude": amplitude,
                "alpha_boost": alpha_boost,
                "size_boost": size_boost,
                "distance_falloff": 1.18,
                "color": color.astype("f4").copy(),
                "color_boost": color_boost,
            }
        )

    def on_mouse_press(self, x, y, button, modifiers):
        if button != mouse.LEFT:
            return

        hit = self.screen_to_world_on_plane(x, y)
        if hit is None:
            return

        self.press_active = True
        self.press_start_time = self.time
        self.press_origin[:] = hit

        self.press_color = self.random_wave_color()

        self.source_active = True
        self.source_pos[:] = hit
        self.source_data[0, :3] = hit
        self.source_data[0, 6:9] = self.press_color
        self.source_vbo.write(self.source_data.tobytes())

    def on_mouse_release(self, x, y, button, modifiers):
        if button != mouse.LEFT or not self.press_active:
            return

        duration = self.time - self.press_start_time
        self.emit_wave_packet(self.press_origin, duration, self.press_color)

        self.press_active = False
        self.start_source_flash(self.press_origin, self.press_color, 0.12)

    def flow_visibility(self):
        axis, side, up = self.world_to_stream(self.base_positions)

        fade_in = smoothstep(
            -self.stream_half_length,
            -self.stream_half_length + self.fade_distance,
            axis,
        )
        fade_out = 1.0 - smoothstep(
            self.stream_half_length - self.fade_distance,
            self.stream_half_length,
            axis,
        )

        side_fade = 1.0 - smoothstep(
            self.stream_half_width - 2.0,
            self.stream_half_width + 0.75,
            np.abs(side),
        )
        up_fade = 1.0 - smoothstep(
            self.stream_half_height - 2.0,
            self.stream_half_height + 0.75,
            np.abs(up),
        )

        return fade_in * fade_out * side_fade * up_fade

    def apply_waves_to_render_state(self):
        self.render_positions[:] = self.base_positions
        flow_alpha = self.flow_visibility()

        self.render_sizes[:] = self.base_sizes
        self.render_alpha[:] = self.base_alpha * flow_alpha
        self.render_colors[:] = self.base_colors

        alive = []

        for wave in self.waves:
            age = self.time - wave["start_time"]
            if age < 0.0:
                alive.append(wave)
                continue

            front_radius = wave["speed"] * age
            if front_radius - wave["packet_length"] > self.scene_radius + 20.0:
                continue

            delta = self.base_positions - wave["origin"][None, :]
            dist = np.sqrt(np.sum(delta * delta, axis=1)) + 1e-6

            local = front_radius - dist
            mask = (local >= 0.0) & (local <= wave["packet_length"])

            if np.any(mask):
                local_m = local[mask]
                dist_m = dist[mask]
                dir_m = delta[mask] / dist_m[:, None]

                x = local_m / wave["packet_length"]
                envelope = np.sin(np.pi * x) ** 1.75

                phase = 2.0 * np.pi * (local_m / wave["wavelength"])
                attenuation = 1.0 / (1.0 + wave["distance_falloff"] * dist_m * dist_m)

                radial_disp = wave["amplitude"] * envelope * np.sin(phase) * attenuation
                self.render_positions[mask] += dir_m * radial_disp[:, None]

                crest = envelope * (0.35 + 0.65 * np.abs(np.sin(phase))) * attenuation
                self.render_alpha[mask] += wave["alpha_boost"] * crest * flow_alpha[mask]
                self.render_sizes[mask] += wave["size_boost"] * crest

                mix_strength = np.clip(
                    wave["color_boost"] * crest * flow_alpha[mask],
                    0.0,
                    0.95,
                )[:, None]
                self.render_colors[mask] += (
                    wave["color"][None, :] - self.base_colors[mask]
                ) * mix_strength

            alive.append(wave)

        self.waves = alive

        np.clip(self.render_alpha, 0.0, 1.0, out=self.render_alpha)
        np.clip(self.render_sizes, 0.8, 7.0, out=self.render_sizes)
        np.clip(self.render_colors, 0.0, 1.0, out=self.render_colors)

    def update_base_motion(self, dt):
        wind = self.wind_dir * (
            self.wind_speed - abs(math.sin(time.time() * 0.5)) + abs(math.sin(time.time() * 0.2))
        )

        self.base_velocities *= 0.9988
        self.base_positions += (wind[None, :] + self.base_velocities) * dt

        flutter = np.array(
            [
                0.020 * math.sin(self.time * 0.60),
                0.010 * math.cos(self.time * 0.35),
                0.015 * math.sin(self.time * 0.45),
            ],
            dtype="f4",
        )
        self.base_positions += flutter[None, :] * dt

        speed = np.linalg.norm(self.base_velocities, axis=1, keepdims=True)
        self.base_velocities /= np.maximum(1.0, speed / 0.65)

        axis, side, up = self.world_to_stream(self.base_positions)
        respawn_mask = (
            (axis > self.stream_half_length + self.spawn_jitter)
            | (np.abs(side) > self.stream_half_width + 1.5)
            | (np.abs(up) > self.stream_half_height + 1.5)
        )

        respawn_indices = np.where(respawn_mask)[0]
        if len(respawn_indices):
            self.spawn_particles(respawn_indices, random_axis=False)

    def update(self, dt):
        self.time += dt

        self.process_event_queue()
        self.update_base_motion(dt)
        self.apply_waves_to_render_state()

        if self.press_active:
            pulse = 16.0 + 4.0 * (0.5 + 0.5 * math.sin(self.time * 9.0))
            self.source_data[0, 3] = pulse
            self.source_data[0, 4] = 0.78 + 0.17 * (0.5 + 0.5 * math.sin(self.time * 8.0))
            self.source_data[0, 6:9] = self.press_color
            self.source_vbo.write(self.source_data.tobytes())
        elif self.source_active:
            if self.time > self.source_flash_until:
                self.source_active = False
            else:
                flash_start = self.source_flash_until - 0.28
                denom = 0.28
                pulse = 14.0 + 6.0 * (1.0 - min(1.0, max(0.0, (self.time - flash_start) / denom)))
                self.source_data[0, 3] = max(10.0, pulse)
                self.source_data[0, 4] = 0.72
                self.source_vbo.write(self.source_data.tobytes())

        self.rebuild_particle_data()
        self.vbo.write(self.particle_data.tobytes())

    def apply_config(self, cfg):
        self.camera_distance = float(cfg.get("camera_distance", self.camera_distance))
        self.stream_half_length = float(cfg.get("stream_half_length", self.stream_half_length))
        self.stream_half_width = float(cfg.get("stream_half_width", self.stream_half_width))
        self.stream_half_height = float(cfg.get("stream_half_height", self.stream_half_height))
        self.fade_distance = float(cfg.get("fade_distance", self.fade_distance))
        self.wind_speed = float(cfg.get("wind_speed", self.wind_speed))
        self.spawn_jitter = float(cfg.get("spawn_jitter", self.spawn_jitter))

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

        # self.ctx.clear(0.015, 0.018, 0.028, 1.0)
        self.program["u_view"].write(self.get_view_matrix().T.tobytes())
        self.program["u_time"].value = self.time

        self.draw_points(
            self.vao,
            size_scale=2200.0,
            max_size=16.0,
            glow_power=1.3,
            twinkle_amount=0.18,
        )

        if self.source_active or self.press_active:
            self.draw_points(
                self.source_vao,
                size_scale=2400.0,
                max_size=28.0,
                glow_power=0.5,
                twinkle_amount=0.0,
            )