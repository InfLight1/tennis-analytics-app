# Append to config.py (after PLAYER_IDENTITY_MIN_FRAMES):

# Cross-check between player_identity.py's frame-count near/far pick and
# detect_hits()'s own player attribution for the same rally (PROJECT.md
# 2026-09-14/16 design decision). A rally's top-2 hit-attributed tracks
# must cover at least this fraction of that rally's attributed hits to be
# trusted as "the two real players" -- below it, attribution is spread
# across too many competing tracks (a messy/merged rally window) to
# resolve reliably. VALIDATED against real data: every normal real rally
# has 100% dominance; the one confirmed disagreement case (rally 22, a
# ~193s merged window with 9 distinct attributed tracks) has only 39%.
PLAYER_IDENTITY_HIT_ATTRIBUTION_DOMINANCE_THRESHOLD = 0.6
