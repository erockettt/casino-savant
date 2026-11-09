"""Card-counting systems and an exact shoe-state tracker.

Tags are listed by rank index (A,2,3,4,5,6,7,8,9,T). Sources: Griffin, *The
Theory of Blackjack*; Wong, *Professional Blackjack*; Schlesinger, *Blackjack
Attack*; Snyder (Zen); Carlson (Omega II). Tag sets are standard and
self-consistent: balanced systems sum to zero over a deck (verified in tests).
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

from ..cards import Comp, PER_DECK, full_shoe, label

#                     A     2    3    4    5    6    7    8    9    T
SYSTEMS: dict[str, dict] = {
    "hilo":       {"tags": (-1, 1, 1, 1, 1, 1, 0, 0, 0, -1), "balanced": True, "name": "Hi-Lo"},
    "ko":         {"tags": (-1, 1, 1, 1, 1, 1, 1, 0, 0, -1), "balanced": False, "name": "Knock-Out (KO)"},
    "hiopt1":     {"tags": (0, 0, 1, 1, 1, 1, 0, 0, 0, -1), "balanced": True, "name": "Hi-Opt I", "ace_side": True},
    "hiopt2":     {"tags": (0, 1, 1, 2, 2, 1, 1, 0, 0, -2), "balanced": True, "name": "Hi-Opt II", "ace_side": True},
    "omega2":     {"tags": (0, 1, 1, 2, 2, 2, 1, 0, -1, -2), "balanced": True, "name": "Omega II", "ace_side": True},
    "halves":     {"tags": (-1, 0.5, 1, 1, 1.5, 1, 0.5, 0, -0.5, -1), "balanced": True, "name": "Wong Halves"},
    "zen":        {"tags": (-1, 1, 1, 2, 2, 2, 1, 0, 0, -2), "balanced": True, "name": "Zen Count"},
}


def system_tags(name: str) -> tuple[float, ...]:
    if name not in SYSTEMS:
        raise KeyError(f"unknown counting system {name!r}; choose from {sorted(SYSTEMS)}")
    return SYSTEMS[name]["tags"]


def ko_initial_running_count(decks: int) -> int:
    """Standard KO IRC convention: 4 - 4*decks (key count then ~ +2 for 6D/8D)."""
    return 4 - 4 * decks


@dataclass
class ShoeTracker:
    """Tracks every observed card exactly and derives count statistics.

    Observations are idempotent per `obs_id`: re-reporting the same physical card
    (e.g. the same card seen again in a later video frame) never double-counts.
    Unseen burned cards reduce the remaining-card total but not any rank.
    """
    decks: int
    system: str = "hilo"
    seen: list[int] = field(default_factory=lambda: [0] * 10)
    unseen_removed: int = 0
    obs_ids: set = field(default_factory=set)
    low_confidence: list = field(default_factory=list)
    history: list = field(default_factory=list)
    shuffles: int = 0

    @property
    def initial(self) -> Comp:
        return full_shoe(self.decks)

    @property
    def remaining(self) -> Comp:
        """Exact composition of cards not yet seen (still includes unseen burns)."""
        return tuple(i - s for i, s in zip(self.initial, self.seen))

    @property
    def cards_remaining(self) -> int:
        """Cards physically left in the shoe (excludes burned cards)."""
        return sum(self.remaining) - self.unseen_removed

    @property
    def decks_remaining(self) -> float:
        return max(self.cards_remaining, 1) / 52.0

    @property
    def penetration(self) -> float:
        return 1.0 - self.cards_remaining / (52 * self.decks)

    def observe(self, rank: int, *, obs_id: str | None = None, confidence: float = 1.0,
                min_confidence: float = 0.98, source: str = "manual") -> bool:
        """Record one exposed card. Returns True if counted.

        Cards below `min_confidence` are held for user confirmation, never counted.
        """
        if obs_id is not None and obs_id in self.obs_ids:
            return False
        if confidence < min_confidence:
            self.low_confidence.append({"rank": label(rank), "obs_id": obs_id, "confidence": confidence, "source": source})
            return False
        if self.seen[rank] >= self.initial[rank]:
            raise ValueError(
                f"Observed more {label(rank)} cards than a {self.decks}-deck shoe contains — "
                "likely a duplicate or misread; correct the input."
            )
        self.seen[rank] += 1
        if obs_id is not None:
            self.obs_ids.add(obs_id)
        self.history.append({"rank": label(rank), "obs_id": obs_id, "source": source, "confidence": confidence})
        return True

    def undo(self) -> None:
        if not self.history:
            return
        last = self.history.pop()
        from ..cards import parse_card
        self.seen[parse_card(last["rank"])] -= 1
        if last["obs_id"] is not None:
            self.obs_ids.discard(last["obs_id"])

    def burn_unseen(self, n: int = 1) -> None:
        self.unseen_removed += n

    def shuffle(self) -> None:
        self.seen = [0] * 10
        self.unseen_removed = 0
        self.obs_ids.clear()
        self.low_confidence.clear()
        self.history.clear()
        self.shuffles += 1

    # ------------------------------------------------------------ counts
    def running_count(self, system: str | None = None) -> float:
        sysname = system or self.system
        tags = system_tags(sysname)
        rc = sum(t * s for t, s in zip(tags, self.seen))
        if sysname == "ko":
            rc += ko_initial_running_count(self.decks)
        return rc

    def true_count(self, system: str | None = None, *, rounding: str = "floor") -> float | None:
        """Running count per deck remaining. None for unbalanced systems (KO uses the RC)."""
        sysname = system or self.system
        if not SYSTEMS[sysname]["balanced"]:
            return None
        tc = self.running_count(sysname) / self.decks_remaining
        if rounding == "floor":
            return math.floor(tc)
        if rounding == "truncate":
            return float(int(tc))
        return tc

    def aces_rich(self) -> float:
        """Ace side count: surplus aces remaining relative to a neutral shoe."""
        rem = self.remaining
        expected = 4 * self.decks * (sum(rem) / (52 * self.decks))
        return rem[0] - expected

    def count_uncertainty(self) -> float:
        """Std. dev. of the TRUE count induced by unseen burn cards (Hi-Lo tags, sampling w/o replacement approx)."""
        if self.unseen_removed == 0:
            return 0.0
        rem = self.remaining
        n = sum(rem)
        tags = system_tags(self.system)
        mean = sum(t * c for t, c in zip(tags, rem)) / n
        var = sum(c * (t - mean) ** 2 for t, c in zip(tags, rem)) / n
        k = self.unseen_removed
        fpc = (n - k) / max(n - 1, 1)
        return math.sqrt(k * var * fpc) / self.decks_remaining

    def snapshot(self) -> dict:
        tc_raw = self.true_count(rounding="none")
        return {
            "system": SYSTEMS[self.system]["name"],
            "decks": self.decks,
            "cards_seen": sum(self.seen),
            "unseen_burns": self.unseen_removed,
            "cards_remaining": self.cards_remaining,
            "decks_remaining": round(self.decks_remaining, 3),
            "penetration": round(self.penetration, 4),
            "running_count": self.running_count(),
            "true_count": None if tc_raw is None else round(tc_raw, 3),
            "true_count_floor": self.true_count(),
            "true_count_sd_from_burns": round(self.count_uncertainty(), 3),
            "aces_rich": round(self.aces_rich(), 2),
            "remaining_by_rank": dict(zip([label(i) for i in range(10)], self.remaining)),
            "pending_low_confidence": list(self.low_confidence),
            "shuffles": self.shuffles,
        }


# Published Hi-Lo indices (Schlesinger, Blackjack Attack, multi-deck S17 DAS).
# Status: EMPIRICALLY SUPPORTED in the literature; NOT re-derived here. The
# composition-dependent solver (exact remaining composition) supersedes these
# whenever a full tracked composition is available.
ILLUSTRIOUS_18 = [
    # (description, player hand, upcard, index, action at/above index, action below)
    ("Insurance", "any", "A", 3, "TAKE", "DECLINE"),
    ("16 v T", "hard16", "T", 0, "STAND", "HIT"),
    ("15 v T", "hard15", "T", 4, "STAND", "HIT"),
    ("T,T v 5", "pairT", "5", 5, "SPLIT", "STAND"),
    ("T,T v 6", "pairT", "6", 4, "SPLIT", "STAND"),
    ("10 v T", "hard10", "T", 4, "DOUBLE", "HIT"),
    ("12 v 3", "hard12", "3", 2, "STAND", "HIT"),
    ("12 v 2", "hard12", "2", 3, "STAND", "HIT"),
    ("11 v A", "hard11", "A", 1, "DOUBLE", "HIT"),
    ("9 v 2", "hard9", "2", 1, "DOUBLE", "HIT"),
    ("10 v A", "hard10", "A", 4, "DOUBLE", "HIT"),
    ("9 v 7", "hard9", "7", 3, "DOUBLE", "HIT"),
    ("16 v 9", "hard16", "9", 5, "STAND", "HIT"),
    ("13 v 2", "hard13", "2", -1, "STAND", "HIT"),
    ("12 v 4", "hard12", "4", 0, "STAND", "HIT"),
    ("12 v 5", "hard12", "5", -2, "STAND", "HIT"),
    ("12 v 6", "hard12", "6", -1, "STAND", "HIT"),
    ("13 v 3", "hard13", "3", -2, "STAND", "HIT"),
]
FAB_4 = [
    ("14 v T", "hard14", "T", 3, "SURRENDER", "basic"),
    ("15 v T", "hard15", "T", 0, "SURRENDER", "basic"),
    ("15 v 9", "hard15", "9", 2, "SURRENDER", "basic"),
    ("15 v A", "hard15", "A", 1, "SURRENDER", "basic"),
]
