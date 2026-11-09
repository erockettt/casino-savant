"""Vision integration layer — PROTOTYPE.

Status: the interface and the temporal-consistency logic are implemented and
tested. NO trained card recogniser ships yet: recognition accuracy has not been
measured on a labelled dataset, so no recogniser output is treated as reliable.
Until one is validated, screenshots are ingested for manual labelling only.

A recogniser implements `Recognizer.detect(frame) -> list[Detection]`.
`FrameAggregator` turns noisy per-frame detections into Observations only after
a card has been read with the same rank in `k` consecutive frames at or above
`min_conf`; disagreements are surfaced as conflicts, never resolved by guessing.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

from .table import Observation


@dataclass
class Detection:
    slot: str
    index: int
    rank: str
    confidence: float


class Recognizer(Protocol):
    def detect(self, frame) -> list[Detection]: ...


class NoRecognizer:
    """Placeholder that refuses to invent readings."""

    def detect(self, frame) -> list[Detection]:
        return []


@dataclass
class FrameAggregator:
    round_id: int
    k: int = 3
    min_conf: float = 0.9
    _streak: dict = field(default_factory=dict)     # (slot, index) -> (rank, count)
    emitted: set = field(default_factory=set)
    conflicts: list = field(default_factory=list)

    def push(self, frame_id: str, detections: list[Detection]) -> list[Observation]:
        out = []
        for d in detections:
            key = (d.slot, d.index)
            if key in self.emitted:
                continue
            if d.confidence < self.min_conf:
                self._streak.pop(key, None)
                continue
            prev = self._streak.get(key)
            if prev and prev[0] != d.rank:
                self.conflicts.append({"key": key, "frame": frame_id, "was": prev[0], "now": d.rank})
                self._streak[key] = (d.rank, 1)
                continue
            count = (prev[1] + 1) if prev else 1
            self._streak[key] = (d.rank, count)
            if count >= self.k:
                self.emitted.add(key)
                out.append(Observation(self.round_id, d.slot, d.index, d.rank, d.confidence, "vision", frame_id))
        return out
