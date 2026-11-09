"""FastAPI backend: stateless calculators + in-memory table sessions.

Run:  uvicorn casino_savant.api.app:app --reload   then open http://127.0.0.1:8000/
"""
from __future__ import annotations

import uuid
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from ..blackjack.counting import FAB_4, ILLUSTRIOUS_18, SYSTEMS, ShoeTracker
from ..blackjack.rules import BlackjackRules
from ..blackjack.solver import BlackjackSolver
from ..cards import full_shoe, parse_card, parse_cards, remove
from ..games import baccarat, roulette
from ..lab import progressions, risk
from ..profiles import ProfileStore, VenueProfile
from ..state.table import Observation, TableSession

app = FastAPI(title="Casino Savant", version="0.1.0")
WEB = Path(__file__).resolve().parents[2] / "web"
store = ProfileStore()
SESSIONS: dict[str, TableSession] = {}
SOLVERS: dict = {}


def solver_for(rules: BlackjackRules) -> BlackjackSolver:
    key = tuple(sorted((k, str(v)) for k, v in rules.to_dict().items()))
    if key not in SOLVERS:
        if len(SOLVERS) > 16:
            SOLVERS.clear()
        SOLVERS[key] = BlackjackSolver(rules)
    return SOLVERS[key]


def _rules(profile_id: str | None, rules: dict | None) -> tuple[BlackjackRules, str]:
    if profile_id:
        p = store.get(profile_id)
        if p.game != "blackjack":
            raise HTTPException(400, "profile is not a blackjack profile")
        base = p.rules | (rules or {})
        return BlackjackRules.from_dict(base), p.status_banner() + (" (with overrides)" if rules else "")
    return BlackjackRules.from_dict(rules or {}), "custom rules (user-supplied)"


class BJRequest(BaseModel):
    player: str = Field(..., examples=["T 6"])
    dealer_up: str = Field(..., examples=["T"])
    profile_id: str | None = None
    rules: dict | None = None
    seen_cards: str | None = Field(None, description="Other cards already seen this shoe (space separated)")
    is_split_hand: bool = False
    hands_after_split: int = 1


@app.get("/")
def index():
    return FileResponse(WEB / "index.html")


@app.get("/api/health")
def health():
    return {"ok": True}


@app.get("/api/profiles")
def list_profiles():
    return [p.to_dict() | {"banner": p.status_banner()} for p in store.all().values()]


@app.put("/api/profiles/{pid}")
def save_profile(pid: str, body: dict):
    try:
        p = VenueProfile(**(body | {"id": pid}))
        store.save(p)
    except (TypeError, ValueError) as e:
        raise HTTPException(400, str(e))
    return p.to_dict()


@app.post("/api/blackjack/analyze")
def bj_analyze(req: BJRequest):
    rules, banner = _rules(req.profile_id, req.rules)
    try:
        player = parse_cards(req.player)
        up = parse_card(req.dealer_up)
        shoe = None
        src = None
        if req.seen_cards:
            if not rules.counting_meaningful:
                src = "seen cards ignored: this game reshuffles every round"
                shoe = remove(full_shoe(rules.decks), player + [up])
            else:
                seen = parse_cards(req.seen_cards)
                shoe = remove(full_shoe(rules.decks), player + [up] + seen)
                src = f"fresh shoe minus visible cards and {len(seen)} other seen cards"
    except ValueError as e:
        raise HTTPException(422, str(e))
    if len(player) < 2:
        raise HTTPException(422, "need at least two player cards")
    a = solver_for(rules).analyze(player, up, shoe, is_split_hand=req.is_split_hand,
                                  hands_after_split=req.hands_after_split, shoe_source=src)
    return a.to_dict() | {"profile": banner}


class BaccaratRequest(BaseModel):
    profile_id: str | None = None
    rules: dict | None = None
    seen_cards: str | None = None


@app.post("/api/baccarat/analyze")
def bac_analyze(req: BaccaratRequest):
    base = store.get(req.profile_id).rules if req.profile_id else {}
    r = baccarat.BaccaratRules(**{k: v for k, v in (base | (req.rules or {})).items() if k != "notes"})
    comp = full_shoe(r.decks)
    if req.seen_cards:
        try:
            comp = remove(comp, parse_cards(req.seen_cards))
        except ValueError as e:
            raise HTTPException(422, str(e))
    out = baccarat.analyze(r, comp)
    out["profile"] = store.get(req.profile_id).status_banner() if req.profile_id else "custom rules"
    return out


class RouletteRequest(BaseModel):
    profile_id: str | None = None
    wheel: Literal["european", "american", "triple_zero"] | None = None
    la_partage: bool | None = None
    en_prison: bool | None = None


@app.post("/api/roulette/analyze")
def rl_analyze(req: RouletteRequest):
    base = dict(store.get(req.profile_id).rules) if req.profile_id else {}
    for k in ("wheel", "la_partage", "en_prison"):
        if getattr(req, k) is not None:
            base[k] = getattr(req, k)
    out = roulette.analyze(roulette.RouletteRules(**base))
    out["profile"] = store.get(req.profile_id).status_banner() if req.profile_id else "custom rules"
    return out


