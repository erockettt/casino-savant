"""Betting-progression laboratory.

Hypothesis under test: "progression X changes the expected return per unit
wagered on a fixed-odds negative-EV bet."  Mathematical result (PROVEN): for
independent rounds, E[net] = edge * E[total wagered] for ANY stopping/staking
rule that depends only on past outcomes (optional-stopping theorem applied to
the martingale net - edge * wagered).  The simulation checks this empirically
and shows how progressions reshape the distribution (many small wins, rare
large losses) without changing the per-unit expectation.
"""
from __future__ import annotations

import math
import random
from dataclasses import dataclass


@dataclass
class BetSpec:
    p_win: float
    p_push: float
    win_pays: float  # net profit per unit on a win

    @property
    def edge(self) -> float:
        return self.p_win * self.win_pays - (1 - self.p_win - self.p_push)


EUROPEAN_RED = BetSpec(18 / 37, 0.0, 1.0)
AMERICAN_RED = BetSpec(18 / 38, 0.0, 1.0)
# Baccarat banker (8 decks, 5% commission): ties push
BACCARAT_BANKER = BetSpec(0.458597, 0.095156, 0.95)
BACCARAT_PLAYER = BetSpec(0.446247, 0.095156, 1.0)


def _fib(n):
    a, b = 1, 1
    for _ in range(n):
        a, b = b, a + b
    return a


class Progression:
    name = "flat"

    def __init__(self, base: float = 1.0, table_max: float = 500.0):
        self.base, self.table_max = base, table_max
        self.reset()

    def reset(self):
        self.state = 0

    def bet(self) -> float:
        return self.base

    def update(self, outcome: int) -> None:  # +1 win, 0 push, -1 loss
        pass


class Martingale(Progression):
    name = "martingale"

    def bet(self):
        return min(self.base * 2 ** self.state, self.table_max)

    def update(self, o):
        if o > 0:
            self.state = 0
        elif o < 0:
            self.state += 1


class ReverseMartingale(Progression):
    """Double after every win (capped by table max); reset after a loss."""
    name = "reverse_martingale"

    def bet(self):
        return min(self.base * 2 ** self.state, self.table_max)

    def update(self, o):
        if o > 0:
            self.state += 1
        elif o < 0:
            self.state = 0


class Fibonacci(Progression):
    name = "fibonacci"

    def bet(self):
        return min(self.base * _fib(self.state), self.table_max)

    def update(self, o):
        if o > 0:
            self.state = max(self.state - 2, 0)
        elif o < 0:
            self.state += 1


class DAlembert(Progression):
    name = "dalembert"

    def bet(self):
        return min(self.base * (1 + self.state), self.table_max)

    def update(self, o):
        if o > 0:
            self.state = max(self.state - 1, 0)
        elif o < 0:
            self.state += 1


class Paroli(ReverseMartingale):
    """Reverse Martingale that banks the profit after three consecutive wins."""
    name = "paroli"

    def update(self, o):
        if o > 0:
            self.state = self.state + 1 if self.state < 2 else 0
        elif o < 0:
            self.state = 0


class Labouchere(Progression):
    name = "labouchere"

    def reset(self):
        self.seq = [1, 2, 3, 4]

    def bet(self):
        if not self.seq:
            self.reset()
        b = self.seq[0] + (self.seq[-1] if len(self.seq) > 1 else 0)
        return min(self.base * b, self.table_max)

    def update(self, o):
        if not self.seq:
            self.reset()
        b = self.seq[0] + (self.seq[-1] if len(self.seq) > 1 else 0)
        if o > 0:
            self.seq = self.seq[1:-1]
        elif o < 0:
            self.seq.append(b)


PROGRESSIONS = {c.name: c for c in (Progression, Martingale, ReverseMartingale, Fibonacci, DAlembert, Paroli, Labouchere)}


def simulate_sessions(spec: BetSpec, prog_name: str, *, sessions: int = 20_000, rounds: int = 100,
                      bankroll: float = 200.0, base: float = 1.0, table_max: float = 500.0,
                      seed: int = 1) -> dict:
    rng = random.Random(seed)
    nets, wagers = [], []
    busts = winners = 0
    for _ in range(sessions):
        prog = PROGRESSIONS[prog_name](base, table_max)
        bank, wag = bankroll, 0.0
        for _ in range(rounds):
            b = min(prog.bet(), bank)
            if b <= 0:
                break
            u = rng.random()
            if u < spec.p_win:
                o, d = 1, b * spec.win_pays
            elif u < spec.p_win + spec.p_push:
                o, d = 0, 0.0
            else:
                o, d = -1, -b
            bank += d
            wag += b
            prog.update(o)
        net = bank - bankroll
        nets.append(net)
        wagers.append(wag)
        busts += bank <= 0
        winners += net > 0
    n = len(nets)
    tot_w = sum(wagers)
    tot_n = sum(nets)
    # ratio estimator with delta-method standard error
    per_unit = tot_n / tot_w
    mw = tot_w / n
    resid = [x - per_unit * w for x, w in zip(nets, wagers)]
    se = math.sqrt(sum(r * r for r in resid) / (n - 1) / n) / mw
    mean_net = tot_n / n
    sd_net = math.sqrt(sum((x - mean_net) ** 2 for x in nets) / (n - 1))
    return {
        "progression": prog_name,
        "theoretical_edge_per_unit": spec.edge,
        "observed_return_per_unit_wagered": per_unit,
        "ci95": (per_unit - 1.96 * se, per_unit + 1.96 * se),
        "edge_inside_ci": per_unit - 1.96 * se <= spec.edge <= per_unit + 1.96 * se,
        "p_session_win": winners / n,
        "p_bust": busts / n,
        "mean_net": mean_net,
        "sd_net": sd_net,
        "mean_wagered": mw,
        "worst_session": min(nets),
        "sessions": n, "rounds_per_session": rounds, "bankroll": bankroll, "seed": seed,
    }
