"""
prioritization.py

Intelligence layer, Phase 1: pattern prioritization.
"""

import pandas as pd
import numpy as np

import config

# ---- Editable config (no CLI args, per project convention) ----
FREQUENCY_WEIGHT = 0.5
POINT_LOSS_WEIGHT = 0.5

PLACEMENT_CONCENTRATION_THRESHOLD_PCT = 35.0

SHORT_RALLY_MAX_HITS = config.RALLY_LENGTH_SHORT_MAX_HITS
LONG_RALLY_MIN_HITS = config.RALLY_LENGTH_LONG_MIN_HITS

COVERAGE_GAP_RELATIVE_THRESHOLD = 0.5

CONSISTENCY_PROXY_GAP_THRESHOLD_PCT = 15.0


class Pattern:
    """One candidate pattern awaiting ranking."""

    def __init__(self, player, category, label, frequency_count,
                 frequency_total, point_loss_count, reason):
        self.player = player
        self.category = category
        self.label = label
        self.frequency_count = frequency_count
        self.frequency_total = max(frequency_total, 1)  # avoid /0
        self.point_loss_count = point_loss_count
        self.reason = reason

    @property
    def frequency_pct(self):
        return 100.0 * self.frequency_count / self.frequency_total


def extract_error_patterns(outcomes_report):
    patterns = []
    error_loc = outcomes_report.get("error_location")
    points_won = outcomes_report.get("points_won")
    if error_loc is None or len(error_loc) == 0:
        return patterns

    confirmed = error_loc[error_loc["error_type"] != "unknown_outcome"]
    if len(confirmed) == 0:
        return patterns

    loss_lookup = {}
    if points_won is not None and len(points_won) > 0:
        loss_lookup = dict(zip(points_won["player_side"], points_won["points_lost"]))

    for player, group in confirmed.groupby("player_side"):
        total_errors = group["count"].sum()
        for _, row in group.iterrows():
            count = row["count"]
            err_type = row["error_type"]
            player_total_losses = loss_lookup.get(player)
            pct_of_losses = (
                f", {100*count/player_total_losses:.0f}% of their total lost points"
                if player_total_losses else ""
            )
            patterns.append(Pattern(
                player=player,
                category="error_location",
                label=f"{err_type}_errors",
                frequency_count=count,
                frequency_total=total_errors,
                point_loss_count=count,
                reason=(f"{count} of {total_errors} errors ({100*count/total_errors:.0f}%) "
                        f"are {err_type} errors{pct_of_losses}."),
            ))
    return patterns


def extract_rally_accuracy_patterns(outcomes_report):
    patterns = []
    accuracy = outcomes_report.get("rally_accuracy")
    if accuracy is None or len(accuracy) == 0:
        return patterns

    for _, row in accuracy.iterrows():
        shots_out = row["shots_out"]
        if shots_out == 0:
            continue
        total_shots = row["shots_in"] + shots_out
        patterns.append(Pattern(
            player=row["player_side"],
            category="rally_accuracy",
            label="overall_error_rate",
            frequency_count=shots_out,
            frequency_total=total_shots,
            point_loss_count=shots_out,
            reason=(f"{row['rally_accuracy_pct']:.0f}% shot accuracy "
                    f"({shots_out} of {total_shots} tracked shots went out) — "
                    f"directly costing {shots_out} points."),
        ))
    return patterns


def extract_pressure_patterns(outcomes_report):
    patterns = []
    outcomes = outcomes_report.get("rally_outcomes")
    if outcomes is None or len(outcomes) == 0:
        return patterns

    pressure = outcomes[outcomes["reason"] == "opponent_no_return"]
    if len(pressure) == 0:
        return patterns

    total_resolved = outcomes[outcomes["winner"].notna()]
    for loser, group in pressure.groupby("loser"):
        count = len(group)
        player_total = len(total_resolved[total_resolved["loser"] == loser])
        patterns.append(Pattern(
            player=loser,
            category="pressure_moments",
            label="unreturned_shots_conceded",
            frequency_count=count,
            frequency_total=max(player_total, 1),
            point_loss_count=count,
            reason=(f"Lost {count} points to shots they didn't get back in play — "
                    f"not a self-inflicted error, but still costing points."),
        ))
    return patterns