# ------------------------------------------------------------------ table sessions
class SessionCreate(BaseModel):
    profile_id: str | None = "reference-6d-s17"
    rules: dict | None = None
    counting_system: str = "hilo"


@app.post("/api/session")
def create_session(req: SessionCreate):
    if req.counting_system not in SYSTEMS:
        raise HTTPException(422, f"unknown system; choose {sorted(SYSTEMS)}")
    rules, banner = _rules(req.profile_id, req.rules)
    sid = uuid.uuid4().hex[:12]
    SESSIONS[sid] = TableSession(rules, req.counting_system, profile_banner=banner)
    return {"session_id": sid, "rules": rules.describe(), "profile": banner,
            "counting_meaningful": rules.counting_meaningful}


def _sess(sid: str) -> TableSession:
    if sid not in SESSIONS:
        raise HTTPException(404, "unknown session")
    return SESSIONS[sid]


class ObsIn(BaseModel):
    slot: str
    index: int
    rank: str
    confidence: float = 1.0
    source: str = "manual"
    frame_id: str | None = None
    round_id: int | None = None


@app.post("/api/session/{sid}/observe")
def observe(sid: str, obs: ObsIn):
    s = _sess(sid)
    res = s.observe(Observation(obs.round_id or s.round_id, obs.slot, obs.index, obs.rank, obs.confidence,
                                obs.source, obs.frame_id))
    return res | {"state": state(sid)}


@app.post("/api/session/{sid}/correct")
def correct(sid: str, obs: ObsIn):
    s = _sess(sid)
    return s.correct(obs.round_id or s.round_id, obs.slot, obs.index, obs.rank) | {"state": state(sid)}


@app.post("/api/session/{sid}/burn")
def burn(sid: str, n: int = 1):
    _sess(sid).burn_unseen(n)
    return state(sid)


@app.post("/api/session/{sid}/new_round")
def new_round(sid: str):
    _sess(sid).new_round()
    return state(sid)


@app.post("/api/session/{sid}/shuffle")
def shuffle(sid: str):
    _sess(sid).shuffle()
    return state(sid)


@app.get("/api/session/{sid}")
def state(sid: str):
    s = _sess(sid)
    return {
        "round_id": s.round_id,
        "dealer": [c for c in map(lambda r: "A23456789T"[r], s.hand("dealer"))],
        "player": [c for c in map(lambda r: "A23456789T"[r], s.hand("player"))],
        "count": s.tracker.snapshot() if s.rules.counting_meaningful else
                 {"note": "Counting disabled: this game reshuffles every round (RNG/CSM)."},
        "conflicts": s.conflicts,
        "rules": s.rules.describe(),
        "profile": s.profile_banner,
    }


@app.get("/api/session/{sid}/analyze")
def session_analyze(sid: str, slot: str = "player"):
    return _sess(sid).analyze(slot)


class DecisionIn(BaseModel):
    slot: str = "player"
    action: str


@app.post("/api/session/{sid}/decision")
def decision(sid: str, d: DecisionIn):
    return _sess(sid).record_decision(d.slot, d.action)


@app.get("/api/session/{sid}/audit")
def audit(sid: str):
    return _sess(sid).audit()


# ------------------------------------------------------------------ research
@app.get("/api/research/indices")
def indices():
    return {"status": "EMPIRICALLY SUPPORTED (literature); not re-derived here",
            "illustrious_18": ILLUSTRIOUS_18, "fab_4": FAB_4}


class ProgressionRequest(BaseModel):
    bet: Literal["european_red", "american_red", "baccarat_banker", "baccarat_player"] = "european_red"
    progression: str = "martingale"
    sessions: int = Field(5000, le=50000)
    rounds: int = Field(100, le=1000)
    bankroll: float = 200
    table_max: float = 500
    seed: int = 1


@app.post("/api/lab/progression")
def lab_progression(req: ProgressionRequest):
    spec = {"european_red": progressions.EUROPEAN_RED, "american_red": progressions.AMERICAN_RED,
            "baccarat_banker": progressions.BACCARAT_BANKER, "baccarat_player": progressions.BACCARAT_PLAYER}[req.bet]
    if req.progression not in progressions.PROGRESSIONS:
        raise HTTPException(422, f"choose from {sorted(progressions.PROGRESSIONS)}")
    return progressions.simulate_sessions(spec, req.progression, sessions=req.sessions, rounds=req.rounds,
                                          bankroll=req.bankroll, table_max=req.table_max, seed=req.seed)


class StakeRequest(BaseModel):
    edge: float
    edge_se: float
    variance: float = 1.3
    bankroll: float
    kelly_multiplier: float = 0.5


@app.post("/api/risk/stake")
def stake(req: StakeRequest):
    out = risk.stake_advice(req.edge, req.edge_se, req.variance, req.bankroll, req.kelly_multiplier)
    mu = max(out.get("conservative_edge", req.edge), -1)
    bet = out.get("recommended_bet", 0)
    if bet > 0:
        out["risk_of_ruin"] = risk.risk_of_ruin(mu * bet, (req.variance ** 0.5) * bet, req.bankroll)
    return out
