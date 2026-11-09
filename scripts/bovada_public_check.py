"""Read-only check of Bovada's PUBLIC rules and terms pages via Browser Use.

Never logs in, signs up, opens a cashier, or interacts with a game. Saves the
validated agent output to research/bovada/ for human review; nothing is applied
to profiles automatically.

Live runs cost money, so they need an explicit flag:
    python scripts/bovada_public_check.py --confirm-spend [--max-cost 0.45] [game_rules|terms]
BROWSER_USE_API_KEY must be set server-side (or injected by a proxy).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from casino_savant.integrations.browser_use import RunOutcome, run_task  # noqa: E402

OUT = ROOT / "research" / "bovada"
GUARD = (" Strict rules: do NOT log in, sign up, create an account, enter any personal data, open a cashier, "
         "or start or click into any real-money game. Only read publicly visible help, rules and legal pages "
         "(bovada.lv and its help center). For every fact, give the exact page URL and quote the sentence it "
         "came from. If a fact is not stated on a public page, write NOT FOUND - never guess or use other sites.")

SOURCE = {"type": "object", "properties": {"url": {"type": "string"}, "quote": {"type": "string"}},
          "required": ["url", "quote"]}
TASKS = {
    "game_rules": (
        "On bovada.lv's public help center / casino game-rules pages, find the published rules for: "
        "(1) each blackjack game (RNG and live dealer): number of decks, dealer hits or stands on soft 17, "
        "blackjack payout, dealer peek or no hole card, doubling rules, double after split, number of splits, "
        "split aces rules, surrender, insurance, and for live dealer the shuffle method or penetration; "
        "(2) baccarat: decks, commission, tie and pair payouts, any no-commission variant; "
        "(3) roulette: which wheels are offered and whether La Partage or En Prison applies." + GUARD,
        {"type": "object", "required": ["blackjack", "baccarat", "roulette", "sources"],
         "properties": {"blackjack": {"type": "array", "items": {"type": "object"}},
                        "baccarat": {"type": "object"}, "roulette": {"type": "object"},
                        "sources": {"type": "array", "items": SOURCE}}},
    ),
    "terms": (
        "On bovada.lv's public Terms and Conditions / Terms of Use pages, find every clause about third-party "
        "software, bots, programs, devices or tools used while playing; advantage play or card counting; "
        "collusion; and consequences for accounts or winnings that break these rules. Give short verbatim "
        "quotes with URL and section heading, and the terms date/version if shown." + GUARD,
        {"type": "object", "required": ["clauses", "terms_version", "sources"],
         "properties": {"clauses": {"type": "array", "items": {"type": "object"}},
                        "terms_version": {"type": "string"}, "sources": {"type": "array", "items": SOURCE}}},
    ),
}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("tasks", nargs="*", help=f"subset of {sorted(TASKS)} (default: all)")
    ap.add_argument("--confirm-spend", action="store_true", help="required: acknowledges each run is billed")
    ap.add_argument("--max-cost", type=float, default=0.45, help="USD cap per run (max 1.00)")
    a = ap.parse_args()
    bad = [t for t in a.tasks if t not in TASKS]
    if bad:
        ap.error(f"unknown task(s) {bad}; choose from {sorted(TASKS)}")
    OUT.mkdir(parents=True, exist_ok=True)
    rc = 0
    for name in a.tasks or list(TASKS):  # sequential: an ambiguous create stops everything
        task, schema = TASKS[name]
        out: RunOutcome = run_task(task, confirm_spend=a.confirm_spend, max_cost_usd=a.max_cost, output_schema=schema)
        (OUT / f"{name}.json").write_text(json.dumps(out.to_dict(), indent=2, default=str))
        print(f"== {name}: status={out.status} ok={out.ok} cost=${out.cost_usd} problems={out.problems}")
        rc |= 0 if out.ok else 1
    return rc


if __name__ == "__main__":
    sys.exit(main())
