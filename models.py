from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
import time
import uuid



def new_id() -> str:
    return uuid.uuid4().hex[:12]


@dataclass(slots=True)
class Word:
    """Shared word protocol used across modules."""

    text: str
    features: Dict[str, float] = field(default_factory=dict)
    meta: Dict[str, Any] = field(default_factory=dict)

    def feature(self, name: str, default: float = 0.5) -> float:
        value = self.features.get(name, default)
        try:
            return float(value)
        except (TypeError, ValueError):
            return float(default)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "text": self.text,
            "features": dict(self.features),
            "meta": dict(self.meta),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Word":
        return cls(
            text=str(data.get("text", "")).strip(),
            features=dict(data.get("features") or {}),
            meta=dict(data.get("meta") or {}),
        )


@dataclass(slots=True)
class Utterance:
    """One detected speech unit sent from speech to composer."""

    words: List[Word]
    text: str = ""
    utterance_id: str = field(default_factory=new_id)
    audio: Any = None
    meta: Dict[str, Any] = field(default_factory=dict)
    created_at: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "utterance_id": self.utterance_id,
            "text": self.text,
            "words": [word.to_dict() for word in self.words],
            "meta": dict(self.meta),
            "created_at": self.created_at,
        }


@dataclass(slots=True)
class StateUpdate:
    """Broadcast live global state updates, usually from speech."""

    values: Dict[str, float]
    source: str = "speech"
    update_id: str = field(default_factory=new_id)
    created_at: float = field(default_factory=time.time)

    def value(self, name: str, default: float = 0.5) -> float:
        raw = self.values.get(name, default)
        try:
            return float(raw)
        except (TypeError, ValueError):
            return float(default)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "source": self.source,
            "update_id": self.update_id,
            "values": dict(self.values),
            "created_at": self.created_at,
        }


@dataclass(slots=True)
class VisualEvent:
    """Message emitted by composer and consumed by visual generators."""

    word: Word
    duration: float
    intensity: float = 1.0
    position: Optional[List[float]] = None
    color: Optional[List[float]] = None
    size: Optional[float] = None
    generator: Optional[str] = None
    meta: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "word": self.word.to_dict(),
            "duration": self.duration,
            "intensity": self.intensity,
            "position": list(self.position) if self.position is not None else None,
            "color": list(self.color) if self.color is not None else None,
            "size": self.size,
            "generator": self.generator,
            "meta": dict(self.meta),
        }


@dataclass(slots=True)
class NoteEvent:
    """Message emitted by composer and consumed by playback."""

    word: Word
    note: int
    velocity: int
    duration: float
    voice: int = 1
    channel: int = 1
    meta: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "word": self.word.to_dict(),
            "note": self.note,
            "velocity": self.velocity,
            "duration": self.duration,
            "voice": self.voice,
            "channel": self.channel,
            "meta": dict(self.meta),
        }


@dataclass
class TranscriptEvent:
    text: str
    kind: str = "final"   # "partial", "final", "partial_clear"
    utterance_id: Optional[str] = None
    words: List[Word] = field(default_factory=list)
