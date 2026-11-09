import pytest
from fastapi.testclient import TestClient

from casino_savant.api.app import app
from casino_savant.blackjack.rules import BlackjackRules
from casino_savant.grading import base_edge_pct, grade_play, suggest_bet
from casino_savant.lab.blackjack_sim import BlackjackSim, SimConfig
from casino_savant.state.table import Observation, TableSession


def _session(cards, **kw):
    s = TableSession(BlackjackRules(**kw.pop("rules", {})), **kw)
    for slot, i, r in cards:
        s.observe(Observation(1, slot, i, r))
    return s


def test_clear_decision_with_verified_rules_is_A():
    s = _session([("player", 0, "T"), ("dealer", 0, "6"), ("player", 1, "9")], rules_verified=True)  # 19 v 6
    assert s.analyze()["grade"]["letter"] == "A"


def test_close_call_and_unverified_rules_downgrade():
    s = _session([("player", 0, "T"), ("dealer", 0, "T"), ("player", 1, "6")],
                 rules={"surrender": "none"}, rules_verified=False)  # 16 v T: hit vs stand nearly equal
    g = s.analyze()["grade"]
    assert g["letter"] in ("C", "D")
    assert any("not verified" in r for r in g["reasons"])
    assert any("close" in r or "coin flip" in r for r in g["reasons"])


def test_missing_input_gives_no_grade():
    s = _session([("player", 0, "T")])
    a = s.analyze()
    assert a["ready"] is False
    assert grade_play(a, rules_verified=True).letter == "—"


def test_base_edge_matches_benchmark_and_known_rule_costs():
    assert base_edge_pct(BlackjackRules()) == pytest.approx(-0.40)
    six_five = base_edge_pct(BlackjackRules(blackjack_payout=1.2)) - base_edge_pct(BlackjackRules())
    assert six_five == pytest.approx(-1.425, abs=0.01)


def test_bet_suggestion_rng_game_is_no_bet():
    out = suggest_bet(BlackjackRules(shuffle="per_hand"), true_count=None, rules_verified=False)
    assert out["units"] == 0 and out["suggestion"].startswith("NO BET")


def test_bet_suggestion_scales_with_count_and_never_bets_negative():
    r = BlackjackRules(decks=8)
    low = suggest_bet(r, true_count=-1, rules_verified=True, cards_seen=200)
    high = suggest_bet(r, true_count=5, rules_verified=True, cards_seen=200)
    assert low["units"] == 0 and "SIT OUT" in low["suggestion"]
    assert high["units"] >= 1 and high["edge_pct"] > 1.5
    no_sit = suggest_bet(r, true_count=-1, rules_verified=True, cards_seen=200, can_sit_out=False)
    assert no_sit["units"] == 1


def test_audit_groups_by_grade():
    s = _session([("player", 0, "T"), ("dealer", 0, "6"), ("player", 1, "9")], rules_verified=True)
    s.record_decision("player", "HIT")
    au = s.audit()
    assert au["by_grade"]["A"]["suggestions"] == 1 and au["followed"] == 0


def test_sim_enhc_costs_more_than_peek_and_sitout_counts_rounds():
    common = dict(decks=8, surrender="none", max_split_hands=2)
    peek = BlackjackSim(BlackjackRules(**common), SimConfig(rounds=400_000, seed=21)).run()
    enhc = BlackjackSim(BlackjackRules(dealer_peeks=False, **common), SimConfig(rounds=400_000, seed=21)).run()
    assert enhc.ev_per_round < peek.ev_per_round  # common random numbers: same shuffles
    w = BlackjackSim(BlackjackRules(penetration=0.5), SimConfig(rounds=20_000, seed=3, bet_ramp={-99: 0, 1: 1})).run()
    assert w.config["rounds_sat_out"] + w.config["rounds_played"] == 20_000
    assert w.config["rounds_sat_out"] > w.config["rounds_played"]


def test_api_grades_and_bet_endpoint():
    c = TestClient(app)
    r = c.post("/api/blackjack/analyze", json={"player": "T 9", "dealer_up": "6", "profile_id": "bovada-bj-live"}).json()
    assert r["grade"]["letter"] in "ABCD" and any("not verified" in x for x in r["grade"]["reasons"])
    assert c.post("/api/roulette/analyze", json={"profile_id": "bovada-roulette-american"}).json()["grade"]["letter"] == "A"
    sid = c.post("/api/session", json={"profile_id": "bovada-bj-live"}).json()["session_id"]
    b = c.get(f"/api/session/{sid}/bet").json()
    assert "grade" in b and b["units"] == 0  # fresh shoe, TC 0, negative edge -> sit out
