"""Exact baccarat probabilities for any finite shoe composition.

Enumerates P1, B1, P2, B2 and any third cards with removal (Punto Banco
tableau). Composition is by baccarat point value 0..9 (value 0 = 10/J/Q/K).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from functools import lru_cache

from ..cards import Comp, bac_value

BacComp = tuple[int, ...]  # counts by point value 0..9


def bac_shoe(decks: int) -> BacComp:
    return (16 * decks,) + (4 * decks,) * 9


def from_rank_comp(comp: Comp) -> BacComp:
    """Convert a rank composition (A..T) to point-value composition (0..9)."""
    c = [0] * 10
    for rank, n in enumerate(comp):
        c[bac_value(rank)] += n
    return tuple(c)


def banker_draws(b: int, p3: int | None) -> bool:
    if p3 is None:
        return b <= 5
    if b <= 2:
        return True
    if b == 3:
        return p3 != 8
    if b == 4:
        return 2 <= p3 <= 7
    if b == 5:
        return 4 <= p3 <= 7
    if b == 6:
        return p3 in (6, 7)
    return False


@dataclass(frozen=True)
class Outcome:
    winner: str          # 'B' | 'P' | 'T'
    b_total: int
    p_total: int
    b_cards: int
    p_cards: int
    player_pair: bool
    banker_pair: bool


@lru_cache(maxsize=64)
def outcome_distribution(comp: BacComp) -> dict[Outcome, float]:
    """Exact probability of every distinguishable round outcome."""
    n0 = sum(comp)
    if n0 < 6:
        raise ValueError("need at least 6 cards to complete a round")
    c = list(comp)
    dist: dict[Outcome, float] = {}

    def take(v: int, n: int) -> float:
        p = c[v] / n
        c[v] -= 1
        return p

    for p1 in range(10):
        if not c[p1]:
            continue
        w1 = take(p1, n0)
        for b1 in range(10):
            if not c[b1]:
                continue
            w2 = w1 * take(b1, n0 - 1)
            for p2 in range(10):
                if not c[p2]:
                    continue
                w3 = w2 * take(p2, n0 - 2)
                for b2 in range(10):
                    if not c[b2]:
                        continue
                    w4 = w3 * take(b2, n0 - 3)
                    pt, bt = (p1 + p2) % 10, (b1 + b2) % 10
                    ppair, bpair = p1 == p2, b1 == b2
                    # Note: pair bets are defined by rank, and 10/J/Q/K share value 0.
                    # Value-0 "pairs" are corrected in pair_probability(); outcomes here
                    # flag value equality only.
                    if pt >= 8 or bt >= 8:
                        _acc(dist, pt, bt, 2, 2, ppair, bpair, w4)
                    elif pt <= 5:
                        n = n0 - 4
                        for p3 in range(10):
                            if not c[p3]:
                                continue
                            w5 = w4 * take(p3, n)
                            pt3 = (pt + p3) % 10
                            if banker_draws(bt, p3):
                                for b3 in range(10):
                                    if not c[b3]:
                                        continue
                                    w6 = w5 * c[b3] / (n - 1)
                                    _acc(dist, pt3, (bt + b3) % 10, 3, 3, ppair, bpair, w6)
                            else:
                                _acc(dist, pt3, bt, 3, 2, ppair, bpair, w5)
                            c[p3] += 1
                    else:  # player stands on 6/7
                        if bt <= 5:
                            n = n0 - 4
                            for b3 in range(10):
                                if c[b3]:
                                    _acc(dist, pt, (bt + b3) % 10, 2, 3, ppair, bpair, w4 * c[b3] / n)
                        else:
                            _acc(dist, pt, bt, 2, 2, ppair, bpair, w4)
                    c[b2] += 1
                c[p2] += 1
            c[b1] += 1
        c[p1] += 1
    return dist


def _acc(dist, pt, bt, pc, bc, pp, bp, w):
    winner = "P" if pt > bt else "B" if bt > pt else "T"
    key = Outcome(winner, bt, pt, bc, pc, pp, bp)
    dist[key] = dist.get(key, 0.0) + w


def pair_probability(rank_comp: Comp) -> float:
    """P(first two cards of a hand are the same RANK) — exact for a rank composition.

    10, J, Q, K are distinct ranks; the rank composition lumps them, so we assume
    the ten-valued group is split evenly into four ranks (true for any shoe dealt
    without bias towards a particular face; stated assumption).
    """
    n = sum(rank_comp)
    tot = 0.0
    for r, cnt in enumerate(rank_comp):
        if r == 9:
            per = cnt / 4
            tot += 4 * (per / n) * ((per - 1) / (n - 1)) if per >= 1 else 0.0
        else:
            tot += (cnt / n) * ((cnt - 1) / (n - 1)) if cnt >= 1 else 0.0
    return tot


@dataclass
class BaccaratRules:
    decks: int = 8
    variant: str = "commission"     # 'commission' | 'no_commission_6' (banker 6 pays 1:2) | 'ez' (banker 3-card 7 pushes)
    commission: float = 0.05
    tie_pays: float = 8.0
    pair_pays: float = 11.0
    notes: tuple[str, ...] = field(default_factory=tuple)


@dataclass
class BetEV:
    bet: str
    ev: float              # per unit wagered
    p_win: float
    p_push: float
    p_lose: float
    variance: float


def analyze(rules: BaccaratRules, rank_comp: Comp | None = None) -> dict:
    from ..cards import full_shoe
    rc = rank_comp if rank_comp is not None else full_shoe(rules.decks)
    dist = outcome_distribution(from_rank_comp(rc))
    pB = sum(p for o, p in dist.items() if o.winner == "B")
    pP = sum(p for o, p in dist.items() if o.winner == "P")
    pT = sum(p for o, p in dist.items() if o.winner == "T")

    bets: list[BetEV] = []

    # Banker
    if rules.variant == "commission":
        pay = {"win": 1 - rules.commission}
        win_probs = [(1 - rules.commission, pB)]
    elif rules.variant == "no_commission_6":
        p_b6 = sum(p for o, p in dist.items() if o.winner == "B" and o.b_total == 6)
        win_probs = [(1.0, pB - p_b6), (0.5, p_b6)]
    elif rules.variant == "ez":
        p_b7_3 = sum(p for o, p in dist.items() if o.winner == "B" and o.b_total == 7 and o.b_cards == 3)
        win_probs = [(1.0, pB - p_b7_3), (0.0, p_b7_3)]
    else:
        raise ValueError(f"unknown variant {rules.variant}")
    ev_b = sum(a * p for a, p in win_probs) - pP
    m2 = sum(a * a * p for a, p in win_probs) + pP
    push_b = pT + sum(p for a, p in win_probs if a == 0)
    bets.append(BetEV("BANKER", ev_b, pB - push_b + pT, push_b, pP, m2 - ev_b ** 2))
    ev_p = pP - pB
    bets.append(BetEV("PLAYER", ev_p, pP, pT, pB, (pP + pB) - ev_p ** 2))
    ev_t = rules.tie_pays * pT - (1 - pT)
    bets.append(BetEV("TIE", ev_t, pT, 0.0, 1 - pT, rules.tie_pays ** 2 * pT + (1 - pT) - ev_t ** 2))
    pp = pair_probability(rc)
    ev_pair = rules.pair_pays * pp - (1 - pp)
    var_pair = rules.pair_pays ** 2 * pp + (1 - pp) - ev_pair ** 2
    bets.append(BetEV("PLAYER PAIR", ev_pair, pp, 0.0, 1 - pp, var_pair))
    bets.append(BetEV("BANKER PAIR", ev_pair, pp, 0.0, 1 - pp, var_pair))

    bets.sort(key=lambda b: b.ev, reverse=True)
    rec = bets[0].bet if bets[0].ev > 0 else "NO BET"
    return {
        "rules": rules.__dict__ | {"notes": list(rules.notes)},
        "cards_remaining": sum(rc),
        "p_banker": pB, "p_player": pP, "p_tie": pT,
        "bets": [b.__dict__ for b in bets],
        "recommendation": rec,
        "explanation": (
            f"Best available wager is {bets[0].bet} at {bets[0].ev:+.4%} per unit. "
            + ("It has positive expectation for this exact composition." if bets[0].ev > 0 else
               "Every wager has negative expectation, so the mathematically optimal choice is not to bet. "
               "Road patterns and streaks do not change these probabilities: each round's odds depend only on the cards remaining.")
        ),
    }
