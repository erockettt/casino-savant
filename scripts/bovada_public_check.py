"""Read-only check of Bovada's PUBLIC rules and terms pages via Browser Use.

Never logs in, signs up, opens a cashier, or interacts with a game. Saves raw
agent output to research/bovada/ for human review; nothing is auto-applied to
profiles. Requires BROWSER_USE_API_KEY (or a proxy that injects it).
"""
import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from browser_use_sdk.v4 import BrowserUse

OUT = Path(__file__).resolve().parents[1] / "research" / "bovada"
GUARD = (" Strict rules: do NOT log in, sign up, create an account, enter any personal data, open a cashier, "
         "or start or click into any real-money game. Only read publicly visible help, rules and legal pages "
         "(bovada.lv and its help center). For every fact, give the exact page URL and quote the sentence it "
         "came from. If a fact is not stated on a public page, write NOT FOUND - never guess or use other sites.")

TASKS = {
    "game_rules": (
        "On bovada.lv's public help center / casino game-rules pages, find the published rules for: "
        "(1) each blackjack game (RNG and live dealer): number of decks, dealer hits or stands on soft 17, "
        "blackjack payout, whether the dealer peeks or there is no hole card, doubling rules, double after split, "
        "number of splits / resplitting, split aces rules, surrender, insurance, and for live dealer the shuffle "
        "method or cut-card penetration; (2) baccarat: decks, commission, tie payout, pair payouts, and any "
        "no-commission variant; (3) roulette: which wheels are offered (single zero, double zero) and whether "
        "La Partage or En Prison applies. Return JSON with keys blackjack (list of games), baccarat, roulette, "
        "and sources." + GUARD
    ),
    "terms": (
        "On bovada.lv's public Terms and Conditions / Terms of Use / casino rules pages, find every clause about: "
        "third-party software, bots, programs, devices or tools used while playing; advantage play or card "
        "counting; collusion; and what happens to accounts or winnings that break these rules. Quote each clause "
        "verbatim (short quotes) with its URL and section heading. Also report the date or version of the terms "
        "if shown. Return JSON with keys clauses (list of {topic, quote, url, section}), terms_version, sources." + GUARD
    ),
}


def run(name_task):
    name, task = name_task
    t0 = time.time()
    with BrowserUse() as client:
        r = client.runs.create(task, max_cost_usd=2.0)
        res = client.runs.wait_for_completion(r.id)
    data = {"task": name, "run_id": r.id, "seconds": round(time.time() - t0), "status": getattr(res, "status", None),
            "result": getattr(res, "result", None)}
    (OUT / f"{name}.json").write_text(json.dumps(data, indent=2, default=str))
    return name, data


if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    names = sys.argv[1:] or list(TASKS)
    with ThreadPoolExecutor(len(names)) as ex:
        for name, data in ex.map(run, [(n, TASKS[n]) for n in names]):
            print(f"== {name} ({data['status']}, {data['seconds']}s)\n{str(data['result'])[:4000]}\n", flush=True)
