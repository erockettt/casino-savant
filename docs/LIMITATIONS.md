# Known limitations and unresolved questions

1. **Split EV is approximate.** Card removal between sibling split hands is ignored, and resplits use a
   constant-probability branching model. Outputs mark SPLIT as `exact: false`, and narrow margins show a warning.
2. **No early surrender, no 5-card Charlie, no side bets in blackjack** (Perfect Pairs, 21+3, etc.).
3. **Simulator strategy is total-dependent**, generated from the infinite-deck solver. The index subset is
   10 plays plus insurance, not the full set. It is a benchmark, not a playing recommendation.
4. **Indices (Illustrious 18 / Fab 4) are taken from the literature**, not re-derived. With a full tracked
   composition the CD solver supersedes them.
5. **Vision is a prototype interface only.** No recogniser is trained or validated. Screenshots need manual card entry.
6. **Bovada profiles are unverified templates** (see BOVADA.md). Every Bovada output shows an UNVERIFIED banner.
7. **Live play:** using any assistance tool during play may breach a venue's or site's terms. The software
   automates nothing and connects to no casino.
8. **Performance:** CD analyses of small pairs (e.g. 2,2 or 3,3) take about 1 s cold, then hit the cache. A 1-deck
   shoe with deep removal is the worst case.
9. **Roulette bias module:** only the research question (Q4) is specified; no estimator is implemented yet.
10. **Baccarat pair bets** assume ten-valued ranks are evenly split between T/J/Q/K in the remaining shoe.
