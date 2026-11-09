"""Venue rule profiles.

A profile bundles game rules for a venue together with *provenance*: where
each rule came from and whether the user has verified it on the actual table.
The solver always uses the profile's rules, but every analysis reports the
verification status so an unconfirmed assumption is never presented as fact.

Profiles live in JSON files under profiles/ and can be created/edited by the user
through the API or by hand.  Bovada presets ship as TEMPLATES: Bovada does not
publish a single authoritative rules page we could verify, and its rules differ
by game title and can change, so every Bovada rule ships with
verified=false.  Confirm each value against the in-game "rules"/"help" screen
of the exact table you are playing, then mark the profile verified.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from .blackjack.rules import BlackjackRules
from .games.baccarat import BaccaratRules
from .games.roulette import RouletteRules

PROFILE_DIR = Path(__file__).resolve().parent.parent / "profiles"


@dataclass
class VenueProfile:
    id: str
    venue: str
    game: str                 # 'blackjack' | 'baccarat' | 'roulette'
    title: str
    rules: dict
    verified: bool = False
    source: str = "user-entered"
    delivery: str = "unknown"  # 'rng' | 'live_dealer' | 'land' | 'unknown'
    notes: list[str] = field(default_factory=list)

    def build_rules(self):
        if self.game == "blackjack":
            return BlackjackRules.from_dict(self.rules)
        if self.game == "baccarat":
            return BaccaratRules(**{k: v for k, v in self.rules.items() if k != "notes"})
        if self.game == "roulette":
            return RouletteRules(**self.rules)
        raise ValueError(f"unknown game {self.game}")

    def status_banner(self) -> str:
        if self.verified:
            return f"{self.venue} – {self.title}: rules VERIFIED ({self.source})."
        return (f"{self.venue} – {self.title}: rules UNVERIFIED template. Check the table's rules screen and "
                "correct any field before relying on the numbers.")

    def to_dict(self) -> dict:
        return self.__dict__.copy()


def _bovada_templates() -> list[VenueProfile]:
    common_notes = [
        "Template only: values are typical of RNG online blackjack and were not confirmed against Bovada's live rule screens.",
        "RNG tables shuffle before every hand, so card counting carries no information there; the tracker is disabled for shuffle='per_hand'.",
        "Check Bovada's terms of service for any restriction on third-party software or assistance during play. "
        "This tool is designed for manual entry, study and post-session review; it places no bets and does not interact with the site.",
    ]
    return [
        VenueProfile(
            id="bovada-bj-rng-classic",
            venue="Bovada", game="blackjack", title="Blackjack (RNG) – template",
            delivery="rng",
            rules=BlackjackRules(decks=6, dealer_hits_soft_17=False, blackjack_payout=1.5, dealer_peeks=True,
                                 double_on="any", double_after_split=True, max_split_hands=2,
                                 resplit_aces=False, hit_split_aces=False, surrender="none",
                                 shuffle="per_hand").to_dict(),
            notes=common_notes,
        ),
        VenueProfile(
            id="bovada-bj-rng-single-deck",
            venue="Bovada", game="blackjack", title="Single Deck Blackjack (RNG) – template",
            delivery="rng",
            rules=BlackjackRules(decks=1, dealer_hits_soft_17=True, blackjack_payout=1.5, dealer_peeks=True,
                                 double_on="any", double_after_split=True, max_split_hands=2,
                                 surrender="none", shuffle="per_hand").to_dict(),
            notes=common_notes + [
                "An unverified secondary source describes a Bovada single-deck game as H17 with double on any two "
                "cards and after splits; confirm on the game screen (some online single-deck games pay 6:5).",
            ],
        ),
        VenueProfile(
            id="bovada-bj-live",
            venue="Bovada", game="blackjack", title="Live Dealer Blackjack – template",
            delivery="live_dealer",
            rules=BlackjackRules(decks=8, dealer_hits_soft_17=False, blackjack_payout=1.5, dealer_peeks=False,
                                 enhc_lose_doubles_and_splits=False, double_on="any", double_after_split=True,
                                 max_split_hands=2, surrender="none", shuffle="shoe", penetration=0.5).to_dict(),
            notes=[
                "Template only: many live-dealer studios use 8-deck shoes, no hole card, and a cut card near half "
                "the shoe; confirm deck count, peek rule, payout and penetration on the table's info panel.",
                "If the studio uses a continuous shuffler, set shuffle='csm' — counting is then meaningless.",
                common_notes[2],
            ],
        ),
        VenueProfile(
            id="bovada-baccarat",
            venue="Bovada", game="baccarat", title="Baccarat – template",
            delivery="unknown",
            rules={"decks": 8, "variant": "commission", "commission": 0.05, "tie_pays": 8.0, "pair_pays": 11.0},
            notes=["Template only: confirm deck count, commission and tie/pair payouts."],
        ),
        VenueProfile(
            id="bovada-roulette-american",
            venue="Bovada", game="roulette", title="American Roulette – template",
            delivery="rng",
            rules={"wheel": "american", "la_partage": False, "en_prison": False},
            notes=["Template only: confirm wheel type (single vs double zero) in the game."],
        ),
        VenueProfile(
            id="bovada-roulette-european",
            venue="Bovada", game="roulette", title="European Roulette – template",
            delivery="rng",
            rules={"wheel": "european", "la_partage": False, "en_prison": False},
            notes=["Template only: confirm wheel type and whether La Partage/En Prison applies."],
        ),
    ]


def _builtin() -> list[VenueProfile]:
    return [
        VenueProfile(id="reference-6d-s17", venue="Reference", game="blackjack", title="6D S17 DAS LS 3:2 (benchmark)",
                     rules=BlackjackRules().to_dict(), verified=True, source="textbook benchmark rules", delivery="land"),
        VenueProfile(id="reference-8d-baccarat", venue="Reference", game="baccarat", title="8-deck Punto Banco 5%",
                     rules={"decks": 8, "variant": "commission", "commission": 0.05, "tie_pays": 8.0, "pair_pays": 11.0},
                     verified=True, source="textbook benchmark rules", delivery="land"),
    ] + _bovada_templates()


class ProfileStore:
    def __init__(self, directory: Path = PROFILE_DIR):
        self.dir = directory
        self.dir.mkdir(parents=True, exist_ok=True)

    def all(self) -> dict[str, VenueProfile]:
        profiles = {p.id: p for p in _builtin()}
        for f in sorted(self.dir.glob("*.json")):
            d = json.loads(f.read_text())
            profiles[d["id"]] = VenueProfile(**d)  # user files override templates
        return profiles

    def get(self, pid: str) -> VenueProfile:
        ps = self.all()
        if pid not in ps:
            raise KeyError(f"unknown profile {pid!r}")
        return ps[pid]

    def save(self, profile: VenueProfile) -> None:
        profile.build_rules()  # validates
        (self.dir / f"{profile.id}.json").write_text(json.dumps(profile.to_dict(), indent=2))
