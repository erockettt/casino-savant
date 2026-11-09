"""Bankroll and risk mathematics.

* Kelly / fractional Kelly — returned ONLY for a positive estimated edge, and
  computed from a conservative (lower-confidence-bound) edge to account for
  estimation error.
* Risk of ruin, diffusion approximation: RoR = exp(-2 * mu * B / sigma^2) for mu > 0
  (infinite play).  For mu <= 0 ruin is certain with unlimited play.
* Finite-target ruin (gambler's ruin with drift) via Brownian motion with absorbing barriers.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field


def kelly_fraction(edge: float, variance: float) -> float:
    """Growth-optimal fraction of bankroll per round (small-edge approximation edge/variance)."""
    if edge <= 0:
        return 0.0
    return edge / variance


def stake_advice(edge_estimate: float, edge_se: float, variance: float, bankroll: float,
                 kelly_multiplier: float = 0.5, z: float = 1.645) -> dict:
    conservative = edge_estimate - z * edge_se
    if conservative <= 0:
        return {
            "recommended_bet": 0.0,
            "reason": (f"Estimated edge {edge_estimate:+.4%} is not positive at the one-sided 95% level "
                       f"(lower bound {conservative:+.4%}). Raising the stake on a non-positive edge only "
                       "scales expected loss and variance; it creates no advantage."),
            "conservative_edge": conservative,
        }
    f = kelly_multiplier * kelly_fraction(conservative, variance)
    return {
        "recommended_bet": f * bankroll,
        "fraction": f,
        "conservative_edge": conservative,
        "reason": f"{kelly_multiplier:g}x Kelly using the lower-bound edge {conservative:+.4%}.",
    }


def risk_of_ruin(mu: float, sigma: float, bankroll: float) -> float:
    """Infinite-horizon probability of losing `bankroll` (units) with per-round mean mu and sd sigma."""
    if mu <= 0:
        return 1.0
    return math.exp(-2 * mu * bankroll / sigma ** 2)


def ruin_before_target(mu: float, sigma: float, bankroll: float, target_gain: float) -> float:
    """P(lose `bankroll` before winning `target_gain`), Brownian approximation."""
    a, b = bankroll, target_gain
    if abs(mu) < 1e-12:
        return b / (a + b)
    k = 2 * mu / sigma ** 2
    # P(hit -a before +b) for drift mu
    num = math.exp(k * b) - 1
    den = math.exp(k * b) - math.exp(-k * a)
    return num / den


@dataclass
class SessionTracker:
    bankroll_start: float
    loss_limit: float | None = None
    max_bet: float | None = None
    rounds: int = 0
    wagered: float = 0.0
    net: float = 0.0
    expected: float = 0.0
    peak: float = 0.0
    max_drawdown: float = 0.0
    sum_sq: float = 0.0
    log: list = field(default_factory=list)

    def record(self, bet: float, result: float, expected_value: float = 0.0, note: str = "") -> dict:
        self.rounds += 1
        self.wagered += bet
        self.net += result
        self.expected += expected_value
        self.sum_sq += result ** 2
        self.peak = max(self.peak, self.net)
        self.max_drawdown = max(self.max_drawdown, self.peak - self.net)
        self.log.append({"bet": bet, "result": result, "ev": expected_value, "note": note})
        return self.status()

    def status(self) -> dict:
        alerts = []
        if self.loss_limit is not None and -self.net >= self.loss_limit:
            alerts.append("LOSS LIMIT REACHED — the plan says stop now. Past losses do not make a win 'due'.")
        mean = self.net / self.rounds if self.rounds else 0.0
        sd = math.sqrt(max(self.sum_sq / self.rounds - mean ** 2, 0)) if self.rounds else 0.0
        return {
            "rounds": self.rounds,
            "wagered": self.wagered,
            "net": self.net,
            "expected_net": self.expected,
            "luck": self.net - self.expected,
            "bankroll": self.bankroll_start + self.net,
            "max_drawdown": self.max_drawdown,
            "sd_per_round": sd,
            "alerts": alerts,
        }