def extract_rally_length_loss_patterns(stats_report, outcomes_report):
    patterns = []
    rally_lengths = stats_report.get("rally_lengths")
    outcomes = outcomes_report.get("rally_outcomes")
    if not rally_lengths or len(rally_lengths.get("per_rally", [])) == 0:
        return patterns
    if outcomes is None or len(outcomes) == 0:
        return patterns

    per_rally = rally_lengths["per_rally"][["rally_id", "n_hits"]]
    resolved = outcomes[outcomes["loser"].notna()][["rally_id", "loser"]]
    merged = per_rally.merge(resolved, on="rally_id", how="inner")
    if len(merged) == 0:
        return patterns

    merged = merged.copy()
    merged["bucket"] = np.select(
        [merged["n_hits"] <= SHORT_RALLY_MAX_HITS, merged["n_hits"] >= LONG_RALLY_MIN_HITS],
        ["short", "long"], default="medium",
    )

    for (loser, bucket), group in merged.groupby(["loser", "bucket"]):
        if bucket == "medium":
            continue
        count = len(group)
        player_total_rallies = len(merged[merged["loser"] == loser])
        cutoff = SHORT_RALLY_MAX_HITS if bucket == "short" else LONG_RALLY_MIN_HITS
        qualifier = "or fewer" if bucket == "short" else "or more"
        patterns.append(Pattern(
            player=loser,
            category="rally_length",
            label=f"lost_{bucket}_rallies",
            frequency_count=count,
            frequency_total=player_total_rallies,
            point_loss_count=count,
            reason=(f"Lost {count} of their {player_total_rallies} rallies "
                    f"({100*count/player_total_rallies:.0f}%) in {bucket} rallies "
                    f"({cutoff} shots {qualifier})."),
        ))
    return patterns


def extract_zone_error_patterns(outcomes_report):
    import match_stats

    patterns = []
    per_shot = outcomes_report.get("per_shot_outcomes")
    if per_shot is None or len(per_shot) == 0:
        return patterns

    errors = per_shot[~per_shot["in_bounds"]].copy()
    if len(errors) == 0:
        return patterns

    errors["zone"] = errors.apply(
        lambda r: match_stats.get_zone(r["hit_table_x"], r["hit_table_y"]), axis=1
    )
    errors = errors.dropna(subset=["zone"])
    if len(errors) == 0:
        return patterns

    for player, group in errors.groupby("player_side"):
        total_player_errors = len(group)
        for zone, zone_group in group.groupby("zone"):
            count = len(zone_group)
            patterns.append(Pattern(
                player=player,
                category="zone_error_rate",
                label=f"errors_from_{zone}",
                frequency_count=count,
                frequency_total=total_player_errors,
                point_loss_count=count,
                reason=(f"{count} of {total_player_errors} errors ({100*count/total_player_errors:.0f}%) "
                        f"are hit from {zone} -- a specific zone this player errs from, not just "
                        f"a zone they hit from often."),
            ))
    return patterns


def _parse_track_id(player_side):
    if not isinstance(player_side, str) or not player_side.startswith("track_"):
        return None
    try:
        return int(player_side.split("_", 1)[1])
    except ValueError:
        return None


def _bin_grid_cell(table_x, table_y, court_w, court_h, rows, cols):
    if pd.isna(table_x) or pd.isna(table_y):
        return None
    col = int(np.clip(table_x / court_w * cols, 0, cols - 1))
    row = int(np.clip(table_y / court_h * rows, 0, rows - 1))
    return (row, col)


def extract_coverage_point_loss_patterns(stats_report, outcomes_report):
    import config as _config

    patterns = []
    coverage = stats_report.get("court_coverage")
    outcomes = outcomes_report.get("rally_outcomes")
    if coverage is None or len(coverage) == 0 or outcomes is None or len(outcomes) == 0:
        return patterns

    gap_cells = {}
    for track_id, group in coverage.groupby("track_id"):
        total_frames = group["frame_count"].sum()
        if total_frames == 0:
            continue
        n_occupied_cells = len(group)
        even_share_pct = 100.0 / n_occupied_cells
        gap_threshold_pct = even_share_pct * COVERAGE_GAP_RELATIVE_THRESHOLD
        cells = set()
        for _, row in group.iterrows():
            pct = 100.0 * row["frame_count"] / total_frames
            if pct < gap_threshold_pct:
                cells.add((row["row"], row["col"]))
        gap_cells[track_id] = cells

    lost = outcomes[outcomes["loser"].notna() & outcomes["final_table_x"].notna()].copy()
    if len(lost) == 0:
        return patterns

    lost["track_id"] = lost["loser"].apply(_parse_track_id)
    lost = lost.dropna(subset=["track_id"])
    if len(lost) == 0:
        return patterns

    lost["cell"] = lost.apply(
        lambda r: _bin_grid_cell(r["final_table_x"], r["final_table_y"],
                                  _config.TABLE_W, _config.TABLE_H,
                                  _config.COURT_GRID_ROWS, _config.COURT_GRID_COLS),
        axis=1,
    )

    for track_id, group in lost.groupby("track_id"):
        track_id = int(track_id)
        cells_here = gap_cells.get(track_id, set())
        if not cells_here:
            continue
        player_total_losses = len(group)
        for cell, count in group["cell"].value_counts().items():
            if cell not in cells_here:
                continue
            patterns.append(Pattern(
                player=f"track_{track_id}",
                category="coverage_point_loss",
                label=f"lost_points_r{cell[0]}_c{cell[1]}",
                frequency_count=int(count),
                frequency_total=player_total_losses,
                point_loss_count=int(count),
                reason=(f"track_{track_id} lost {count} points with the ball landing in grid cell "
                        f"(row {cell[0]}, col {cell[1]}) — a cell that's also a confirmed "
                        f"coverage gap for this player."),
            ))
    return patterns


