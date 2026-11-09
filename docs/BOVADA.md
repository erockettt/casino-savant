# Using Casino Savant with Bovada

## What "adaptable for Bovada" means here

Casino Savant ships **rule-profile templates** for Bovada's game families. The solver
then gives exact numbers for whichever rules you confirm. It does **not** connect to
Bovada, read its screens, or place bets.

| Profile id | Game | Delivery | Counting? |
|---|---|---|---|
| `bovada-bj-rng-classic` | Blackjack (RNG) | software | Disabled (reshuffled every hand) |
| `bovada-bj-rng-single-deck` | Single-deck blackjack (RNG) | software | Disabled |
| `bovada-bj-live` | Live-dealer blackjack | studio shoe | Enabled. Useful only if penetration is real |
| `bovada-baccarat` | Baccarat | either | Composition matters only in a live shoe |
| `bovada-roulette-american` / `-european` | Roulette | RNG | n/a |

## Status: every Bovada rule is UNVERIFIED

I could not find a primary Bovada source for its table rules. Searches returned only
secondary sites, and one of them describes a Bovada single-deck game as H17 with double
on any two cards and after splits. Rules also differ by title and can change. Every
template therefore ships with `verified: false`, and every analysis shows a yellow
"UNVERIFIED template" banner.

### How to verify a profile (2 minutes per game)

1. Open the game on Bovada and find its **Rules / Help / ⓘ** screen.
2. Read off each field:
   - number of decks
   - whether the dealer hits or stands on soft 17
   - the blackjack payout (3:2 or 6:5)
   - whether the dealer peeks or uses no hole card
   - doubling restrictions, and whether doubling after a split is allowed
   - how many split hands are allowed, and whether split aces can be resplit or hit
   - whether surrender is offered
   - insurance
3. Save a corrected copy. A file in `profiles/` overrides the template with the same id:

```bash
curl -X PUT http://127.0.0.1:8000/api/profiles/bovada-bj-rng-classic -H 'Content-Type: application/json' -d '{"venue":"Bovada","game":"blackjack","title":"Blackjack (RNG) – verified 2026-11-09","delivery":"rng","verified":true,"source":"in-game rules screen, checked 2026-11-09","rules":{"decks":6,"dealer_hits_soft_17":false,"blackjack_payout":1.5,"dealer_peeks":true,"double_on":"any","double_after_split":true,"max_split_hands":2,"surrender":"none","shuffle":"per_hand"}}'
```

You can also edit `profiles/<id>.json` by hand.

## What the math says about Bovada-style games

- **RNG blackjack:** the deck is effectively reshuffled before every hand. Card counting carries **zero**
  information, and the tracker resets every round for `shuffle: "per_hand"`. Benchmark §3 shows a counter
  with a 1–12 spread getting the same −0.55% as flat basic strategy. The only lever is **perfect
  rule-specific strategy**, which the solver gives you. It cuts the edge to the game's minimum but cannot
  make it positive.
- **Live-dealer blackjack:** studio shoes are often cut around half the shoe. Counting gains shrink sharply
  with shallow penetration. Use the simulator with the confirmed penetration before assuming any edge:

```python
from casino_savant.lab.blackjack_sim import BlackjackSim, SimConfig
from casino_savant.blackjack.rules import BlackjackRules
r = BlackjackRules(decks=8, dealer_peeks=False, penetration=0.5, surrender="none", max_split_hands=2)
print(BlackjackSim(r, SimConfig(rounds=2_000_000, use_indices=True, bet_ramp={-99: 1, 2: 2, 3: 4, 4: 8})).run().ev_per_round)
```

- **Baccarat and roulette:** every standard wager has negative expectation. The engines will say **NO BET**.
  Roads, streaks and progressions do not change this (Benchmark §4).

## Terms of service and responsible use

Online casinos commonly restrict third-party software or assistance during play. I could not retrieve
Bovada's current terms, so **read them yourself** (search the terms page for "software", "bot", "third
party" or "advantage") before using any tool while a hand is in progress.

The project avoids automation by design:

- no screen scraping
- no browser automation
- no auto-betting
- no detection evasion

The intended workflow is studying, drilling the rule-specific strategy and post-session review (Replay Lab).
Bovada is an offshore operator. A CardPlayer review notes that no regulator can step in on a dispute,
so set your own loss limits (`SessionTracker.loss_limit`).
