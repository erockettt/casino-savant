# Research register

Labels: **PROVEN MATHEMATICALLY** · **EMPIRICALLY SUPPORTED** · **HYPOTHESIS** · **INCONCLUSIVE** · **DISPROVEN**.
"Reproduced" means this codebase recomputes the figure and a test enforces it.

## Findings

| # | Claim | Label | Evidence |
|---|---|---|---|
| F1 | Baccarat 8D: Banker 1.058%, Player 1.235%, Tie (8:1) 14.36%, Pair (11:1) 10.36% house edge | PROVEN · reproduced | Exact enumeration; `test_baccarat_8deck_reference` |
| F2 | EZ Baccarat banker edge 1.018%; no-commission (banker 6 pays ½) 1.458% | PROVEN · reproduced | `test_baccarat_variants` |
| F3 | Roulette edges 2.70% / 5.26% / 7.69%; top line 7.89%; La Partage 1.35% | PROVEN · reproduced | `test_roulette_*` |
| F4 | No betting progression changes return per unit wagered | PROVEN (optional stopping) · confirmed by simulation | MATH_SPEC LAB-1; BENCHMARKS §4 |
| F5 | Roads (Big Road, Big Eye Boy, Small Road, Cockroach Pig), streak following or fading, and alternating bets have no predictive value | PROVEN for i.i.d.-equivalent outcomes. In a finite shoe, outcomes depend only on remaining composition, which roads summarise far less well than a direct card count | Exchangeability; BAC-1 |
| F6 | "Hot/cold numbers" predict nothing on an unbiased wheel | PROVEN (independence) | — |
| F7 | Dealer bust (S17, ∞ deck): 2:35.36%, 3:37.39%, 4:39.45%, 5:41.64%, 6:42.32%, 7:26.23%, 8:24.45%, 9:22.84%, T:21.21%, A:11.53% | PROVEN · reproduced | `test_infinite_dealer_bust_reference` |
| F8 | ∞ deck: 16 v T stand −0.5404, hit −0.5398 | PROVEN · reproduced | `test_infinite_16_vs_10_reference` |
| F9 | CD exceptions: T,6 v T hit but 4,4,8 v T stand (6D, no surrender); T,2 v 4 hit while other 12s stand | PROVEN for stated rules · reproduced | `test_composition_dependence_16_vs_10`, `test_cd_exception_t2_vs_4` |
| F10 | 6D S17 DAS LS basic strategy ≈ −0.40% | EMPIRICALLY SUPPORTED · reproduced (−0.400% ± 0.111%, 4M rounds) | BENCHMARKS §2 |
| F11 | Hi-Lo edge rises ≈0.5% per true count | EMPIRICALLY SUPPORTED · reproduced (EV-by-TC table) | BENCHMARKS §2 |
| F12 | Counting yields nothing on reshuffle-every-hand games | PROVEN (no information carried between rounds) · confirmed by simulation | BENCHMARKS §3 |
| F13 | Illustrious 18 / Fab 4 Hi-Lo indices | EMPIRICALLY SUPPORTED (literature); **not re-derived here** | Schlesinger, *Blackjack Attack* |
| F14 | Extreme baccarat compositions can make a bet positive (e.g. pairs) | PROVEN for the composition; **operational value INCONCLUSIVE** (rare, late in the shoe, needs exact tracking) | `test_baccarat_card_removal_can_flip_sign_in_extreme_shoes` |
| F16 | Live-dealer 8D shoes are beatable only by sitting out negative counts, with modest edges and long horizons | EMPIRICALLY SUPPORTED (simulation, template rules) | LIVE_DEALER_STUDY.md |
| F15 | Wheel bias could create a roulette edge | HYPOTHESIS. It needs a wheel-specific dataset with enough power to detect a bias larger than the house edge (see Q4) | — |

## Source register

| Source | Use | Accessed |
|---|---|---|
| Griffin, *The Theory of Blackjack* (6th ed., 1999) | Effects of removal, count-system theory | literature |
| Schlesinger, *Blackjack Attack* (3rd ed., 2005) | Illustrious 18, Fab 4, betting correlation | literature |
| Wong, *Professional Blackjack* (1994) | Halves count, indices | literature |
| Thorp, *Beat the Dealer* (1962/66) | Historical basis of counting | literature |
| Wizard of Odds (wizardofodds.com) — blackjack dealer probabilities, baccarat and roulette edges | Reference fixtures F1–F3, F7, F8 | values from prior knowledge, re-derived in code |
| [easy.vegas – blackjack](https://easy.vegas/games/blackjack), [easy.vegas – online](https://easy.vegas/online) | Online-blackjack context | 2026-11-09 search |
| [UKGC RTS 16 – third-party software](https://www.gamblingcommission.gov.uk/standards/remote-gambling-and-software-technical-standards/rts-16-use-of-third-party-software) | Regulatory norm: operators should state which software is permitted | 2026-11-09 |
| [CardPlayer – Bovada alternatives](https://cardplayer.com/online-casinos/bovada-alternatives) | Bovada context (offshore operator) | 2026-11-09 |
| [Casino.org – Bovada review](https://corg-worker-test.g7cloud.com/us/reviews/bovada-casino/) | Bovada context (offshore operator, no regulator for disputes) | 2026-11-09 |

## Research queue (open questions)

- Q1 Exact multi-hand split EV (replace the BJ-4 approximation); measure the approximation error by exhaustive enumeration at 1–2 decks.
- Q2 Simulation-derived betting correlation (BC), playing efficiency (PE) and insurance correlation (IC) for every implemented count, plus sensitivity to missed cards.
- ~~Q3~~ **Answered** in [LIVE_DEALER_STUDY.md](LIVE_DEALER_STUDY.md). In 8-deck shoes at 50–62.5% penetration, playing every round with a 1–8 or 1–16 spread shows **no** edge at 95% confidence. Sitting out true counts below +1 shows +0.6% to +1.3% per unit bet across every rule set and penetration tested. It needs roughly 850–4,300 hours to reach N0, with a 30–55% risk of ruin on a 200-unit bankroll. Label: EMPIRICALLY SUPPORTED (simulation) for template rules.
- Q4 Roulette bias power analysis: spins needed to detect a pocket bias of size δ at α = 0.05 / 37 (Bonferroni) with 80% power, and whether such a δ beats 2.70%.
- Q5 Full-shoe baccarat composition simulation: how often any bet turns positive at realistic cut-card depth, and the EV per hand of a perfect-information side counter.
- Q6 Recogniser validation: build a labelled screenshot dataset and require ≥99.5% per-card accuracy with calibrated confidence before vision input can bypass manual confirmation.
