"""Graded suggestions.

The system never places bets. It SUGGESTS (a playing action, a bet size, or
NO BET) and GRADES each suggestion so the user knows how much to trust it.

Grade = how confident the suggestion deserves to be, NOT whether it will win:

  A  clear-cut and well-founded: large EV margin, verified rules, reliable inputs
  B  sound: moderate margin or a minor input caveat
  C  close call: options nearly equal, or an important assumption unverified
  D  weak foundation: approximation, guessed composition and unverified rules together
  —  no suggestion: required input missing or conflicting (the system refuses to guess)

Every grade lists the reasons that lowered it, so a grade is reproducible.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .blackjack.rules import BlackjackRules

ORDER = ["A", "B", "C", "D"]


@dataclass
class Grade:
    letter: str
    score: int                # 0-100, for sorting/calibration
    summary: str
    reasons: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return self.__dict__.copy()


def _letter(score: int) -> str:
    return "A" if score >= 85 else "B" if score >= 70 else "C" if score >= 50 else "D"


def grade_play(analysis: dict, *, rules_verified: bool) -> Grade:
    """Grade a blackjack playing suggestion (output of BlackjackSolver.analyze().to_dict())."""
    if not analysis.get("ready", True):
        return Grade("—", 0, "No suggestion: " + "; ".join(analysis.get("missing", [])))
    legal = analysis["legal"]
    if len(legal) == 1:
        return Grade("A", 100, f"{legal[0]['action']} — no decision to make.")
    score = 100
    reasons = []
    m = analysis["margin"]
    if m < 0.002:
        score -= 45
        reasons.append(f"coin flip: best beats next by only {m:.4f} units")
    elif m < 0.01:
        score -= 25
        reasons.append(f"close call: margin {m:.4f} units")
    elif m < 0.05:
        score -= 8
        reasons.append(f"moderate margin {m:.3f} units")
    if not legal[0].get("exact", True) or not legal[1].get("exact", True):
        score -= 12 if m >= 0.01 else 25
        reasons.append("top choices include the split approximation")
    if not rules_verified:
        score -= 15
        reasons.append("table rules not verified")
    src = analysis.get("shoe_source", "")
    if "assumed fresh shoe" in src:
        score -= 5
        reasons.append("no shoe tracking (fresh shoe assumed)")
    count = analysis.get("count") or {}
    if count.get("true_count_sd_from_burns", 0) > 0.5:
        score -= 8
        reasons.append("unseen burn cards blur the composition")
    score = max(score, 0)
    letter = _letter(score)
    best = legal[0]
    summary = f"{best['action']} (EV {best['ev']:+.4f}); " + ("solid." if letter in "AB" else "treat as a lean, not a certainty.")
    return Grade(letter, score, summary, reasons)


# --------------------------------------------------------------------- bet sizing
# Approximate off-the-top house-edge effects (% of initial bet) relative to a
# 6D S17 DAS late-surrender peek 3:2 game measured at -0.40% in docs/BENCHMARKS.md.
# Values are commonly published rule-effect approximations (e.g. Wizard of Odds
# rule-variation tables); status EMPIRICALLY SUPPORTED, accuracy roughly +/-0.05%.
DECK_EFFECT = {1: 0.48, 2: 0.19, 4: 0.06, 5: 0.03, 6: 0.0, 8: -0.02}
HILO_SLOPE = 0.5  # % edge gained per Hi-Lo true count (benchmarked in docs/BENCHMARKS.md)


def base_edge_pct(r: BlackjackRules) -> float:
    e = -0.40 + DECK_EFFECT.get(r.decks, -0.03 if r.decks > 8 else 0.0)
    if r.dealer_hits_soft_17:
        e -= 0.22
    if not r.double_after_split:
        e += -0.14
    if r.surrender == "none":
        e -= 0.08
    if r.max_split_hands <= 2:
        e -= 0.04
    if r.resplit_aces:
        e += 0.08
    if r.double_on == "10-11":
        e -= 0.20
    elif r.double_on == "9-11":
        e -= 0.10
    if not r.dealer_peeks and r.enhc_lose_doubles_and_splits:
        e -= 0.11
    e += (r.blackjack_payout - 1.5) * 4.75  # P(player natural) ~ 4.75%; 6:5 -> -1.43%
    return e


def suggest_bet(rules: BlackjackRules, *, true_count: float | None, rules_verified: bool,
                bankroll_units: float = 200.0, max_units: float = 8.0, kelly_multiplier: float = 0.5,
                cards_seen: int = 0, tc_sd: float = 0.0, can_sit_out: bool = True) -> dict:
    """Suggest a bet size for the NEXT round, in table-minimum units, with a grade."""
    reasons: list[str] = []
    base = base_edge_pct(rules)
    if not rules.counting_meaningful:
        g = Grade("A", 95, "No edge exists on a game reshuffled every round; the count is always neutral.",
                  [] if rules_verified else ["table rules not verified (affects the size of the loss, not the conclusion)"])
        if not rules_verified:
            g.score, g.letter = 85, "A"
        return {"suggestion": "NO BET (or table minimum if playing for entertainment)",
                "units": 0, "edge_pct": base, "edge_basis": "off-the-top edge; counting has no effect",
                "expected_loss_per_unit": -base / 100, "grade": g.to_dict()}
    if true_count is None:
        return {"suggestion": "No suggestion", "units": None,
                "grade": Grade("—", 0, "Use a balanced count (true count unavailable).").to_dict()}
    edge = base + HILO_SLOPE * true_count
    score = 100
    if cards_seen < 52:
        score -= 10
        reasons.append("early in the shoe: count based on few cards")
    if tc_sd > 0.5:
        score -= 10
        reasons.append(f"true count uncertain by ±{tc_sd:.1f} from unseen burns")
    if not rules_verified:
        score -= 15
        reasons.append("table rules not verified")
    if abs(edge) < 0.25:
        score -= 30
        reasons.append("estimated edge is within ±0.25% of zero (estimate error is about that size)")
    reasons.append("edge estimated from rule-effect table + 0.5%/TC slope, not solved exactly")
    score -= 5
    if edge <= 0:
        sug = "SIT OUT (watch only)" if can_sit_out else "TABLE MINIMUM"
        units = 0 if can_sit_out else 1
        summary = f"Estimated edge {edge:+.2f}% — no advantage; {sug.lower()}."
    else:
        f = kelly_multiplier * (edge / 100) / 1.3
        units = max(1, min(max_units, round(f * bankroll_units)))
        sug = f"BET {units:g} UNIT{'S' if units != 1 else ''}"
        summary = f"Estimated edge {edge:+.2f}% at TC {true_count:+.1f}; {kelly_multiplier:g}x Kelly sizing on {bankroll_units:g} units, capped at {max_units:g}."
    g = Grade(_letter(max(score, 0)), max(score, 0), summary, reasons)
    return {"suggestion": sug, "units": units, "edge_pct": edge,
            "edge_basis": f"off-the-top {base:+.2f}% + {HILO_SLOPE}% x TC {true_count:+.1f}",
            "grade": g.to_dict()}


def grade_no_bet(game: str, best_ev: float, *, rules_verified: bool) -> dict:
    """Baccarat/roulette: NO BET is a proven suggestion whenever every wager is negative."""
    if best_ev < 0:
        g = Grade("A", 95 if rules_verified else 88,
                  f"NO BET: every {game} wager loses on average (best {best_ev:+.3%}). Proven mathematically.",
                  [] if rules_verified else ["rules not verified (changes the loss size, not the sign)"])
    else:
        g = Grade("B", 75, f"Positive-EV wager available ({best_ev:+.3%}) for this exact composition.",
                  ["depends on every dealt card being recorded correctly"])
    return g.to_dict()
