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

## What Bovada's own public pages confirm (checked 2026-11-09)

A read-only Browser Use run read Bovada's public help pages and Terms of Service. I then re-fetched every cited
page and checked each quote against the live text: all 31 checkable quotes matched. Raw results are in
`research/bovada/`. The two runs cost $0.36.

| Game | Confirmed by Bovada | Not published anywhere public |
|---|---|---|
| Classic Blackjack (RNG) | 6 decks, 3:2, **shuffled after every hand**, **dealer hits soft 17**, split up to 3 hands, surrender allowed | peek, doubling limits, DAS, split aces, insurance, surrender timing |
| Single Deck (RNG) | 1 deck, H17, double any two, double after split, split aces one card, 3:2, split to 2 hands (New) / 3 (Classic) | peek, surrender, insurance |
| Double Deck (RNG) | 2 decks, split once ("same rules as Single Deck") | payout, peek, surrender, insurance |
| Live Dealer Blackjack | **nothing** | everything: decks, soft 17, payout, peek, penetration |
| Baccarat | only live **Super 6** (6 decks, 5% commission, tie 8:1, pairs 11:1), which Bovada calls a different game | standard baccarat rules |
| Roulette | American (38 slots, 0 + 00) and European (37 slots) both offered, also live | La Partage / En Prison |

Simulated house edge with the confirmed rules (1.5M hands each, ±0.18%): **Single Deck ≈ −0.11%**,
Classic ≈ −0.47%, Double Deck ≈ −0.62%. All are negative and none can be counted, because every RNG game is
reshuffled each hand. Single Deck is the cheapest to play.

The blackjack profiles stay **unverified** (the banner says PARTLY CONFIRMED) because peek and insurance rules aren't
public. American roulette is fully verified, since its only rule is the wheel type.

## Terms of Service: what applies to this tool

Bovada's Terms of Service (latest update January 3, 2024) say:

- **§6.3 No Player Assistance Programs:** prohibits "external player assistance programs" designed to give an
  unfair advantage. The definition explicitly includes **computer software**. Penalty: account closure and voided
  winnings.
- **§6.4 Bots Prohibited:** all actions must be made by the player through Bovada's own interface. Penalty:
  account disabled and **all balances, including deposits, forfeited**.
- **Card counting and "advantage play" are not mentioned** anywhere in the public terms or help center.

**Practical reading:** counting in your head from what you see is your own first-hand observation. Running this
software **during real-money play** could reasonably be treated as an §6.3 assistance program. Use Casino Savant
for **study, drills, and post-session review**. It never places bets, and you should not run it alongside a live
real-money hand on Bovada.

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

## Graded suggestions: how to use them on Bovada Live

The tool **only suggests**. You place every bet yourself.

1. In the dashboard, open **Table tracker**, choose `bovada-bj-live` (or your verified copy), and enter your
   bankroll and maximum bet in units. Untick "Table lets me sit out rounds" if the table doesn't allow it.
2. As cards are exposed, tap them in. The tool shows two graded suggestions:
   - **Next-round bet:** SIT OUT, TABLE MINIMUM, or BET n UNITS, from the true count and half-Kelly sizing.
   - **Playing action:** the exact-EV best action, with every alternative's EV.
3. After acting, tap the action you took. The **Replay Lab** groups your decisions by grade and reports the
   EV you gave up by not following the suggestion. Wins and losses are never used to grade: a correct play
   that loses is variance.

| Grade | Meaning |
|---|---|
| A | Clear-cut: large EV margin, verified rules, reliable inputs |
| B | Sound: moderate margin, or one input caveat (e.g. unverified rules, few cards seen) |
| C | Close call: options nearly equal, or the edge estimate is within its own error |
| D | Weak foundation: several caveats stacked (approximation + unverified rules + guessed composition) |
| — | No suggestion: a required card is missing or two readings conflict |

Unverified Bovada templates cap most grades below A. Verifying the profile is the single biggest grade
improvement you can make.

### What the live-dealer study found (docs/LIVE_DEALER_STUDY.md)

- Playing every round with a bet spread at 50–62.5% penetration did **not** beat an 8-deck shoe.
- **Sitting out true counts below +1** produced +0.6% to +1.3% per unit bet. It needs 850–4,300 hours to reach N0
  (the number of hours before expected profit outweighs one standard deviation of luck), and has a 30–55% risk of
  ruin on a 200-unit bankroll. That's a long, high-variance grind, not a quick win.
- Before investing time, measure Bovada Live's real penetration: over several shoes, count how many cards are
  dealt before the shuffle. Then rerun the study with that number.

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