def extract_placement_patterns(stats_report):
    patterns = []
    tendencies = stats_report.get("tactical_tendencies")
    if tendencies is None or len(tendencies) == 0:
        return patterns

    for _, row in tendencies.iterrows():
        pct = row["pct_of_shots"] * 100.0
        if pct < PLACEMENT_CONCENTRATION_THRESHOLD_PCT:
            continue
        patterns.append(Pattern(
            player=row["player_side"],
            category="shot_placement",
            label=f"concentration_{row['zone']}",
            frequency_count=row["count"],
            frequency_total=int(row["count"] / row["pct_of_shots"]) if row["pct_of_shots"] else row["count"],
            point_loss_count=0,
            reason=(f"{pct:.0f}% of shots go to {row['zone']} — a heavy zone concentration. "
                    f"Not yet cross-referenced against error/point-loss data."),
        ))
    return patterns


def extract_rally_length_patterns(stats_report):
    patterns = []
    rally_lengths = stats_report.get("rally_lengths")
    if not rally_lengths or len(rally_lengths.get("per_rally", [])) == 0:
        return patterns

    per_rally = rally_lengths["per_rally"]
    total = len(per_rally)

    short_count = (per_rally["n_hits"] <= SHORT_RALLY_MAX_HITS).sum()
    long_count = (per_rally["n_hits"] >= LONG_RALLY_MIN_HITS).sum()

    if short_count > 0:
        patterns.append(Pattern(
            player="both",
            category="rally_length",
            label="short_rallies",
            frequency_count=short_count,
            frequency_total=total,
            point_loss_count=0,
            reason=(f"{short_count} of {total} rallies ({100*short_count/total:.0f}%) end in "
                    f"{SHORT_RALLY_MAX_HITS} shots or fewer — a possible consistency signal. "
                    f"Not yet linked to who specifically loses these rallies."),
        ))
    if long_count > 0:
        patterns.append(Pattern(
            player="both",
            category="rally_length",
            label="long_rallies",
            frequency_count=long_count,
            frequency_total=total,
            point_loss_count=0,
            reason=(f"{long_count} of {total} rallies ({100*long_count/total:.0f}%) reach "
                    f"{LONG_RALLY_MIN_HITS}+ shots."),
        ))
    return patterns


def extract_coverage_patterns(stats_report):
    patterns = []
    coverage = stats_report.get("court_coverage")
    if coverage is None or len(coverage) == 0:
        return patterns

    for track_id, group in coverage.groupby("track_id"):
        total_frames = group["frame_count"].sum()
        if total_frames == 0:
            continue
        n_occupied_cells = len(group)
        even_share_pct = 100.0 / n_occupied_cells
        gap_threshold_pct = even_share_pct * COVERAGE_GAP_RELATIVE_THRESHOLD

        for _, row in group.iterrows():
            pct = 100.0 * row["frame_count"] / total_frames
            if pct >= gap_threshold_pct:
                continue
            patterns.append(Pattern(
                player=f"track_{track_id}",
                category="court_coverage",
                label=f"low_occupancy_r{row['row']}_c{row['col']}",
                frequency_count=int(row["frame_count"]),
                frequency_total=int(total_frames),
                point_loss_count=0,
                reason=(f"track_{track_id} spends only {pct:.1f}% of tracked frames in grid cell "
                        f"(row {row['row']}, col {row['col']}) — a positional gap. "
                        f"Point-loss link not available."),
            ))
    return patterns


def extract_consistency_proxy_patterns(stats_report):
    patterns = []
    consistency = stats_report.get("consistency")
    if consistency is None or len(consistency) < 2:
        return patterns

    sorted_df = consistency.sort_values("avg_hits_per_rally")
    lowest = sorted_df.iloc[0]
    highest = sorted_df.iloc[-1]
    if highest["avg_hits_per_rally"] == 0:
        return patterns

    gap_pct = 100.0 * (highest["avg_hits_per_rally"] - lowest["avg_hits_per_rally"]) / highest["avg_hits_per_rally"]
    if gap_pct < CONSISTENCY_PROXY_GAP_THRESHOLD_PCT:
        return patterns

    patterns.append(Pattern(
        player=lowest["player_side"],
        category="consistency_proxy",
        label="low_avg_hits_per_rally",
        frequency_count=int(lowest["rallies_participated"]),
        frequency_total=int(lowest["rallies_participated"] + highest["rallies_participated"]),
        point_loss_count=0,
        reason=(f"Averages {lowest['avg_hits_per_rally']:.1f} hits/rally vs. "
                f"{highest['avg_hits_per_rally']:.1f} for the opponent ({gap_pct:.0f}% lower) — "
                f"proxy signal only (no outcomes_report supplied)."),
    ))
    return patterns


