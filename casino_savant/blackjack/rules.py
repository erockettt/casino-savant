"""Blackjack rule specification.

Every field is explicit. Nothing is inferred from a venue name: a venue profile
(see casino_savant.profiles) supplies values together with a verification flag.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Literal

DoubleRule = Literal["any", "9-11", "10-11"]
Surrender = Literal["none", "late"]
ShuffleMode = Literal["shoe", "csm", "per_hand"]


@dataclass(frozen=True)
class BlackjackRules:
    decks: int = 6
    dealer_hits_soft_17: bool = False
    blackjack_payout: float = 1.5          # 1.5 = 3:2, 1.2 = 6:5, 1.0 = even
    dealer_peeks: bool = True              # False = European no-hole-card (ENHC)
    enhc_lose_doubles_and_splits: bool = True  # ENHC: lose all bets to a dealer BJ (False = OBO)
    double_on: DoubleRule = "any"
    double_after_split: bool = True
    max_split_hands: int = 4               # 2 = no resplitting
    resplit_aces: bool = False
    hit_split_aces: bool = False
    surrender: Surrender = "late"
    insurance_offered: bool = True
    shuffle: ShuffleMode = "shoe"          # 'per_hand' = RNG game reshuffled every round
    penetration: float = 0.75              # fraction dealt before reshuffle (shoe games only)
    table_min: float | None = None
    table_max: float | None = None
    notes: tuple[str, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if self.decks < 1:
            raise ValueError("decks must be >= 1")
        if self.max_split_hands < 1:
            raise ValueError("max_split_hands must be >= 1")
        if not 0.0 < self.penetration <= 1.0:
            raise ValueError("penetration must be in (0, 1]")

    def can_double(self, total: int, soft: bool) -> bool:
        if self.double_on == "any":
            return True
        if soft:  # restricted-double games use hard totals only
            return False
        lo = 9 if self.double_on == "9-11" else 10
        return lo <= total <= 11

    @property
    def counting_meaningful(self) -> bool:
        """Card tracking carries information only if cards are not reshuffled every round."""
        return self.shuffle == "shoe"

    def describe(self) -> str:
        parts = [
            f"{self.decks}D",
            "H17" if self.dealer_hits_soft_17 else "S17",
            {1.5: "BJ 3:2", 1.2: "BJ 6:5", 1.0: "BJ 1:1"}.get(self.blackjack_payout, f"BJ pays {self.blackjack_payout}"),
            "peek" if self.dealer_peeks else ("ENHC" + ("" if self.enhc_lose_doubles_and_splits else " OBO")),
            f"DOA" if self.double_on == "any" else f"D{self.double_on}",
            "DAS" if self.double_after_split else "NDAS",
            "no resplit" if self.max_split_hands <= 2 else f"split to {self.max_split_hands}",
            "LS" if self.surrender == "late" else "no surrender",
            {"shoe": f"shoe pen {self.penetration:.0%}", "csm": "CSM", "per_hand": "reshuffle every hand"}[self.shuffle],
        ]
        return " ".join(parts)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["notes"] = list(self.notes)
        return d

    @staticmethod
    def from_dict(d: dict) -> "BlackjackRules":
        d = dict(d)
        if "notes" in d:
            d["notes"] = tuple(d["notes"])
        return BlackjackRules(**d)
