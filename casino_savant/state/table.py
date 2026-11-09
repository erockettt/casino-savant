"""Blackjack table state manager + Replay Lab audit.

Input contract (shared by manual entry and any future vision recogniser):

    Observation(round_id, slot, index, rank, confidence, source, frame_id)

* `slot`  — 'dealer', 'player', 'player:1' (split hand), 'other:3' (other seats), 'burn'
* `index` — position of the card within that slot (0, 1, 2 ...)
A physical card is identified by (round_id, slot, index); re-observing it in a
later frame never double-counts. A conflicting rank for an already-recorded
card is rejected and flagged for user correction instead of overwriting silently.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field

from ..blackjack.counting import ShoeTracker
from ..blackjack.rules import BlackjackRules
from ..blackjack.solver import BlackjackSolver
from ..cards import label, parse_card
from ..grading import grade_play, suggest_bet


@dataclass
class Observation:
    round_id: int
    slot: str
    index: int
    rank: str
    confidence: float = 1.0
    source: str = "manual"
    frame_id: str | None = None


@dataclass
class TableSession:
    rules: BlackjackRules
    counting_system: str = "hilo"
    min_confidence: float = 0.98
    profile_banner: str = ""
    rules_verified: bool = False
    can_sit_out: bool = True
    bankroll_units: float = 200.0
    max_units: float = 8.0
    round_id: int = 1
    cards: dict = field(default_factory=dict)       # (round, slot, index) -> rank idx
    conflicts: list = field(default_factory=list)
    decisions: list = field(default_factory=list)   # replay-lab log

    def __post_init__(self):
        self.tracker = ShoeTracker(self.rules.decks, self.counting_system)
        self.solver = BlackjackSolver(self.rules)

    # -------------------------------------------------------------- input
    def observe(self, obs: Observation) -> dict:
        key = (obs.round_id, obs.slot, obs.index)
        if obs.slot == "burn" and obs.rank in ("?", ""):
            self.tracker.burn_unseen()
            return {"accepted": True, "reason": "unseen burn"}
        try:
            rank = parse_card(obs.rank)
        except ValueError as e:
            return {"accepted": False, "reason": str(e)}
        if key in self.cards:
            if self.cards[key] != rank:
                self.conflicts.append({"key": list(key), "recorded": label(self.cards[key]), "new": label(rank),
                                       "source": obs.source, "frame": obs.frame_id})
                return {"accepted": False, "reason": "conflicts with an already-recorded card; correction required"}
            return {"accepted": False, "reason": "duplicate observation of the same card (ignored)"}
        if obs.confidence < self.min_confidence:
            self.tracker.low_confidence.append({"key": list(key), "rank": label(rank), "confidence": obs.confidence})
            return {"accepted": False, "reason": f"confidence {obs.confidence:.2f} below {self.min_confidence}; confirm manually"}
        self.tracker.observe(rank, obs_id=str(key), source=obs.source, confidence=obs.confidence,
                             min_confidence=0.0)
        self.cards[key] = rank
        return {"accepted": True}

    def correct(self, round_id: int, slot: str, index: int, rank: str) -> dict:
        key = (round_id, slot, index)
        new = parse_card(rank)
        if key in self.cards:
            old = self.cards[key]
            self.tracker.seen[old] -= 1
            self.tracker.obs_ids.discard(str(key))
            del self.cards[key]
        self.conflicts = [c for c in self.conflicts if tuple(c["key"]) != key]
        self.tracker.low_confidence = [c for c in self.tracker.low_confidence if tuple(c.get("key", ())) != key]
        return self.observe(Observation(round_id, slot, index, label(new), 1.0, "user-correction"))

    def burn_unseen(self, n: int = 1):
        self.tracker.burn_unseen(n)

    def new_round(self) -> int:
        self.round_id += 1
        if not self.rules.counting_meaningful:
            # RNG / CSM: every round starts from a full shoe
            self.tracker.shuffle()
        return self.round_id

    def shuffle(self):
        self.tracker.shuffle()

    # -------------------------------------------------------------- views
    def hand(self, slot: str, round_id: int | None = None) -> list[int]:
        rid = self.round_id if round_id is None else round_id
        items = sorted((k[2], v) for k, v in self.cards.items() if k[0] == rid and k[1] == slot)
        return [v for _, v in items]

    def analyze(self, slot: str = "player", *, hands_after_split: int = 1) -> dict:
        player = self.hand(slot)
        dealer = self.hand("dealer")
        missing = []
        if len(player) < 2:
            missing.append("player needs at least two cards")
        if not dealer:
            missing.append("dealer upcard not recorded")
        if self.conflicts:
            missing.append("unresolved card conflicts")
        pending = [c for c in self.tracker.low_confidence if c.get("key") and c["key"][0] == self.round_id]
        if pending:
            missing.append("low-confidence cards in this round await confirmation")
        if missing:
            return {"ready": False, "missing": missing}
        up = dealer[0]
        comp = self.tracker.remaining
        if self.rules.counting_meaningful:
            src = (f"tracked composition ({sum(self.tracker.seen)} cards seen this shoe"
                   + (f", {self.tracker.unseen_removed} unseen burns" if self.tracker.unseen_removed else "") + ")")
        else:
            src = "fresh shoe every round (RNG/CSM game: past cards carry no information)"
        a = self.solver.analyze(player, up, comp, hands_after_split=hands_after_split,
                                is_split_hand=slot != "player", shoe_source=src)
        out = a.to_dict()
        out["ready"] = True
        out["count"] = self.tracker.snapshot() if self.rules.counting_meaningful else None
        out["profile"] = self.profile_banner
        out["grade"] = grade_play(out, rules_verified=self.rules_verified).to_dict()
        return out

    def bet_suggestion(self) -> dict:
        """Graded suggestion for the size of the NEXT bet (the system never bets itself)."""
        tc = self.tracker.true_count(rounding="none") if self.rules.counting_meaningful else None
        if self.rules.counting_meaningful and self.counting_system != "hilo":
            # sizing model is calibrated for Hi-Lo; derive the Hi-Lo TC from the exact composition
            tc = self.tracker.true_count("hilo", rounding="none")
        return suggest_bet(self.rules, true_count=tc, rules_verified=self.rules_verified,
                           bankroll_units=self.bankroll_units, max_units=self.max_units,
                           cards_seen=sum(self.tracker.seen), tc_sd=self.tracker.count_uncertainty(),
                           can_sit_out=self.can_sit_out)

    # -------------------------------------------------------------- replay lab
    def record_decision(self, slot: str, action_taken: str) -> dict:
        a = self.analyze(slot)
        if not a.get("ready"):
            return {"recorded": False, "missing": a.get("missing")}
        evs = {x["action"]: x["ev"] for x in a["legal"]}
        taken = action_taken.upper()
        if taken not in evs:
            return {"recorded": False, "reason": f"{taken} not legal here; legal: {list(evs)}"}
        best = a["best"]
        entry = {
            "grade": a["grade"]["letter"], "followed": taken == best,
            "t": time.time(), "round": self.round_id, "slot": slot,
            "player": a["player_cards"], "dealer_up": a["dealer_up"],
            "taken": taken, "best": best, "ev_taken": evs[taken], "ev_best": evs[best],
            "ev_loss": evs[best] - evs[taken], "margin": a["margin"], "rules": a["rules"],
            "shoe": a["shoe_source"],
        }
        self.decisions.append(entry)
        return {"recorded": True, **entry}

    def audit(self) -> dict:
        n = len(self.decisions)
        errs = [d for d in self.decisions if d["ev_loss"] > 1e-9]
        by_grade = {}
        for d in self.decisions:
            g = by_grade.setdefault(d["grade"], {"suggestions": 0, "followed": 0, "ev_lost_when_ignored": 0.0})
            g["suggestions"] += 1
            g["followed"] += d["followed"]
            g["ev_lost_when_ignored"] += d["ev_loss"]
        return {
            "decisions": n,
            "followed": sum(d["followed"] for d in self.decisions),
            "by_grade": dict(sorted(by_grade.items())),
            "mistakes": len(errs),
            "total_ev_lost_units": sum(d["ev_loss"] for d in errs),
            "worst": sorted(errs, key=lambda d: d["ev_loss"], reverse=True)[:10],
            "log": self.decisions,
            "interpretation": ("EV lost is measured in units of the initial bet against the exact solver for the "
                               "recorded cards and rules. Results (wins/losses) are NOT used: a correct decision "
                               "that lost is variance, not a mistake."),
        }
