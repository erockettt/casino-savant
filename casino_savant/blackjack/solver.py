"""Composition-dependent blackjack expected-value solver.

Method (see docs/MATH_SPEC.md §BJ for the derivation):

* All probabilities are computed from the exact remaining-card composition with
  card removal at every draw — for the player's hits and for every dealer card.
* Peek games: the dealer has already checked for blackjack, so EVs are
  conditional on "hole card does not complete a natural".  Because the dealer's
  hole card and the player's subsequent draws are exchangeable, we can draw the
  player's cards first, then weight each path by P(hole card is not the
  blackjack-completing rank | remaining cards).  Summing those unnormalised
  values and dividing once by P(no dealer BJ | shoe at decision) gives the
  exact conditional EV.  Argmax decisions inside the recursion are unaffected
  by the common denominator.
* ENHC (no hole card): the dealer's natural is a possible outcome after the
  player acts; doubled/split bets are lost (or only the original bet with OBO).
* Stand / hit / double / surrender: exact under the stated rules.
* Split: card removal is exact for the first two cards of each split hand
  and for that hand's own draws; interaction between sibling split hands
  (cards one hand removes from the other) is ignored, and resplitting is
  handled by a branching model with a fixed pair-card probability.  This is a
  labelled APPROXIMATION (typical error < 0.002 units at 6 decks; see tests).

Outcome vector index: 0..4 -> dealer final 17..21, 5 -> bust, 6 -> dealer natural.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Sequence

from ..cards import Comp, HandTotal, add_card, bj_value, full_shoe, label, remove
from .rules import BlackjackRules

ACE, TEN = 0, 9
NOUT = 7


@dataclass
class ActionEV:
    action: str
    ev: float
    exact: bool = True
    note: str = ""


@dataclass
class Analysis:
    player_cards: list[str]
    dealer_up: str
    player_total: int
    soft: bool
    rules: str
    legal: list[ActionEV]
    best: str
    margin: float                    # best minus second-best EV (units of initial bet)
    insurance_ev: float | None       # EV per unit of insurance bet, if offered
    p_dealer_blackjack: float        # given visible cards, before any peek
    dealer_outcomes: dict[str, float]  # conditional dealer final distribution if player stands now
    shoe_cards_remaining: int
    shoe_source: str
    assumptions: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    explanation: str = ""

    def to_dict(self) -> dict:
        d = self.__dict__.copy()
        d["legal"] = [a.__dict__ for a in self.legal]
        return d


class BlackjackSolver:
    """Exact-composition solver. One instance caches results for one rule set."""

    def __init__(self, rules: BlackjackRules):
        self.r = rules
        self._dealer_cache: dict = {}
        self._hit_cache: dict = {}
        self._stand_cache: dict = {}

    # ------------------------------------------------------------------ dealer
    def _dealer_after_hole(self, total: int, soft: bool, shoe: Comp) -> tuple[float, ...]:
        """Final-total distribution once the dealer holds >= 2 cards (no natural possible)."""
        key = (total, soft, shoe)
        hit = self._dealer_cache.get(key)
        if hit is not None:
            return hit
        if total > 21:
            res = (0.0, 0.0, 0.0, 0.0, 0.0, 1.0, 0.0)
        elif total >= 18 or (total == 17 and not (soft and self.r.dealer_hits_soft_17)):
            res = tuple(1.0 if i == total - 17 else 0.0 for i in range(NOUT))
        else:
            n = sum(shoe)
            if n == 0:
                raise ValueError("shoe exhausted while dealer drawing")
            acc = [0.0] * NOUT
            for rank, cnt in enumerate(shoe):
                if cnt == 0:
                    continue
                p = cnt / n
                t2, s2 = add_card(total, soft, rank)
                sub = self._dealer_after_hole(t2, s2, remove(shoe, (rank,)))
                for i in range(NOUT):
                    acc[i] += p * sub[i]
            res = tuple(acc)
        self._dealer_cache[key] = res
        return res

    def excluded_hole_rank(self, up: int) -> int | None:
        if not self.r.dealer_peeks:
            return None
        if up == ACE:
            return TEN
        if up == TEN:
            return ACE
        return None

    def p_no_bj(self, shoe: Comp, up: int) -> float:
        """Weight of the conditioning event (peek) — 1.0 when nothing is conditioned."""
        ex = self.excluded_hole_rank(up)
        if ex is None:
            return 1.0
        return 1.0 - shoe[ex] / sum(shoe)

    def dealer_dist(self, shoe: Comp, up: int) -> tuple[float, ...]:
        """Unnormalised (peek) or full (ENHC / no-peek-needed) dealer distribution."""
        key = ("up", up, shoe)
        hit = self._dealer_cache.get(key)
        if hit is not None:
            return hit
        ex = self.excluded_hole_rank(up)
        n = sum(shoe)
        acc = [0.0] * NOUT
        t0, s0 = add_card(0, False, up)
        for rank, cnt in enumerate(shoe):
            if cnt == 0 or rank == ex:
                continue
            p = cnt / n
            if {up, rank} == {ACE, TEN}:
                acc[6] += p  # natural (only reachable when not peeking)
                continue
            t, s = add_card(t0, s0, rank)
            sub = self._dealer_after_hole(t, s, remove(shoe, (rank,)))
            for i in range(NOUT):
                acc[i] += p * sub[i]
        res = tuple(acc)
        self._dealer_cache[key] = res
        return res

    # ------------------------------------------------------------------ player
    def _stand(self, total: int, shoe: Comp, up: int, mult: float = 1.0) -> float:
        key = (total, shoe, up, mult)
        hit = self._stand_cache.get(key)
        if hit is not None:
            return hit
        d = self.dealer_dist(shoe, up)
        ev = d[5] * mult  # dealer bust
        for i in range(5):
            dt = 17 + i
            if total > dt:
                ev += d[i] * mult
            elif total < dt:
                ev -= d[i] * mult
        if d[6]:
            lose = 1.0 if (mult == 1.0 or not self.r.enhc_lose_doubles_and_splits) else mult
            ev -= d[6] * lose
        self._stand_cache[key] = ev
        return ev

    def _bust_weight(self, shoe: Comp, up: int) -> float:
        return self.p_no_bj(shoe, up)

    def _hit(self, total: int, soft: bool, shoe: Comp, up: int) -> float:
        """Unnormalised EV of hitting now and continuing optimally (hit/stand only)."""
        key = (total, soft, shoe, up)
        hit = self._hit_cache.get(key)
        if hit is not None:
            return hit
        n = sum(shoe)
        ev = 0.0
        for rank, cnt in enumerate(shoe):
            if cnt == 0:
                continue
            p = cnt / n
            t2, s2 = add_card(total, soft, rank)
            s_after = remove(shoe, (rank,))
            if t2 > 21:
                ev -= p * self._bust_weight(s_after, up)
            elif t2 == 21:
                ev += p * self._stand(21, s_after, up)
            else:
                ev += p * max(self._stand(t2, s_after, up), self._hit(t2, s2, s_after, up))
        self._hit_cache[key] = ev
        return ev

    def _best_hs(self, total: int, soft: bool, shoe: Comp, up: int) -> float:
        if total >= 21:
            return self._stand(total, shoe, up) if total == 21 else -self._bust_weight(shoe, up)
        return max(self._stand(total, shoe, up), self._hit(total, soft, shoe, up))

    def _double(self, total: int, soft: bool, shoe: Comp, up: int) -> float:
        n = sum(shoe)
        ev = 0.0
        for rank, cnt in enumerate(shoe):
            if cnt == 0:
                continue
            p = cnt / n
            t2, _ = add_card(total, soft, rank)
            s_after = remove(shoe, (rank,))
            if t2 > 21:
                ev -= 2.0 * p * self._bust_weight(s_after, up)
            else:
                ev += p * self._stand(t2, s_after, up, mult=2.0)
        return ev

    # ------------------------------------------------------------------ split
    def _split_hand_values(self, pair: int, shoe: Comp, up: int) -> tuple[float, float, float]:
        """Return (p_pair_card, E_not_pair, E_pair_unsplittable) for one split hand (unnormalised)."""
        n = sum(shoe)
        p_pair = shoe[pair] / n
        e_np = 0.0
        e_pair = 0.0
        aces = pair == ACE
        for rank, cnt in enumerate(shoe):
            if cnt == 0:
                continue
            p = cnt / n
            t, s = add_card(0, False, pair)
            t, s = add_card(t, s, rank)
            s_after = remove(shoe, (rank,))
            if aces and not self.r.hit_split_aces:
                v = self._stand(t, s_after, up)
            else:
                opts = [self._best_hs(t, s, s_after, up)]
                if self.r.double_after_split and self.r.can_double(t, s):
                    opts.append(self._double(t, s, s_after, up))
                v = max(opts)
            if rank == pair:
                e_pair = v
            else:
                e_np += p * v
        e_np_cond = e_np / (1 - p_pair) if p_pair < 1 else 0.0
        return p_pair, e_np_cond, e_pair

    def _split(self, pair: int, shoe: Comp, up: int) -> float:
        p, e_np, e_pair = self._split_hand_values(pair, shoe, up)
        max_hands = self.r.max_split_hands
        if pair == ACE and not self.r.resplit_aces:
            max_hands = 2
        memo: dict = {}

        def f(pending: int, hands: int) -> float:
            # expected total value of `pending` unresolved hands when `hands` hands exist
            if pending == 0:
                return 0.0
            k = (pending, hands)
            if k in memo:
                return memo[k]
            # resolve one pending hand
            v = (1 - p) * (e_np + f(pending - 1, hands))
            if hands < max_hands:
                v += p * f(pending + 1, hands + 1)
            else:
                v += p * (e_pair + f(pending - 1, hands))
            memo[k] = v
            return v

        return f(2, 2)

    # ------------------------------------------------------------------ public
    def analyze(
        self,
        player: Sequence[int],
        up: int,
        shoe: Comp | None = None,
        *,
        hands_after_split: int = 1,
        is_split_hand: bool = False,
        shoe_source: str | None = None,
    ) -> Analysis:
        """Analyse a decision.

        `shoe` is the composition of UNSEEN cards (the dealer hole card is still
        unseen and must be included). If omitted, a full shoe minus the visible
        player cards and dealer upcard is assumed — an explicit assumption that is
        reported back.
        """
        r = self.r
        warnings: list[str] = []
        assumptions = [r.describe()]
        if shoe is None:
            shoe = remove(full_shoe(r.decks), list(player) + [up])
            shoe_source = shoe_source or "assumed fresh shoe minus visible cards (no tracking data)"
        else:
            shoe_source = shoe_source or "supplied composition"
        if sum(shoe) < 20:
            warnings.append("Very few cards remain; results assume the dealer will not run out of cards.")
        ht = HandTotal.of(player)
        n_cards = len(player)
        n = sum(shoe)
        p_dbj = 0.0
        if up == ACE:
            p_dbj = shoe[TEN] / n
        elif up == TEN:
            p_dbj = shoe[ACE] / n

        insurance = None
        if r.insurance_offered and up == ACE and n_cards == 2 and not is_split_hand:
            pt = shoe[TEN] / n
            insurance = 2 * pt - (1 - pt)

        norm = self.p_no_bj(shoe, up)
        player_bj = n_cards == 2 and not is_split_hand and ht.total == 21
        legal: list[ActionEV] = []
        if player_bj:
            if r.dealer_peeks or p_dbj == 0:
                win = r.blackjack_payout * (1 - p_dbj)
            else:
                win = r.blackjack_payout * (1 - p_dbj)
            legal.append(ActionEV("STAND (blackjack)", win, note="pushes against a dealer natural"))
            if up == ACE and r.insurance_offered:
                legal.append(ActionEV("EVEN MONEY", 1.0, note="equivalent to blackjack + full insurance"))
        elif ht.total > 21:
            legal.append(ActionEV("BUST", -1.0))
        else:
            legal.append(ActionEV("STAND", self._stand(ht.total, shoe, up) / norm))
            if ht.total < 21:
                legal.append(ActionEV("HIT", self._hit(ht.total, ht.soft, shoe, up) / norm))
            may_double = n_cards == 2 and r.can_double(ht.total, ht.soft) and (not is_split_hand or r.double_after_split)
            if may_double:
                legal.append(ActionEV("DOUBLE", self._double(ht.total, ht.soft, shoe, up) / norm))
            if n_cards == 2 and player[0] == player[1] and hands_after_split < r.max_split_hands:
                if not (is_split_hand and player[0] == ACE and not r.resplit_aces):
                    legal.append(
                        ActionEV("SPLIT", self._split(player[0], shoe, up) / norm, exact=False,
                                 note="approximation: sibling-hand card removal ignored")
                    )
            if r.surrender == "late" and n_cards == 2 and not is_split_hand:
                if r.dealer_peeks:
                    sur = -0.5
                else:
                    sur = -0.5 * (1 - p_dbj) - p_dbj
                legal.append(ActionEV("SURRENDER", sur))

        legal.sort(key=lambda a: a.ev, reverse=True)
        best = legal[0].action
        margin = legal[0].ev - legal[1].ev if len(legal) > 1 else float("inf")
        if margin < 0.005 and len(legal) > 1:
            warnings.append(
                f"Close decision: {legal[0].action} beats {legal[1].action} by only {margin:.4f} units; "
                "small composition or rule errors can flip it."
            )
        if any(not a.exact for a in legal[:2]):
            warnings.append("A top-ranked action uses the split approximation; treat a narrow margin with caution.")

        d = self.dealer_dist(shoe, up)
        tot = sum(d)
        names = ["17", "18", "19", "20", "21", "bust", "blackjack"]
        outcomes = {names[i]: d[i] / tot for i in range(NOUT)}

        a = Analysis(
            player_cards=[label(c) for c in player],
            dealer_up=label(up),
            player_total=ht.total,
            soft=ht.soft,
            rules=r.describe(),
            legal=legal,
            best=best,
            margin=margin,
            insurance_ev=insurance,
            p_dealer_blackjack=p_dbj,
            dealer_outcomes=outcomes,
            shoe_cards_remaining=n,
            shoe_source=shoe_source,
            assumptions=assumptions,
            warnings=warnings,
        )
        a.explanation = explain(a, r)
        return a


def explain(a: Analysis, r: BlackjackRules) -> str:
    if len(a.legal) == 1:
        return f"{a.legal[0].action}: no decision required."
    kind = "soft" if a.soft else "hard"
    best, second = a.legal[0], a.legal[1]
    lines = [
        f"{kind.capitalize()} {a.player_total} vs dealer {a.dealer_up}: {best.action} "
        f"(EV {best.ev:+.4f}) beats {second.action} (EV {second.ev:+.4f}) by {a.margin:.4f} units per unit bet.",
        f"If you stand now the dealer busts {a.dealer_outcomes['bust']:.1%} of the time"
        + (" (already conditioned on the dealer not having blackjack)." if r.dealer_peeks and a.dealer_up in ("A", "T") else "."),
    ]
    if best.ev < 0:
        lines.append("Every option loses on average; the recommendation minimises the expected loss.")
    if a.insurance_ev is not None:
        verdict = "favourable" if a.insurance_ev > 0 else "unfavourable"
        lines.append(f"Insurance EV {a.insurance_ev:+.4f} per unit insured: {verdict} for this composition.")
    lines.append(f"Cards: {a.shoe_source}; {a.shoe_cards_remaining} unseen.")
    return " ".join(lines)
