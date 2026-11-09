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
    confirmed_fields: list[str] = field(default_factory=list)  # fields confirmed from a primary source

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
        if self.confirmed_fields:
            return (f"{self.venue} – {self.title}: PARTLY CONFIRMED from {self.venue}'s public pages "
                    f"({', '.join(self.confirmed_fields)}); other rules UNVERIFIED. Check the in-game rules screen.")
        return (f"{self.venue} – {self.title}: rules UNVERIFIED template. Check the table's rules screen and "
                "correct any field before relying on the numbers.")

    def to_dict(self) -> dict:
        return self.__dict__.copy()


HUB = "https://hub.bovada.lv/casino"
BOVADA_CHECKED = "2026-11-09"
SRC_TYPES = f"{HUB}/blackjack/types-of-online-blackjack-games-to-play/"
SRC_SINGLE = f"{HUB}/blackjack/a-guide-to-double-down-in-single-deck-blackjack/"
SRC_CLASSIC_VS_NEW = f"{HUB}/slots/classic-blackjack-vs-the-new-blackjack/"
SRC_PERFECT_PAIRS = f"{HUB}/blackjack/an-introduction-to-perfect-pairs-blackjack/"
SRC_ROULETTE = f"{HUB}/roulette/you-need-to-try-these-roulette-strategies/"
SRC_LIVE = f"{HUB}/table-games/live-dealer-games-what-you-need-to-know/"
SRC_SUPER6 = f"{HUB}/table-games/live-dealer-super-6-guide/"
SRC_TOS = "https://www.bovada.lv/terms-of-service"

TOS_NOTE = (
    "Bovada Terms of Service s.6.3 (updated Jan 3, 2024) prohibit 'external player assistance programs' designed to "
    "give an unfair advantage, explicitly including computer software, with account closure and voided winnings as "
    "the penalty. Card counting is not mentioned. Using this tool DURING real-money play could fall under s.6.3; "
    "use it for study, drills and post-session review. It places no bets and never touches the site."
)


