"""
report.py
Day 4 (no-footage) deliverable, pulled forward from the original Day 7 plan
(PROJECT.md Day 7: "Build report generator..."). Consumes match_stats.py's
report dict and formats it into the single structured per-video output the
MVP's Definition of Done requires. Exercised by generate_synthetic_data.py's
smoke test in the meantime.

Output format was still an open question in PROJECT.md §10 ("JSON, CSV, or
both?") -- this skeleton produces both: a machine-readable JSON (all stats,
nested structures preserved) and a short human-readable text summary
(coaching-style recommendations section), since the MVP's Definition of
Done mentions both "structured output" and "basic improvement
recommendations." Simplify to one format once real output is actually
being handed to a user and that open question gets resolved.

DAY 5 UPDATE -- recommendations are no longer a placeholder.
Previously this section just printed a static "[placeholder]" string
because match_stats.py alone had no winner/error classification to power
real recommendations. Now that rally_outcomes.py + prioritization.py exist
and carry real point-loss data (PROJECT.md Day 5), this module:
  1. Builds an outcomes_report (rally_outcomes.py) alongside the existing
     stats_report (match_stats.py) -- both are required inputs to
     prioritization.build_priority_table().
  2. Runs build_priority_table() to get a ranked, cross-player pattern
     table with real point_loss_count values.
  3. Converts that flat table into a PER-PLAYER shortlist via
     build_recommendations() -- see that function's docstring for why this
     isn't just "take the global top N."
  4. Renders the shortlist into both the JSON output (machine-readable,
     full pattern detail) and the text summary (headline + reason per
     pattern, grouped under each player).
Internal QA notes (unknown_position_rate, ambiguous_rate -- both flagged
"[internal QA only]" by prioritization.py, per PROJECT.md §2 "not surfaced
to the player") are kept in their own DATA QUALITY section, never folded
into RECOMMENDATIONS -- they're pipeline health signals, not coaching
findings, and shouldn't read as one.

JSON SHAPE CHANGE (Day 5): previously the JSON was just match_stats.py's
raw report dict, flattened straight to the file. It's now wrapped:
    {"stats": <match_stats.py's report dict, unchanged>,
     "priority_patterns": <prioritization.py's full ranked table>,
     "recommendations": <per-player shortlist, same data as priority_patterns
                         but grouped/filtered -- what the text summary uses>,
     "data_quality_notes": <prioritization.py's internal QA notes>}
Nothing downstream consumes the old flat shape yet (report.py isn't wired
into main.py -- still a Day 7 task per PROJECT.md), so this is safe to
restructure now rather than bolt new keys onto the old shape.

ENCODING FIX (2026-09-20): both output files were opened with plain
open(path, "w"), which defaults to the platform's locale encoding -- on
Windows that's typically cp1252, not UTF-8. Confirmed on real output: the
em dashes (—) baked into several reason strings (error_location,
pressure_moments, etc.) were silently mangled into "?" replacement
characters in match_report.txt. Fixed by passing encoding="utf-8"
explicitly on both writes -- json.dump's own output is unaffected (it
already escapes non-ASCII by default), but the underlying file handle
still needs a correct encoding to avoid the same failure on any other
non-ASCII content written through it in the future.
"""

import json
from pathlib import Path

import numpy as np
import pandas as pd

import config
import match_stats
import rally_outcomes
import prioritization


# ── Editable top-of-file variables ─────────────────────────────────────────
# config.py doesn't have report paths yet -- falls back to CODE_DIR if not
# added. Add REPORT_JSON / REPORT_SUMMARY to config.py alongside the other
# pipeline-artifact paths (EVENTS_CSV, METRICS_CSV, etc.) if you want these
# centralized instead.
REPORT_JSON_PATH = getattr(config, "REPORT_JSON", config.CODE_DIR / "match_report.json")
REPORT_SUMMARY_PATH = getattr(config, "REPORT_SUMMARY", config.CODE_DIR / "match_report.txt")

# How many patterns to surface per player. Not a global top-N -- applied
# PER PLAYER (see build_recommendations docstring), so one player's noisy
# error patterns can't crowd a second player's single real signal off the
# list. ESTIMATED, unvalidated -- a coach-facing UI test would tell you
# whether 3 is the right density; this is a reasonable starting guess.
TOP_N_RECOMMENDATIONS_PER_PLAYER = 3

# A pattern must clear this combined_score (0-1, from prioritization.py's
# min-max normalized frequency + point-loss blend) to be surfaced at all.
# Exists because "ranked #1" and "worth mentioning" aren't the same thing:
# in a clean or thin-data session, the top-ranked pattern might still be a
# combined_score of 0.05, which shouldn't read as a genuine finding just
# because nothing else scored higher. ESTIMATED, unvalidated -- needs real
# match data + coach feedback to calibrate for real, same caveat as every
# other ESTIMATED threshold in this codebase.
MIN_RECOMMENDATION_SCORE = 0.15

