# Mathematical specification

Units: EV is in units of the initial wager. Ranks are indexed A,2..9,T (all ten-valued cards share an index).

## BJ-1 Dealer distribution (exact, finite shoe)
D(t, s, S) = final-total distribution for dealer total t, softness s, unseen composition S.
- Stand when t ≥ 18, or t = 17 and not (s and H17). Bust when t > 21.
- Otherwise D(t,s,S) = Σ_r (S_r/|S|) · D(t⊕r, S − r).
- The hole card is drawn from S as well. With peek, the BJ-completing rank (T under A, A under T) is
  **excluded without renormalising**, so the result sums to P(no dealer BJ | S).

## BJ-2 Conditioning on "dealer has no blackjack" (peek games)
The true process draws the hole card H first, then the player's cards from S − H. Draws without replacement
are exchangeable, so (H, player draws) has the same joint law as (player draws, then H from what remains).
Let U(a) = E[payoff(a) · 1{H ≠ x}] be computed by drawing player cards first and weighting the dealer
step by the excluded-hole mass (BJ-1). Then the exact conditional EV is

  EV(a | no BJ) = U(a) / P(H ≠ x | S₀), where S₀ is the composition at the decision.

At any intermediate state all actions share the same denominator, so argmax over unnormalised U is exact.
A player bust contributes −P(H ≠ x | S') (the conditioning weight of that path).

## BJ-3 Player actions
- Stand: Σ_outcomes D · payoff. Under ENHC, dealer BJ costs 1 unit, or the doubled/split amount unless OBO.
- Hit: H(t,s,S) = Σ_r p_r · {bust: −w(S−r); 21: Stand; else max(Stand, H)}, memoised on (t, s, S).
- Double: one card, then stand at 2× stake.
- Late surrender: −0.5 (peek). Under ENHC: −0.5·(1−p_BJ) − p_BJ.
- Insurance (per unit insured): 2·p_T − (1 − p_T), with p_T from the composition before the peek.

## BJ-4 Split (APPROXIMATION, labelled in every output)
Each split hand is solved exactly with removal of its own cards. Sibling hands are treated as independent:
one hand's draws are not removed from the other's shoe. Resplitting uses a branching recursion
f(pending, hands) with a constant pair-card probability p.
**Status: HYPOTHESIS-level accuracy bound** (<0.002 units at 6D, from agreement with the infinite-deck split
values). Exact multi-hand split algorithms (e.g. Cacarulo/MGP) are on the backlog.

## BJ-5 Counting
Running count RC = Σ tag(rank) over observed cards (KO adds IRC = 4 − 4·decks).
True count TC = RC / (cards remaining / 52). Cards remaining exclude unseen burns.
Unseen-burn uncertainty: sd(TC) ≈ √(k·Var(tag)·fpc) / decks_remaining.
The composition-dependent solver uses the full tracked composition. It never treats unseen cards as known:
burned cards stay in the "unseen" pool, which is exactly right because they are a random sample of it.

## BAC-1 Baccarat
Exact enumeration of P1, B1, P2, B2, P3, B3 with removal, under the standard tableau. Point values
0 (10/J/Q/K) to 9. Pair bets use rank composition; ten-valued ranks are assumed evenly split across T/J/Q/K.

## RL-1 Roulette
EV = p·X − (1 − p). La Partage: an even-money stake loses half on zero. En Prison (single prison): a zero
imprisons the stake, which is returned at par if the next spin wins and lost otherwise.

## LAB-1 Progressions (PROVEN)
With independent rounds and edge e per unit, M_n = Net_n − e·Wagered_n is a martingale. For bounded stakes
and a finite horizon, optional stopping gives E[Net] = e·E[Wagered]. Therefore no staking rule based on past
outcomes changes the return per unit wagered.

## RISK-1
Kelly fraction f* ≈ edge / variance, applied to the one-sided 95% **lower bound** of the edge and scaled
by a fractional multiplier. When that bound is ≤ 0 the system recommends no wager. Risk of ruin (diffusion):
RoR = exp(−2μB/σ²) for μ > 0, and 1 otherwise.
