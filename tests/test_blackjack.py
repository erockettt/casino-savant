import random

import pytest

from casino_savant.blackjack.infinite import InfiniteDeck
from casino_savant.blackjack.rules import BlackjackRules
from casino_savant.blackjack.solver import BlackjackSolver
from casino_savant.cards import HandTotal, add_card, full_shoe, parse_cards, remove

S17 = BlackjackRules()
H17 = BlackjackRules(dealer_hits_soft_17=True)


def evs(a):
    return {x.action: x.ev for x in a.legal}


# --- Reference fixtures: infinite-deck dealer bust probabilities, S17 -------------
# Published widely (e.g. Wizard of Odds "dealer outcome probabilities"); values for
# 10 and A are unconditional on the dealer natural, so we convert our conditional ones.
DEALER_BUST_S17 = {2: 0.3536, 3: 0.3739, 4: 0.3945, 5: 0.4164, 6: 0.4232, 7: 0.2623, 8: 0.2445, 9: 0.2284}


@pytest.mark.parametrize("up,ref", DEALER_BUST_S17.items())
def test_infinite_dealer_bust_reference(up, ref):
    assert InfiniteDeck(S17).dealer_final(up)[5] == pytest.approx(ref, abs=6e-4)


def test_infinite_dealer_bust_ten_ace_unconditional():
    I = InfiniteDeck(S17)
    assert I.dealer_final(10)[5] * (1 - 1 / 13) == pytest.approx(0.2121, abs=5e-4)
    assert I.dealer_final(1)[5] * (1 - 4 / 13) == pytest.approx(0.1153, abs=5e-4)


def test_infinite_16_vs_10_reference():
    I = InfiniteDeck(S17)
    assert I.stand(16, 10) == pytest.approx(-0.5404, abs=2e-4)
    assert I.hit(16, False, 10) == pytest.approx(-0.5398, abs=2e-4)


# --- Independent cross-check: CD solver with huge shoe -> infinite deck ------------
@pytest.mark.parametrize("hand,up", [((9, 5), 9), ((9, 1), 5), ((0, 6), 8), ((4, 5), 0), ((9, 9), 5)])
def test_cd_converges_to_infinite(hand, up):
    rules = BlackjackRules(decks=4000)
    s = BlackjackSolver(rules)
    I = InfiniteDeck(rules)
    a = evs(s.analyze(list(hand), up))
    ht = HandTotal.of(list(hand))
    upv = 1 if up == 0 else (10 if up == 9 else up + 1)
    assert a["STAND"] == pytest.approx(I.stand(ht.total, upv), abs=2e-3)
    if ht.total < 21:
        assert a["HIT"] == pytest.approx(I.hit(ht.total, ht.soft, upv), abs=2e-3)
        assert a["DOUBLE"] == pytest.approx(I.double(ht.total, ht.soft, upv), abs=2e-3)


# --- Monte Carlo verification of exact finite-shoe EVs ------------------------------
def _mc_stand(rules, player, up, n, seed):
    rng = random.Random(seed)
    shoe = remove(full_shoe(rules.decks), player + [up])
    deck = [r for r, c in enumerate(shoe) for _ in range(c)]
    pt = HandTotal.of(player).total
    tot = cnt = 0
    while cnt < n:
        rng.shuffle(deck)
        hole = deck[0]
        if {up, hole} == {0, 9}:
            continue  # condition on no dealer blackjack (peek)
        t, s = add_card(0, False, up)
        t, s = add_card(t, s, hole)
        i = 1
        while t < 17 or (t == 17 and s and rules.dealer_hits_soft_17):
            t, s = add_card(t, s, deck[i]); i += 1
        tot += 1 if (t > 21 or pt > t) else (-1 if pt < t else 0)
        cnt += 1
    return tot / cnt


@pytest.mark.parametrize("rules,player,up", [(BlackjackRules(decks=1), [9, 5], 9), (BlackjackRules(decks=2), [9, 7], 0)])
def test_stand_ev_matches_monte_carlo(rules, player, up):
    exact = evs(BlackjackSolver(rules).analyze(player, up))["STAND"]
    mc = _mc_stand(rules, player, up, 60000, seed=3)
    assert mc == pytest.approx(exact, abs=0.012)  # ~3 SE


# --- Known basic-strategy decisions (6D S17 DAS LS) -----------------------------------
@pytest.mark.parametrize("player,up,best", [
    ("T 6", "T", "SURRENDER"), ("T 2", "3", "HIT"), ("8 4", "4", "STAND"), ("5 6", "T", "DOUBLE"),
    ("5 6", "A", "HIT"), ("A 7", "9", "HIT"), ("A 7", "3", "DOUBLE"), ("8 8", "T", "SPLIT"),
    ("A A", "6", "SPLIT"), ("T T", "6", "STAND"), ("9 9", "7", "STAND"), ("9 9", "9", "SPLIT"),
    ("5 5", "9", "DOUBLE"), ("T 5", "T", "SURRENDER"), ("T 4", "T", "HIT"), ("A 6", "2", "HIT"),
])
def test_basic_strategy_6d_s17(player, up, best):
    s = BlackjackSolver(S17)
    assert s.analyze(parse_cards(player), parse_cards(up)[0]).best == best


def test_h17_changes_11_vs_ace_to_double():
    # Known rule-dependent deviation: 11 v A is double under H17, hit under S17 (6D).
    assert BlackjackSolver(H17).analyze([4, 5], 0).best == "DOUBLE"
    assert BlackjackSolver(S17).analyze([4, 5], 0).best == "HIT"


def test_composition_dependence_16_vs_10():
    # Two-card 16 (T,6) vs T without surrender: hitting slightly better; 3-card 16 (4,4,8) prefers standing (6D).
    r = BlackjackRules(surrender="none")
    s = BlackjackSolver(r)
    assert s.analyze([9, 5], 9).best == "HIT"
    assert s.analyze([3, 3, 7], 9).best == "STAND"


def test_cd_exception_t2_vs_4():
    # Documented CD exception (multi-deck): T,2 v 4 hits while other 12s stand.
    s = BlackjackSolver(S17)
    assert s.analyze([9, 1], 3).best == "HIT"
    assert s.analyze([6, 4], 3).best == "STAND"


def test_insurance_reflects_composition():
    s = BlackjackSolver(BlackjackRules(decks=1))
    base = s.analyze([4, 6], 0).insurance_ev
    assert base == pytest.approx(3 * 16 / 49 - 1)
    shoe = remove(full_shoe(1), [4, 6, 0] + [1, 2, 3, 4, 5, 1, 2, 3])  # remove 8 low cards
    assert s.analyze([4, 6], 0, shoe).insurance_ev > 0


def test_six_five_payout_and_enhc():
    a = BlackjackSolver(BlackjackRules(blackjack_payout=1.2)).analyze([0, 9], 5)
    assert a.legal[0].ev == pytest.approx(1.2)
    # ENHC: doubling 11 vs T risks the doubled bet against a natural -> lower double EV than peek
    peek = evs(BlackjackSolver(S17).analyze([4, 5], 9))["DOUBLE"]
    enhc = evs(BlackjackSolver(BlackjackRules(dealer_peeks=False)).analyze([4, 5], 9))["DOUBLE"]
    assert enhc < peek


def test_restricted_double_and_no_surrender():
    a = BlackjackSolver(BlackjackRules(double_on="10-11", surrender="none")).analyze([0, 6], 3)
    assert {x.action for x in a.legal} == {"STAND", "HIT"}


def test_parse_rejects_garbage():
    with pytest.raises(ValueError):
        parse_cards("T Z")
