import pytest
from hypothesis import given, settings, strategies as st

from casino_savant.blackjack.counting import SYSTEMS, ShoeTracker
from casino_savant.blackjack.rules import BlackjackRules
from casino_savant.cards import PER_DECK
from casino_savant.state.table import Observation, TableSession
from casino_savant.state.vision import Detection, FrameAggregator


@pytest.mark.parametrize("name", [k for k, v in SYSTEMS.items() if v["balanced"]])
def test_balanced_systems_sum_to_zero(name):
    assert sum(t * n for t, n in zip(SYSTEMS[name]["tags"], PER_DECK)) == 0


def test_ko_unbalanced_plus_four_per_deck():
    assert sum(t * n for t, n in zip(SYSTEMS["ko"]["tags"], PER_DECK)) == 4


@settings(max_examples=50, deadline=None)
@given(st.lists(st.integers(0, 9), max_size=150), st.integers(1, 8))
def test_full_shoe_hilo_ends_at_zero(seq, decks):
    t = ShoeTracker(decks)
    seen = 0
    for r in seq:
        if t.seen[r] < t.initial[r]:
            t.observe(r)
            seen += 1
    assert t.cards_remaining == 52 * decks - seen
    # dealing the rest of the shoe brings any balanced count back to 0
    for r in range(10):
        while t.seen[r] < t.initial[r]:
            t.observe(r)
    assert t.running_count() == 0


def test_hilo_true_count():
    t = ShoeTracker(6)
    for r in [1, 2, 3, 4, 5] * 4:  # 20 low cards -> RC +20
        t.observe(r)
    assert t.running_count() == 20
    assert t.true_count(rounding="none") == pytest.approx(20 / ((312 - 20) / 52))


def test_duplicate_obs_id_not_double_counted_and_overflow_rejected():
    t = ShoeTracker(1)
    assert t.observe(9, obs_id="x") and not t.observe(9, obs_id="x")
    assert t.running_count() == -1
    for _ in range(3):
        t.observe(0)
    with pytest.raises(ValueError):
        t.observe(0)
        t.observe(0)


def test_low_confidence_held_not_counted():
    t = ShoeTracker(6)
    assert not t.observe(1, confidence=0.6)
    assert t.running_count() == 0 and len(t.low_confidence) == 1


def test_table_session_dedup_conflict_and_analysis():
    s = TableSession(BlackjackRules())
    for slot, i, r in [("player", 0, "T"), ("dealer", 0, "T"), ("player", 1, "6")]:
        assert s.observe(Observation(1, slot, i, r))["accepted"]
    assert not s.observe(Observation(1, "player", 1, "6"))["accepted"]          # same card, later frame
    assert not s.observe(Observation(1, "player", 1, "5"))["accepted"]          # conflicting read
    assert s.analyze()["ready"] is False                                        # blocked until corrected
    s.correct(1, "player", 1, "6")
    a = s.analyze()
    assert a["ready"] and a["best"] == "SURRENDER"
    assert s.tracker.running_count() == -1


def test_rng_profile_resets_each_round():
    s = TableSession(BlackjackRules(shuffle="per_hand"))
    for i, r in enumerate("2345"):
        s.observe(Observation(1, "other", i, r))
    assert sum(s.tracker.seen) == 4
    s.new_round()
    assert sum(s.tracker.seen) == 0


def test_replay_audit_measures_ev_not_results():
    s = TableSession(BlackjackRules(surrender="none"))
    for slot, i, r in [("player", 0, "T"), ("dealer", 0, "6"), ("player", 1, "2")]:
        s.observe(Observation(1, slot, i, r))
    rec = s.record_decision("player", "HIT")   # 12 v 6: STAND is correct
    assert rec["recorded"] and rec["ev_loss"] > 0
    assert s.audit()["mistakes"] == 1


def test_frame_aggregator_requires_consistency():
    agg = FrameAggregator(round_id=1, k=3)
    d = lambda r, c=0.99: [Detection("player", 0, r, c)]
    assert agg.push("f1", d("T")) == [] and agg.push("f2", d("T")) == []
    assert len(agg.push("f3", d("T"))) == 1
    assert agg.push("f4", d("T")) == []                      # already emitted, never re-counted
    agg2 = FrameAggregator(round_id=1, k=2)
    agg2.push("a", d("T")); out = agg2.push("b", d("4"))     # disagreement resets + logged
    assert out == [] and agg2.conflicts
