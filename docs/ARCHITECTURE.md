# Architecture

```
casino-savant/
├── casino_savant/
│   ├── cards.py              shared rank/shoe primitives (composition = tuple of 10 counts)
│   ├── profiles.py           venue rule profiles + verification status (Bovada templates)
│   ├── blackjack/
│   │   ├── rules.py          BlackjackRules (typed, validated)
│   │   ├── solver.py         composition-dependent EV solver (source of truth)
│   │   ├── infinite.py       independent ∞-deck solver, basic-strategy generator
│   │   └── counting.py       count systems, ShoeTracker, published indices
│   ├── games/
│   │   ├── baccarat.py       exact finite-shoe enumeration, bet EVs
│   │   └── roulette.py       exact bet EVs, French rules
│   ├── state/
│   │   ├── table.py          TableSession: observations → state → analysis; Replay Lab audit
│   │   └── vision.py         Recognizer protocol, FrameAggregator (prototype)
│   ├── lab/
│   │   ├── blackjack_sim.py  seeded Monte Carlo
│   │   ├── progressions.py   staking-system lab
│   │   └── risk.py           Kelly, RoR, session tracker
│   └── api/app.py            FastAPI (REST); serves web/index.html
├── web/index.html            dashboard (vanilla JS, no build step)
├── profiles/                 user-verified profile JSON (overrides templates)
├── scripts/run_benchmarks.py writes docs/BENCHMARKS.md
├── tests/                    pytest + hypothesis
└── docs/
```

## Data flow (table companion)

```
manual keypad ─┐
screenshot ────┼─► Observation(round, slot, index, rank, confidence, source, frame)
vision (future)┘        │  dedup by (round, slot, index) · conflicts → user · low confidence → held
                        ▼
                 TableSession ──► ShoeTracker (exact unseen composition, counts)
                        │
                        ▼
              BlackjackSolver(rules from VenueProfile) ──► Analysis (all legal EVs, margin,
                        │                                   warnings, explanation, profile banner)
                        ▼
              Replay Lab log ──► audit (EV lost per decision, independent of results)
```

## Design rules

- The solvers are deterministic and are the only source of numbers. An LLM layer (planned) may explain results
  or parse input, but never computes an EV.
- Every output carries its assumptions: the rules string, the profile verification banner, and the shoe-source
  string (tracked vs assumed fresh).
- Missing, conflicting or low-confidence inputs block a recommendation; they are never filled in.
- RNG and CSM profiles (`shuffle != "shoe"`) disable counting and reset the composition every round.

## Planned (not built)

- React/Next.js front end, PostgreSQL persistence, WebSocket streaming. The current REST + static page covers Phase 4's manual-entry scope.
- A trained card recogniser (OpenCV / detector), gated on the labelled-dataset accuracy in RESEARCH Q6.
- Challenger-vs-champion strategy registry with versioned configs and promotion gates (Phase 7).
- A voice / natural-language explanation agent.