# Coach-facing section headers per prioritization.py category. Kept
# separate from the category's internal slug (e.g. "zone_error_rate") so
# the text report reads like a coaching note, not a variable name.
CATEGORY_HEADLINES = {
    "error_location": "Error tendency",
    "rally_accuracy": "Overall shot consistency",
    "pressure_moments": "Points lost under pressure",
    "rally_length": "Rally-length pattern",
    "zone_error_rate": "Where errors originate",
    "shot_placement": "Shot placement tendency",
    "court_coverage": "Court coverage gap",
    "coverage_point_loss": "Coverage gap costing points",
    "consistency_proxy": "Consistency signal (proxy -- no outcomes data)",
}


def _headline_for(category):
    return CATEGORY_HEADLINES.get(category, category.replace("_", " ").title())


def _df_to_records(obj):
    """Recursively converts DataFrames inside the report dict to
    JSON-serializable lists of records, and numpy scalars to native Python
    types; leaves everything else as-is."""
    if isinstance(obj, pd.DataFrame):
        return obj.to_dict(orient="records")
    if isinstance(obj, dict):
        return {k: _df_to_records(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_df_to_records(v) for v in obj]
    if isinstance(obj, np.floating):
        return float(obj)
    if isinstance(obj, np.integer):
        return int(obj)
    return obj


# ---------------------------------------------------------------------------
# Recommendations: flat ranked table -> per-player coaching shortlist
# ---------------------------------------------------------------------------

def build_recommendations(priority_df, known_players=None,
                           top_n=TOP_N_RECOMMENDATIONS_PER_PLAYER,
                           min_score=MIN_RECOMMENDATION_SCORE):
    """
    Turns prioritization.py's flat, cross-player ranked pattern table into
    a per-player shortlist of coaching-relevant observations.

    WHY NOT JUST "TAKE THE GLOBAL TOP N": prioritization.py's table is
    ranked across BOTH players together. Taking the global top N naively
    would let one player's crowded error patterns (e.g. 5 different
    zone_error_rate rows, all real, all costing points) push a second
    player's single most important signal off the list entirely, even if
    that second player's issue is just as real. Grouping by player first,
    then applying top_n within each player's own patterns, guarantees
    every player with qualifying data gets a shortlist -- not just
    whichever player happened to generate the noisiest table.

    WHY A SCORE FLOOR ON TOP OF TOP N: "ranked #1 for this player" isn't
    the same as "worth a coaching conversation." In a clean session (or a
    thin synthetic one), a player's best-ranked pattern might still have a
    combined_score of 0.05 -- min_score keeps a genuinely unremarkable
    session from being forced to produce 3 recommendations anyway.

    WHY "NOTHING TO REPORT" IS EXPLICIT, NOT OMITTED: known_players (pass
    match_stats.py's consistency table's player list) ensures a player who
    generated zero qualifying patterns still gets an entry -- with an
    empty list -- rather than silently vanishing from the report. A clean
    session should read as "no notable patterns," a real and useful
    result, not look like a data-quality gap where the player is just
    missing.

    Returns: {player: [pattern_row_dict, ...]} for every player in
    known_players (plus any additional players priority_df mentions that
    weren't in known_players, as a safety net). Players with no qualifying
    patterns map to an empty list.
    """
    recs = {player: [] for player in (known_players or [])}

    if priority_df is None or len(priority_df) == 0:
        return recs

    for player, group in priority_df.groupby("player"):
        qualifying = (
            group[group["combined_score"] >= min_score]
            .sort_values("combined_score", ascending=False)
            .head(top_n)
        )
        recs[player] = qualifying.to_dict("records")

    return recs


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------

def generate_report(events_csv, player_csv=None,
                     json_path=REPORT_JSON_PATH, summary_path=REPORT_SUMMARY_PATH):
    """
    Orchestration entry point -- mirrors match_stats.run_statistics()'s call
    shape so main.py can wire this in as a Step 8 the same way Step 7 calls
    match_stats. Not yet added to main.py itself (that's a Day 7 task once
    this is validated against real data).

    Now builds THREE report dicts instead of one: match_stats.py's
    stats_report (as before), rally_outcomes.py's outcomes_report (new),
    and prioritization.py's ranked priority table (new) -- see module
    docstring for the resulting JSON shape change.
    """
    stats_report = match_stats.generate_stats_report(events_csv, player_csv=player_csv)
    outcomes_report = rally_outcomes.generate_outcomes_report(events_csv)
    priority_df, priority_notes = prioritization.build_priority_table(stats_report, outcomes_report)

    known_players = []
    if len(stats_report.get("consistency", [])) > 0:
        known_players = stats_report["consistency"]["player_side"].tolist()

    recommendations = build_recommendations(priority_df, known_players=known_players)

    full_report = {
        "stats": stats_report,
        "priority_patterns": priority_df,
        "recommendations": recommendations,
        "data_quality_notes": priority_notes,
    }

    Path(json_path).parent.mkdir(parents=True, exist_ok=True)
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(_df_to_records(full_report), f, indent=2, default=str)
    print(f"Saved {json_path}")

    with open(summary_path, "w", encoding="utf-8") as f:
        f.write(_build_summary_text(stats_report, recommendations, priority_notes))
    print(f"Saved {summary_path}")

    return full_report


def _build_summary_text(report, recommendations, data_quality_notes):
    """
    Builds a short human-readable summary. RALLY PATTERNS / CONSISTENCY /
    TACTICAL TENDENCIES sections are unchanged from the Day 4 skeleton --
    still descriptive, not prescriptive. RECOMMENDATIONS is the section
    that changed: real, per-player, ranked findings from prioritization.py
    instead of a static placeholder.
    """
    lines = ["TENNIS MATCH ANALYSIS -- SUMMARY REPORT", "=" * 40, ""]

    rally_summary = report["rally_lengths"]["summary"]
    if rally_summary:
        lines.append("RALLY PATTERNS")
        lines.append(f"  Total rallies: {rally_summary.get('n_rallies', 'N/A')}")
        avg_shots = rally_summary.get("avg_shots_per_rally")
        lines.append(f"  Avg shots/rally: {avg_shots:.1f}" if avg_shots is not None else "  Avg shots/rally: N/A")
        lines.append(f"  Longest rally (shots): {rally_summary.get('max_shots_in_rally', 'N/A')}")
        avg_dur = rally_summary.get("avg_rally_duration_sec")
        lines.append(f"  Avg rally duration: {avg_dur:.1f}s" if avg_dur is not None else "  Avg rally duration: N/A")
        lines.append("")

    consistency = report["consistency"]
    if len(consistency) > 0:
        lines.append("CONSISTENCY (per player)")
        for _, row in consistency.iterrows():
            lines.append(
                f"  {row['player_side']}: {row['total_hits']} hits across "
                f"{row['rallies_participated']} rallies "
                f"({row['avg_hits_per_rally']:.1f} avg/rally)"
            )
        lines.append("")

    tendencies = report["tactical_tendencies"]
    if len(tendencies) > 0:
        lines.append("TACTICAL TENDENCIES (top zone per player)")
        top_per_player = (
            tendencies.sort_values("pct_of_shots", ascending=False)
            .groupby("player_side")
            .first()
        )
        for player_side, row in top_per_player.iterrows():
            lines.append(f"  {player_side}: favors {row['zone']} ({row['pct_of_shots'] * 100:.0f}% of shots)")
        lines.append("")

    if report.get("court_coverage") is None:
        lines.append(
            "Court coverage: not available (requires player table_x/table_y from "
            "the transform stage -- see PROJECT.md Day 6 note)"
        )
        lines.append("")

    # ── RECOMMENDATIONS (Day 5: real, per-player, ranked) ───────────────
    lines.append("RECOMMENDATIONS")
    lines.append(
        "  Prioritized by frequency + point-loss impact. This flags what's "
        "happening and how much it's costing -- deciding what to change "
        "technically is a conversation for the player's coach, not this report."
    )
    lines.append("")

    if not recommendations:
        lines.append(
            "  No player data available to generate recommendations from "
            "(no consistency data -- check upstream event detection)."
        )
    else:
        for player, patterns in recommendations.items():
            lines.append(f"  {player}:")
            if not patterns:
                lines.append(
                    "    No qualifying patterns this session -- reads as a clean "
                    "session, not a data gap."
                )
            else:
                for i, pattern in enumerate(patterns, start=1):
                    headline = _headline_for(pattern["category"])
                    lines.append(f"    {i}. [{headline}] {pattern['reason']}")
            lines.append("")

    # ── DATA QUALITY (internal-only, kept separate from recommendations) ─
    if data_quality_notes:
        lines.append("DATA QUALITY NOTES (internal -- not a coaching finding)")
        for note in data_quality_notes:
            lines.append(f"  - {note}")
        lines.append("")

    return "\n".join(lines)


if __name__ == "__main__":
    # NOTE: will not produce meaningful output until real rally_events.csv
    # exists (blocked on footage, same as analysis.py/match_stats.py). Run
    # generate_synthetic_data.py first to exercise this against synthetic
    # data instead.
    generate_report(config.EVENTS_CSV, player_csv=None)