def _normalize(values):
    if not values:
        return []
    lo, hi = min(values), max(values)
    if hi == lo:
        return [0.5 for _ in values]
    return [(v - lo) / (hi - lo) for v in values]


def build_priority_table(stats_report, outcomes_report=None):
    notes = []
    shot_placement = stats_report.get("shot_placement")
    if shot_placement and shot_placement.get("unknown_position_rate") is not None:
        rate = shot_placement["unknown_position_rate"]
        if not pd.isna(rate):
            notes.append(f"[internal QA only] unknown_position_rate: {rate*100:.1f}% of hits "
                          f"had no resolvable court position.")

    patterns = []
    patterns.extend(extract_placement_patterns(stats_report))
    patterns.extend(extract_coverage_patterns(stats_report))

    if outcomes_report is not None:
        patterns.extend(extract_error_patterns(outcomes_report))
        patterns.extend(extract_rally_accuracy_patterns(outcomes_report))
        patterns.extend(extract_pressure_patterns(outcomes_report))
        patterns.extend(extract_rally_length_loss_patterns(stats_report, outcomes_report))
        patterns.extend(extract_zone_error_patterns(outcomes_report))
        patterns.extend(extract_coverage_point_loss_patterns(stats_report, outcomes_report))

        ambiguous_rate = outcomes_report.get("ambiguous_rate")
        if ambiguous_rate is not None and not pd.isna(ambiguous_rate):
            notes.append(f"[internal QA only] ambiguous_rate: {ambiguous_rate*100:.1f}% of rallies "
                          f"had no determinable winner (tracking gaps or undetected bounces).")

        error_loc = outcomes_report.get("error_location")
        if error_loc is not None and len(error_loc) > 0:
            unknown_count = error_loc.loc[error_loc["error_type"] == "unknown_outcome", "count"].sum()
            total_count = error_loc["count"].sum()
            if total_count and unknown_count:
                notes.append(f"[internal QA only] unknown_outcome shots: {unknown_count} of "
                              f"{total_count} tracked shot outcomes ({100*unknown_count/total_count:.1f}%) "
                              f"couldn't be classified in/out -- excluded from error_location patterns.")
    else:
        patterns.extend(extract_rally_length_patterns(stats_report))
        patterns.extend(extract_consistency_proxy_patterns(stats_report))
        notes.append("[integration note] No outcomes_report supplied -- error_location, "
                      "rally_accuracy, pressure_moments, zone_error_rate, and "
                      "coverage_point_loss patterns are all unavailable; rally_length falls back "
                      "to an aggregate (not per-player) signal, and consistency falls back to the "
                      "weaker avg_hits_per_rally proxy.")

    if not patterns:
        return pd.DataFrame(columns=[
            "rank", "player", "category", "pattern", "frequency_pct",
            "point_loss_count", "combined_score", "reason",
        ]), notes

    freq_norm = _normalize([p.frequency_pct for p in patterns])
    loss_norm = _normalize([p.point_loss_count for p in patterns])

    rows = []
    for p, f_n, l_n in zip(patterns, freq_norm, loss_norm):
        combined = FREQUENCY_WEIGHT * f_n + POINT_LOSS_WEIGHT * l_n
        rows.append({
            "player": p.player,
            "category": p.category,
            "pattern": p.label,
            "frequency_pct": round(p.frequency_pct, 1),
            "point_loss_count": p.point_loss_count,
            "combined_score": round(combined, 3),
            "reason": p.reason,
        })

    df = pd.DataFrame(rows).sort_values("combined_score", ascending=False).reset_index(drop=True)
    df.insert(0, "rank", df.index + 1)
    return df, notes


if __name__ == "__main__":
    import config
    import match_stats
    import rally_outcomes

    events_path = config.CODE_DIR / "synthetic_rally_events.csv"
    player_path = config.CODE_DIR / "synthetic_player_data.csv"

    stats_report = match_stats.generate_stats_report(
        events_csv=str(events_path), player_csv=str(player_path),
    )
    outcomes_report = rally_outcomes.generate_outcomes_report(str(events_path))

    table, notes = build_priority_table(stats_report, outcomes_report)
    pd.set_option("display.max_colwidth", None)
    pd.set_option("display.width", 160)
    print(table.to_string(index=False))
    if notes:
        print("\nData-quality notes:")
        for n in notes:
            print(" -", n)