def _bovada_templates() -> list[VenueProfile]:
    """Bovada profiles. Fields marked confirmed were read on Bovada's public help pages
    (agent-extracted, then re-checked against the live pages on BOVADA_CHECKED).
    Unconfirmed fields keep conventional defaults, so profiles stay verified=False."""
    rng_note = "Bovada says its RNG blackjack decks are shuffled after every hand, so card counting carries no information."
    return [
        VenueProfile(
            id="bovada-bj-rng-classic",
            venue="Bovada", game="blackjack", title="Classic Blackjack (RNG, 6 decks)",
            delivery="rng",
            rules=BlackjackRules(decks=6, dealer_hits_soft_17=True, blackjack_payout=1.5, dealer_peeks=True,
                                 double_on="any", double_after_split=True, max_split_hands=3,
                                 resplit_aces=False, hit_split_aces=False, surrender="late",
                                 shuffle="per_hand").to_dict(),
            confirmed_fields=["decks", "blackjack_payout", "shuffle", "dealer_hits_soft_17", "max_split_hands", "surrender offered"],
            source=f"Bovada public pages, checked {BOVADA_CHECKED}: {SRC_TYPES} ; {SRC_PERFECT_PAIRS}",
            notes=[rng_note,
                   "Confirmed: 6 decks, 3:2, shuffled every hand, dealer hits soft 17, split up to three hands, surrender allowed.",
                   "NOT published: dealer peek, doubling restrictions, double after split, split-ace rules, insurance, "
                   "surrender timing (modelled as late surrender). Check the in-game rules screen for these.",
                   TOS_NOTE],
        ),
        VenueProfile(
            id="bovada-bj-rng-single-deck",
            venue="Bovada", game="blackjack", title="Single Deck Blackjack (RNG)",
            delivery="rng",
            rules=BlackjackRules(decks=1, dealer_hits_soft_17=True, blackjack_payout=1.5, dealer_peeks=True,
                                 double_on="any", double_after_split=True, max_split_hands=2,
                                 hit_split_aces=False, surrender="none", shuffle="per_hand").to_dict(),
            confirmed_fields=["decks", "dealer_hits_soft_17", "double_on", "double_after_split", "hit_split_aces",
                              "blackjack_payout", "shuffle", "max_split_hands (New format: 2; Classic format: 3)"],
            source=f"Bovada public pages, checked {BOVADA_CHECKED}: {SRC_SINGLE} ; {SRC_CLASSIC_VS_NEW} ; {SRC_TYPES}",
            notes=[rng_note,
                   "Confirmed: 1 deck, dealer hits soft 17, double any two cards, double after split, split aces get one "
                   "card, 3:2, split to two hands in the New format (three in the Classic format: set max_split_hands=3).",
                   "NOT published: dealer peek, surrender, insurance.",
                   TOS_NOTE],
        ),
        VenueProfile(
            id="bovada-bj-rng-double-deck",
            venue="Bovada", game="blackjack", title="Double Deck Blackjack (RNG)",
            delivery="rng",
            rules=BlackjackRules(decks=2, dealer_hits_soft_17=True, blackjack_payout=1.5, dealer_peeks=True,
                                 double_on="any", double_after_split=True, max_split_hands=2,
                                 surrender="none", shuffle="per_hand").to_dict(),
            confirmed_fields=["decks", "max_split_hands (split once)"],
            source=f"Bovada public pages, checked {BOVADA_CHECKED}: {SRC_TYPES}",
            notes=["Confirmed: 2 decks, split once per round. Bovada says it shares Single Deck's rules, which would "
                   "mean H17, double any two, DAS; that inference is not a direct statement for this game.",
                   "NOT published: blackjack payout, dealer peek, surrender, insurance, shuffle frequency "
                   "(assumed every hand like Bovada's other RNG blackjack).",
                   TOS_NOTE],
        ),
        VenueProfile(
            id="bovada-bj-live",
            venue="Bovada", game="blackjack", title="Live Dealer Blackjack – template",
            delivery="live_dealer",
            rules=BlackjackRules(decks=8, dealer_hits_soft_17=False, blackjack_payout=1.5, dealer_peeks=False,
                                 enhc_lose_doubles_and_splits=False, double_on="any", double_after_split=True,
                                 max_split_hands=2, surrender="none", shuffle="shoe", penetration=0.5).to_dict(),
            source=f"no rules published; searched {BOVADA_CHECKED}: {SRC_LIVE}",
            notes=[
                "Bovada's public pages give NO live-blackjack rules (decks, soft 17, payout, peek, penetration all not found). "
                "Everything here is a generic live-studio template; read the table's info panel.",
                "If the studio uses a continuous shuffler, set shuffle='csm' — counting is then meaningless.",
                TOS_NOTE,
            ],
        ),
        VenueProfile(
            id="bovada-baccarat",
            venue="Bovada", game="baccarat", title="Baccarat – template",
            delivery="unknown",
            rules={"decks": 8, "variant": "commission", "commission": 0.05, "tie_pays": 8.0, "pair_pays": 11.0},
            source=f"standard-baccarat rules not published; searched {BOVADA_CHECKED}",
            notes=["Bovada's public pages give no standard-baccarat rules. Its live 'Super 6' game is documented "
                   f"(6 decks, 5% banker commission, tie 8:1, pairs 11:1: {SRC_SUPER6}) but Bovada calls it a "
                   "different game, so it is not modelled here."],
        ),
        VenueProfile(
            id="bovada-roulette-american",
            venue="Bovada", game="roulette", title="American Roulette (0, 00)",
            delivery="rng",
            rules={"wheel": "american", "la_partage": False, "en_prison": False},
            verified=True, confirmed_fields=["wheel"],
            source=f"Bovada public pages, checked {BOVADA_CHECKED}: {SRC_ROULETTE}",
            notes=["Confirmed: American wheel has 38 slots with 0 and 00. Also offered live. "
                   "No special half-back rules apply to double-zero wheels."],
        ),
        VenueProfile(
            id="bovada-roulette-european",
            venue="Bovada", game="roulette", title="European Roulette (single 0)",
            delivery="rng",
            rules={"wheel": "european", "la_partage": False, "en_prison": False},
            confirmed_fields=["wheel"],
            source=f"Bovada public pages, checked {BOVADA_CHECKED}: {SRC_ROULETTE}",
            notes=["Confirmed: 37 slots, single zero (also Flash Roulette). La Partage / En Prison: NOT published; "
                   "modelled as absent (the conservative assumption). Check the game's rules screen."],
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
