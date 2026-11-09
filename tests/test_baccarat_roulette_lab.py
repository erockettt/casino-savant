import pytest
from fastapi.testclient import TestClient

from casino_savant.api.app import app
from casino_savant.blackjack.rules import BlackjackRules
from casino_savant.cards import full_shoe
from casino_savant.games import baccarat as bac
from casino_savant.games import roulette as rl
from casino_savant.lab import progressions as pg
from casino_savant.lab import risk
from casino_savant.lab.blackjack_sim import BlackjackSim, SimConfig
from casino_savant.profiles import ProfileStore


# --- Baccarat: published 8-deck values (Wizard of Odds / standard combinatorial result)
def test_baccarat_8deck_reference():
    a = bac.analyze(bac.BaccaratRules(decks=8))
    assert a["p_banker"] == pytest.approx(0.458597, abs=2e-6)
    assert a["p_player"] == pytest.approx(0.446247, abs=2e-6)
    assert a["p_tie"] == pytest.approx(0.095156, abs=2e-6)
    ev = {b["bet"]: b["ev"] for b in a["bets"]}
    assert ev["BANKER"] == pytest.approx(-0.010579, abs=2e-6)
    assert ev["PLAYER"] == pytest.approx(-0.012351, abs=2e-6)
    assert ev["TIE"] == pytest.approx(-0.143596, abs=2e-6)
    assert ev["PLAYER PAIR"] == pytest.approx(-0.103614, abs=2e-6)
    assert a["recommendation"] == "NO BET"


def test_baccarat_variants():
    ez = {b["bet"]: b["ev"] for b in bac.analyze(bac.BaccaratRules(variant="ez"))["bets"]}
    assert ez["BANKER"] == pytest.approx(-0.010183, abs=3e-6)
    nc = {b["bet"]: b["ev"] for b in bac.analyze(bac.BaccaratRules(variant="no_commission_6"))["bets"]}
    assert nc["BANKER"] == pytest.approx(-0.014581, abs=3e-6)


def test_baccarat_probabilities_sum_to_one_on_depleted_shoe():
    comp = list(full_shoe(1)); comp[9] -= 10; comp[7] -= 3
    a = bac.analyze(bac.BaccaratRules(decks=1), tuple(comp))
    assert a["p_banker"] + a["p_player"] + a["p_tie"] == pytest.approx(1.0, abs=1e-12)


def test_baccarat_card_removal_can_flip_sign_in_extreme_shoes():
    # Pair bet with a shoe of only 9s and tens: pairs very likely -> positive EV (effect is real, but rare in practice)
    comp = (0, 0, 0, 0, 0, 0, 0, 0, 20, 20)
    a = bac.analyze(bac.BaccaratRules(decks=1), comp)
    assert a["recommendation"] != "NO BET"


# --- Roulette
@pytest.mark.parametrize("wheel,edge", [("european", 1 / 37), ("american", 2 / 38), ("triple_zero", 3 / 39)])
def test_roulette_edges(wheel, edge):
    for row in rl.analyze(rl.RouletteRules(wheel=wheel))["bets"]:
        if row["bet"] != "top_line":
            assert row["house_edge"] == pytest.approx(edge, abs=1e-12)


def test_roulette_special_rules():
    assert rl.bet_ev(rl.RouletteRules(wheel="american"), "top_line")["house_edge"] == pytest.approx(3 / 38)
    assert rl.bet_ev(rl.RouletteRules(la_partage=True), "red")["house_edge"] == pytest.approx(0.5 / 37)


# --- Progressions: return per unit wagered equals the edge (optional stopping)
@pytest.mark.parametrize("prog", sorted(pg.PROGRESSIONS))
def test_progressions_do_not_change_edge(prog):
    r = pg.simulate_sessions(pg.EUROPEAN_RED, prog, sessions=6000, rounds=60, seed=11)
    assert r["edge_inside_ci"] or abs(r["observed_return_per_unit_wagered"] - r["theoretical_edge_per_unit"]) < 0.01


def test_martingale_wins_often_but_loses_big():
    r = pg.simulate_sessions(pg.AMERICAN_RED, "martingale", sessions=5000, rounds=100, seed=2)
    assert r["p_session_win"] > 0.6 and r["worst_session"] <= -100


# --- Risk
def test_risk_rules():
    assert risk.stake_advice(-0.005, 0.001, 1.3, 10000)["recommended_bet"] == 0
    assert risk.stake_advice(0.01, 0.008, 1.3, 10000)["recommended_bet"] == 0     # not significant
    adv = risk.stake_advice(0.01, 0.001, 1.3, 10000)
    assert 0 < adv["recommended_bet"] < 10000 * 0.01 / 1.3
    assert risk.risk_of_ruin(-0.01, 1.1, 100) == 1.0
    assert risk.ruin_before_target(0.0, 1.0, 100, 100) == pytest.approx(0.5)


# --- Simulation: basic strategy within published range for 6D S17 DAS LS (~ -0.3%..-0.5%)
def test_sim_basic_strategy_edge_plausible():
    res = BlackjackSim(BlackjackRules(decks=6), SimConfig(rounds=150_000, seed=5)).run()
    lo, hi = res.ci95
    assert lo < -0.0035 < hi or abs(res.ev_per_round + 0.004) < 0.008


def test_sim_reproducible():
    a = BlackjackSim(BlackjackRules(), SimConfig(rounds=5000, seed=9)).run().net
    b = BlackjackSim(BlackjackRules(), SimConfig(rounds=5000, seed=9)).run().net
    assert a == b


# --- Profiles (Bovada templates must be unverified)
def test_bovada_templates_unverified_and_valid():
    ps = ProfileStore().all()
    bov = [p for p in ps.values() if p.venue == "Bovada"]
    assert len(bov) >= 5
    for p in bov:
        assert not p.verified
        p.build_rules()
    assert ps["bovada-bj-rng-classic"].build_rules().counting_meaningful is False


# --- API smoke
def test_api_end_to_end():
    c = TestClient(app)
    r = c.post("/api/blackjack/analyze", json={"player": "T 6", "dealer_up": "T", "profile_id": "reference-6d-s17"})
    assert r.status_code == 200 and r.json()["best"] == "SURRENDER"
    r = c.post("/api/blackjack/analyze", json={"player": "T 6", "dealer_up": "T", "profile_id": "bovada-bj-rng-classic",
                                                "seen_cards": "2 3 4"})
    assert "UNVERIFIED" in r.json()["profile"] and "ignored" in r.json()["shoe_source"]
    sid = c.post("/api/session", json={"profile_id": "reference-6d-s17"}).json()["session_id"]
    for slot, i, rank in [("player", 0, "T"), ("dealer", 0, "9"), ("player", 1, "6")]:
        assert c.post(f"/api/session/{sid}/observe", json={"slot": slot, "index": i, "rank": rank}).json()["accepted"]
    assert c.get(f"/api/session/{sid}/analyze").json()["ready"]
    assert c.post("/api/baccarat/analyze", json={}).json()["recommendation"] == "NO BET"
    assert c.post("/api/roulette/analyze", json={"profile_id": "bovada-roulette-american"}).status_code == 200
    assert c.post("/api/blackjack/analyze", json={"player": "T X", "dealer_up": "T"}).status_code == 422
