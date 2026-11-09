"""Independent infinite-deck (total-dependent) blackjack solver.

Deliberately written separately from solver.py (different state representation,
no card removal) so the two can validate each other: as the number of decks
grows, the composition-dependent solver must converge to these values.

Also used to generate a rule-specific total-dependent basic-strategy table for
the simulation laboratory.
"""
from __future__ import annotations

from functools import lru_cache

from .rules import BlackjackRules

# probability of each point value 1..10 (1 = ace)
P = {v: (4 / 13 if v == 10 else 1 / 13) for v in range(1, 11)}


def _add(total: int, soft: bool, v: int) -> tuple[int, bool]:
    total += v
    if v == 1 and total + 10 <= 21:
        return total + 10, True
    if total > 21 and soft:
        return total - 10, False
    return total, soft


class InfiniteDeck:
    def __init__(self, rules: BlackjackRules):
        self.r = rules
        self._dealer = lru_cache(maxsize=None)(self._dealer_impl)
        self._hit = lru_cache(maxsize=None)(self._hit_impl)

    def _dealer_impl(self, total: int, soft: bool) -> tuple[float, ...]:
        if total > 21:
            return (0, 0, 0, 0, 0, 1.0)
        if total >= 18 or (total == 17 and not (soft and self.r.dealer_hits_soft_17)):
            return tuple(1.0 if i == total - 17 else 0.0 for i in range(6))
        out = [0.0] * 6
        for v, p in P.items():
            sub = self._dealer(*_add(total, soft, v))
            for i in range(6):
                out[i] += p * sub[i]
        return tuple(out)

    def dealer_final(self, up: int) -> tuple[float, ...]:
        """Dealer final distribution [17..21, bust], conditioned on no natural (peek)."""
        t0, s0 = _add(0, False, up)
        out = [0.0] * 6
        mass = 0.0
        for v, p in P.items():
            if {up, v} == {1, 10}:
                continue
            mass += p
            sub = self._dealer(*_add(t0, s0, v))
            for i in range(6):
                out[i] += p * sub[i]
        return tuple(x / mass for x in out)

    def stand(self, total: int, up: int, mult: float = 1.0) -> float:
        d = self.dealer_final(up)
        ev = d[5]
        for i in range(5):
            dt = 17 + i
            ev += d[i] * (1 if total > dt else -1 if total < dt else 0)
        return ev * mult

    def _hit_impl(self, total: int, soft: bool, up: int) -> float:
        ev = 0.0
        for v, p in P.items():
            t, s = _add(total, soft, v)
            if t > 21:
                ev -= p
            elif t == 21:
                ev += p * self.stand(21, up)
            else:
                ev += p * max(self.stand(t, up), self._hit(t, s, up))
        return ev

    def hit(self, total: int, soft: bool, up: int) -> float:
        return self._hit(total, soft, up)

    def double(self, total: int, soft: bool, up: int) -> float:
        ev = 0.0
        for v, p in P.items():
            t, _ = _add(total, soft, v)
            ev += p * (-2.0 if t > 21 else self.stand(t, up, 2.0))
        return ev

    def best_hs(self, total: int, soft: bool, up: int) -> float:
        if total == 21:
            return self.stand(21, up)
        return max(self.stand(total, up), self.hit(total, soft, up))

    def split(self, pv: int, up: int) -> float:
        """Split without resplitting, infinite deck (2 x one-hand EV)."""
        ev = 0.0
        for v, p in P.items():
            t, s = _add(*_add(0, False, pv), v)
            if pv == 1 and not self.r.hit_split_aces:
                val = self.stand(t, up)
            else:
                opts = [self.best_hs(t, s, up)]
                if self.r.double_after_split and self.r.can_double(t, s):
                    opts.append(self.double(t, s, up))
                val = max(opts)
            ev += p * val
        return 2 * ev

    # ---------------------------------------------------------------- strategy
    def decide(self, total: int, soft: bool, up: int, *, can_double: bool, can_split_pv: int | None,
               can_surrender: bool) -> str:
        opts = {"S": self.stand(total, up)}
        if total < 21:
            opts["H"] = self.hit(total, soft, up)
        if can_double and self.r.can_double(total, soft):
            opts["D"] = self.double(total, soft, up)
        if can_split_pv is not None:
            opts["P"] = self.split(can_split_pv, up)
        if can_surrender and self.r.surrender == "late":
            opts["R"] = -0.5
        return max(opts, key=opts.get)

    def strategy_table(self) -> dict:
        """Basic strategy keyed by ('hard'|'soft'|'pair', value, upcard 1..10).

        Values: two-card decisions with every option, plus 'hit_only' entries
        for multi-card hands. Codes: S stand, H hit, D double, P split, R surrender.
        """
        table: dict = {}
        for up in range(1, 11):
            for total in range(4, 22):
                table[("hard", total, up)] = self.decide(total, False, up, can_double=True, can_split_pv=None, can_surrender=True)
                table[("hard_mc", total, up)] = self.decide(total, False, up, can_double=False, can_split_pv=None, can_surrender=False)
            for total in range(12, 22):
                table[("soft", total, up)] = self.decide(total, True, up, can_double=True, can_split_pv=None, can_surrender=True)
                table[("soft_mc", total, up)] = self.decide(total, True, up, can_double=False, can_split_pv=None, can_surrender=False)
            for pv in range(1, 11):
                t, s = _add(*_add(0, False, pv), pv)
                table[("pair", pv, up)] = self.decide(t, s, up, can_double=True, can_split_pv=pv, can_surrender=True)
        return table
