# Casino Savant

Exact-math decision support and research lab for blackjack, card counting, baccarat and roulette.
Deterministic solvers are the source of truth; nothing is guessed, and the system is allowed to conclude
that **no advantage exists** (which is the correct answer for roulette, standard baccarat and RNG blackjack).

## Quick start

```bash
pip install -r requirements.txt
```

```bash
python -m pytest -q
```

```bash
uvicorn casino_savant.api.app:app --port 8000
```

Then open http://127.0.0.1:8000/ for the dashboard (Blackjack · Table tracker · Baccarat · Roulette · Lab).

Reproduce the benchmark report (≈1 minute on 4 cores):

```bash
python scripts/run_benchmarks.py --rounds 4000000
```

## What is built (and tested)

| Component | Module | Status |
|---|---|---|
| Composition-dependent blackjack EV solver (stand/hit/double/split/surrender/insurance, peek & ENHC, H17/S17, 3:2/6:5, DAS, resplits, restricted doubles) | `casino_savant/blackjack/solver.py` | Built · exact except split (labelled approximation) |
| Independent infinite-deck solver + rule-specific basic-strategy generator | `blackjack/infinite.py` | Built · matches published references |
| Counting engine: Hi-Lo, KO, Hi-Opt I/II, Omega II, Wong Halves, Zen; exact rank tracking, true count, penetration, unseen-burn uncertainty, ace side count | `blackjack/counting.py` | Built |
| Table state manager with per-card identity (no double counting across frames), conflict detection, user correction, RNG auto-reset | `state/table.py` | Built |
| Replay Lab: records the action taken and audits EV lost vs the exact solver | `state/table.py` | Built |
| Vision interface + temporal-consistency frame aggregator | `state/vision.py` | **Prototype** — no trained recogniser |
| Baccarat exact finite-shoe enumerator (commission, EZ, no-commission-6, tie, pairs) | `games/baccarat.py` | Built · matches published values to 6 d.p. |
| Roulette (single/double/triple zero, La Partage, En Prison) | `games/roulette.py` | Built |
| Blackjack Monte Carlo (real shoe, cut card, splits, Hi-Lo ramp and indices, EV by true count) | `lab/blackjack_sim.py` | Built |
| Progression lab (Martingale, Reverse Martingale, Paroli, Fibonacci, D'Alembert, Labouchere, flat) | `lab/progressions.py` | Built |
| Risk: conservative-edge Kelly, risk of ruin, session tracker with loss limits | `lab/risk.py` | Built |
| **Graded suggestions**: every playing action, next-bet size and NO BET gets an A–D grade with the reasons. The system never bets | `grading.py` | Built |
| Live-dealer study (penetration × rules × spread, with sit-out) | `scripts/live_dealer_study.py` → `docs/LIVE_DEALER_STUDY.md` | Built |
| Venue profiles with verification status, **Bovada templates** | `profiles.py`, `profiles/*.json` | Built — Bovada rules **unverified** |
| FastAPI backend + dashboard | `api/app.py`, `web/index.html` | Built |

See `docs/` for the architecture, the math spec, the research register, benchmark results, the Bovada guide and known limitations.
