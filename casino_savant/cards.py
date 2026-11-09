"""Card and shoe primitives shared by every card-game engine.

Ranks are indexed 0..9 to keep shoe compositions small and hashable:
    index 0 -> Ace, 1 -> 2, ..., 8 -> 9, 9 -> ten-valued (10, J, Q, K)
A shoe composition is a tuple of 10 non-negative ints (cards remaining by rank).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Sequence

RANK_LABELS = ("A", "2", "3", "4", "5", "6", "7", "8", "9", "T")
_PARSE = {
    "A": 0, "1": 0, "ACE": 0,
    "2": 1, "3": 2, "4": 3, "5": 4, "6": 5, "7": 6, "8": 7, "9": 8,
    "T": 9, "10": 9, "J": 9, "Q": 9, "K": 9,
}
PER_DECK = (4, 4, 4, 4, 4, 4, 4, 4, 4, 16)

Comp = tuple[int, ...]


def parse_card(token: str) -> int:
    """Parse '10', 'T', 'K', 'Kh', 'a', '7s' ... into a rank index.

    Suits are accepted and ignored. Raises ValueError on anything unreadable;
    callers must never guess an unreadable card.
    """
    t = token.strip().upper()
    if not t:
        raise ValueError("empty card token")
    if t[-1] in "SHDC♠♥♦♣" and len(t) > 1:
        t = t[:-1]
    if t not in _PARSE:
        raise ValueError(f"unrecognised card {token!r}")
    return _PARSE[t]


def parse_cards(text: str | Iterable[str]) -> list[int]:
    if isinstance(text, str):
        tokens = text.replace(",", " ").split()
    else:
        tokens = list(text)
    return [parse_card(t) for t in tokens]


def label(rank: int) -> str:
    return RANK_LABELS[rank]


def full_shoe(decks: int) -> Comp:
    if decks < 1:
        raise ValueError("decks must be >= 1")
    return tuple(n * decks for n in PER_DECK)


def remove(comp: Comp, ranks: Iterable[int]) -> Comp:
    c = list(comp)
    for r in ranks:
        if c[r] <= 0:
            raise ValueError(f"card {label(r)} is not available in the shoe composition")
        c[r] -= 1
    return tuple(c)


def bj_value(rank: int) -> int:
    """Blackjack point value (ace returned as 1)."""
    return 10 if rank == 9 else rank + 1


def bac_value(rank: int) -> int:
    """Baccarat point value."""
    return 0 if rank == 9 else rank + 1


@dataclass(frozen=True)
class HandTotal:
    total: int   # best total (ace counted as 11 when it does not bust)
    soft: bool   # True when an ace is currently counted as 11

    @staticmethod
    def of(ranks: Sequence[int]) -> "HandTotal":
        hard = sum(bj_value(r) for r in ranks)
        if 0 in ranks and hard + 10 <= 21:
            return HandTotal(hard + 10, True)
        return HandTotal(hard, False)


def add_card(total: int, soft: bool, rank: int) -> tuple[int, bool]:
    """Add one card to a (total, soft) blackjack hand."""
    v = bj_value(rank)
    total += v
    if rank == 0 and total + 10 <= 21:
        total += 10
        soft = True
    if total > 21 and soft:
        total -= 10
        soft = False
    return total, soft
