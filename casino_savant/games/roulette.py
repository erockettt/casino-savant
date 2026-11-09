"""Exact roulette bet expectations for single-, double- and triple-zero wheels.

Each bet: (numbers covered, payout X:1). EV = p*X - (1-p) with modifications for
La Partage (half of even-money stakes returned on zero) and En Prison
(stake imprisoned; released at even money on the next spin, single imprisonment).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

Wheel = Literal["european", "american", "triple_zero"]

RED = {1, 3, 5, 7, 9, 12, 14, 16, 18, 19, 21, 23, 25, 27, 30, 32, 34, 36}

BETS = {
    # name: (numbers covered among 1..36 or zeros, payout)
    "straight": (1, 35),
    "split": (2, 17),
    "street": (3, 11),
    "corner": (4, 8),
    "six_line": (6, 5),
    "dozen": (12, 2),
    "column": (12, 2),
    "red": (18, 1), "black": (18, 1), "odd": (18, 1), "even": (18, 1), "low": (18, 1), "high": (18, 1),
}
EVEN_MONEY = {"red", "black", "odd", "even", "low", "high"}


@dataclass
class RouletteRules:
    wheel: Wheel = "european"
    la_partage: bool = False
    en_prison: bool = False

    @property
    def pockets(self) -> int:
        return {"european": 37, "american": 38, "triple_zero": 39}[self.wheel]

    @property
    def zeros(self) -> int:
        return self.pockets - 36


def bet_ev(rules: RouletteRules, bet: str) -> dict:
    n = rules.pockets
    if bet == "top_line":
        if rules.wheel != "american":
            raise ValueError("top line (0-00-1-2-3) exists only on double-zero wheels")
        k, pay = 5, 6
    elif bet == "basket" and rules.wheel == "european":
        k, pay = 4, 8  # 0-1-2-3 'first four'
    else:
        k, pay = BETS[bet]
    p = k / n
    q_zero = rules.zeros / n
    ev = p * pay - (1 - p)
    var = p * pay ** 2 + (1 - p) - ev ** 2
    note = ""
    if bet in EVEN_MONEY and rules.wheel == "european":
        if rules.la_partage:
            ev = p * 1 - (1 - p - q_zero) - 0.5 * q_zero
            var = p + (1 - p - q_zero) + 0.25 * q_zero - ev ** 2
            note = "La Partage: half stake returned on zero"
        elif rules.en_prison:
            # imprisoned once: next spin wins -> stake returned (0 net), else lost; zero again -> lost (single prison)
            ret_prison = p * 0 + (1 - p) * -1
            ev = p - (1 - p - q_zero) + q_zero * ret_prison
            var = p + (1 - p - q_zero) + q_zero * (1 - p) - ev ** 2
            note = "En Prison (single imprisonment; zero on the prison spin loses)"
    return {"bet": bet, "p_win": p, "payout": pay, "ev": ev, "house_edge": -ev, "variance": var, "note": note}


def analyze(rules: RouletteRules) -> dict:
    names = list(BETS) + (["top_line"] if rules.wheel == "american" else []) + (["basket"] if rules.wheel == "european" else [])
    rows = [bet_ev(rules, b) for b in names]
    rows.sort(key=lambda r: r["ev"], reverse=True)
    return {
        "rules": {"wheel": rules.wheel, "la_partage": rules.la_partage, "en_prison": rules.en_prison, "pockets": rules.pockets},
        "bets": rows,
        "recommendation": "NO BET",
        "explanation": (
            f"On a {rules.pockets}-pocket wheel every wager has negative expectation "
            f"(best: {rows[0]['bet']} at {rows[0]['ev']:+.4%}). Spins are independent, so past results "
            "('hot'/'cold' numbers, streaks) do not change the next spin's probabilities, and no betting "
            "progression changes the per-unit expectation. A real edge would require a physically biased "
            "wheel demonstrated with a large, wheel-specific dataset (see the bias-research module)."
        ),
    }
