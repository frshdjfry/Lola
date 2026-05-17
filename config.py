#!/usr/bin/env python3
from __future__ import annotations

import json
import threading
from copy import deepcopy
from pathlib import Path
from typing import Any, Dict, Optional


def _deep_merge(base: Dict[str, Any], incoming: Dict[str, Any]) -> Dict[str, Any]:
    out = deepcopy(base)
    for key, value in incoming.items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = _deep_merge(out[key], value)
        else:
            out[key] = deepcopy(value)
    return out


class ConfigStore:
    """
    Lean active-config store.

    Main ideas:
    - one active config in memory
    - load/save JSON files
    - update a whole mapping or a single key
    - support named presets stored as JSON files
    - allow dotted keys like: "visual.generator"
    """

    def __init__(
        self,
        config_path: str | Path | None = None,
        *,
        defaults: Optional[Dict[str, Any]] = None,
        presets_dir: str | Path | None = None,
    ):
        self._lock = threading.RLock()
        self._defaults: Dict[str, Any] = deepcopy(defaults or {})
        self._config: Dict[str, Any] = deepcopy(self._defaults)

        self._config_path: Optional[Path] = None
        self._presets_dir: Optional[Path] = Path(presets_dir).expanduser().resolve() if presets_dir else None
        self._current_preset_name: Optional[str] = None

        if config_path is not None:
            self.load(config_path)

    @property
    def config_path(self) -> Optional[Path]:
        return self._config_path

    @property
    def current_preset_name(self) -> Optional[str]:
        return self._current_preset_name

    def set_presets_dir(self, path: str | Path) -> Path:
        with self._lock:
            self._presets_dir = Path(path).expanduser().resolve()
            self._presets_dir.mkdir(parents=True, exist_ok=True)
            return self._presets_dir

    def load(self, path: str | Path) -> Dict[str, Any]:
        path = Path(path).expanduser().resolve()

        with path.open("r", encoding="utf-8") as f:
            loaded = json.load(f)

        if not isinstance(loaded, dict):
            raise ValueError("Config JSON root must be an object")

        preset_name = None
        if self._presets_dir is not None:
            try:
                path.relative_to(self._presets_dir)
                preset_name = path.stem
            except ValueError:
                preset_name = None

        with self._lock:
            self._config_path = path
            self._config = _deep_merge(self._defaults, loaded)
            self._current_preset_name = preset_name
            return deepcopy(self._config)

    def reset_to_defaults(self) -> Dict[str, Any]:
        with self._lock:
            self._config = deepcopy(self._defaults)
            self._current_preset_name = None
            return deepcopy(self._config)

    def snapshot(self) -> Dict[str, Any]:
        with self._lock:
            return deepcopy(self._config)

    def get(self, key: Optional[str] = None, default: Any = None) -> Any:
        with self._lock:
            if key is None or key == "":
                return deepcopy(self._config)

            cursor: Any = self._config
            for part in key.split("."):
                if not isinstance(cursor, dict) or part not in cursor:
                    return default
                cursor = cursor[part]
            return deepcopy(cursor)

    def set(self, key: str, value: Any) -> Any:
        if not key:
            raise ValueError("key must not be empty")

        parts = key.split(".")

        with self._lock:
            cursor = self._config
            for part in parts[:-1]:
                next_value = cursor.get(part)
                if not isinstance(next_value, dict):
                    next_value = {}
                    cursor[part] = next_value
                cursor = next_value

            cursor[parts[-1]] = deepcopy(value)
            return deepcopy(value)

    def update(self, values: Dict[str, Any], *, merge: bool = True) -> Dict[str, Any]:
        if not isinstance(values, dict):
            raise ValueError("values must be a dict")

        with self._lock:
            if merge:
                self._config = _deep_merge(self._config, values)
            else:
                self._config = deepcopy(values)
            return deepcopy(self._config)

    def save(self, path: str | Path | None = None) -> Path:
        with self._lock:
            target = Path(path).expanduser().resolve() if path is not None else self._config_path
            if target is None:
                raise ValueError("No config path set. Pass a path explicitly.")

            target.parent.mkdir(parents=True, exist_ok=True)
            with target.open("w", encoding="utf-8") as f:
                json.dump(self._config, f, indent=2, ensure_ascii=False)

            self._config_path = target
            return target

    def save_preset(self, name: str, *, presets_dir: str | Path | None = None) -> Path:
        if not name or not name.strip():
            raise ValueError("Preset name must not be empty")

        with self._lock:
            base_dir = Path(presets_dir).expanduser().resolve() if presets_dir else self._presets_dir
            if base_dir is None:
                raise ValueError("No presets_dir set. Pass one explicitly or set it first.")

            base_dir.mkdir(parents=True, exist_ok=True)
            path = base_dir / f"{name}.json"

            with path.open("w", encoding="utf-8") as f:
                json.dump(self._config, f, indent=2, ensure_ascii=False)

            self._current_preset_name = name
            return path

    def load_preset(self, name: str, *, presets_dir: str | Path | None = None) -> Dict[str, Any]:
        if not name or not name.strip():
            raise ValueError("Preset name must not be empty")

        with self._lock:
            base_dir = Path(presets_dir).expanduser().resolve() if presets_dir else self._presets_dir
            if base_dir is None:
                raise ValueError("No presets_dir set. Pass one explicitly or set it first.")

            path = base_dir / f"{name}.json"
            with path.open("r", encoding="utf-8") as f:
                loaded = json.load(f)

            if not isinstance(loaded, dict):
                raise ValueError("Preset JSON root must be an object")

            self._config = _deep_merge(self._defaults, loaded)
            self._current_preset_name = name
            return deepcopy(self._config)

    def save_to_current_preset(self) -> Path:
        with self._lock:
            if not self._current_preset_name:
                raise ValueError("No current preset loaded")
            return self.save_preset(self._current_preset_name)

    def list_presets(self, *, presets_dir: str | Path | None = None) -> list[str]:
        with self._lock:
            base_dir = Path(presets_dir).expanduser().resolve() if presets_dir else self._presets_dir
            if base_dir is None or not base_dir.exists():
                return []

            return sorted(p.stem for p in base_dir.glob("*.json") if p.is_file())

    def info(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "config_path": str(self._config_path) if self._config_path else None,
                "presets_dir": str(self._presets_dir) if self._presets_dir else None,
                "current_preset_name": self._current_preset_name,
            }
