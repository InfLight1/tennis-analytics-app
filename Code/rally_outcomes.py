"""
rally_outcomes.py
(reconstructed from session content for local diagnostic use)
"""

import pandas as pd
import numpy as np

import config

NET_X = config.NET_POSITION_OFFSET
COURT_W = config.TABLE_W
COURT_H = config.TABLE_H
OTHER_SIDE = {"near": "far", "far": "near"}
SERVICE_LINE = config.SERVICE_LINE_OFFSET_FROM_BASELINE
TOL = config.IN_OUT_TOLERANCE_CM
SERVE_BOX_CHECK = True
SERVE_MAX_FLIGHT_FRAMES = 45    # serve contact -> first bounce (measured ~20-30)
FAR_BOX_LONG_MARGIN_CM = 100    # near-player serve called long only this far past the far service line (None = never)
# Two serves per point (2026-09-30, confirmed by the user): a serve fault is
# only a lost point if it's the SECOND serve. A first-serve fault is a rally
# lost by the server on the serve itself, followed by the same server serving
# again within SECOND_SERVE_MAX_GAP_S (labeled data: 5-12 s; a new point:
# >= 22 s). It is kept as a row (serve % / fault stats) but awards no point.
TWO_SERVES = True
SECOND_SERVE_MAX_GAP_S = 15
MIN_SERVE_GAP_S = 3          # nobody serves again sooner than this
# The receiver often swats a fault back over (or into the net) anyway; the
# point was already over when the serve landed out, so serve + one more hit
# is still a serve fault (point 13 of ground_truth_points.csv, 2026-10-21).
# More hits than that = a real rally, so a "fault" there is a misread bounce.
SERVE_FAULT_MAX_HITS = 2
DROP_BETWEEN_POINT_FEEDS = True   # see drop_between_point_feeds


def classify_error_type(hit_table_x, bounce_table_x, bounce_table_y, hitter_side=None):
    # The hitter's resolved side beats their projected contact position: a
    # ball struck in the air projects long, even past the net (2026-09-29).
    if hitter_side in OTHER_SIDE:
        hit_table_x = 0.0 if hitter_side == "near" else float(COURT_W)
    if pd.isna(hit_table_x) or pd.isna(bounce_table_x) or pd.isna(bounce_table_y):
        return "unclassified"

    hit_side_near = hit_table_x < NET_X
    bounce_side_near = bounce_table_x < NET_X
    if hit_side_near == bounce_side_near:
        return "net"
    if bounce_table_x < 0 or bounce_table_x > COURT_W:
        return "long"
    y_lo, y_hi = config.rally_width_bounds()   # alleys count in doubles
    if bounce_table_y < y_lo or bounce_table_y > y_hi:
        return "wide"
    return "unclassified"


def _consecutive_hit_bounce_pairs(events_df):
    for rally_id, group in events_df.groupby("rally_id"):
        g = group.sort_values("frame").reset_index(drop=True)
        for i in range(len(g) - 1):
            cur, nxt = g.iloc[i], g.iloc[i + 1]
            if cur["event_type"] == "hit" and nxt["event_type"] == "bounce":
                yield cur, nxt


def per_shot_accuracy(events_df):
    rows = []
    unknown_rows = []
    for hit, bounce in _consecutive_hit_bounce_pairs(events_df):
        if hit["player_side"] in (None, "unknown"):
            continue
        in_bounds = bounce.get("in_bounds")
        if pd.isna(in_bounds):
            unknown_rows.append({"player_side": hit["player_side"]})
            continue
        rows.append({"player_side": hit["player_side"], "in": bool(in_bounds)})

    unknown_counts = (
        pd.DataFrame(unknown_rows).groupby("player_side").size()
        if unknown_rows else pd.Series(dtype=int)
    )

    if not rows:
        summary = pd.DataFrame(columns=["player_side", "shots_in", "shots_out", "rally_accuracy_pct"])
    else:
        df = pd.DataFrame(rows)
        summary = df.groupby("player_side")["in"].agg(
            shots_in="sum", shots_out=lambda s: int((~s).sum())
        ).reset_index()
        summary["rally_accuracy_pct"] = (
            100.0 * summary["shots_in"] / (summary["shots_in"] + summary["shots_out"])
        )

    all_players = set(summary["player_side"]) | set(unknown_counts.index)
    summary = summary.set_index("player_side").reindex(all_players).reset_index()
    for col in ("shots_in", "shots_out"):
        summary[col] = summary[col].fillna(0).astype(int)
    summary["unknown_outcome_shots"] = (
        summary["player_side"].map(unknown_counts).fillna(0).astype(int)
    )
    summary["rally_accuracy_pct"] = np.where(
        (summary["shots_in"] + summary["shots_out"]) > 0,
        100.0 * summary["shots_in"] / (summary["shots_in"] + summary["shots_out"]),
        np.nan,
    )

    return summary[["player_side", "shots_in", "shots_out", "rally_accuracy_pct", "unknown_outcome_shots"]]


def error_location_stats(events_df):
    rows = []
    for hit, bounce in _consecutive_hit_bounce_pairs(events_df):
        if hit["player_side"] in (None, "unknown"):
            continue
        in_bounds = bounce.get("in_bounds")
        if pd.isna(in_bounds):
            rows.append({"player_side": hit["player_side"], "error_type": "unknown_outcome"})
            continue
        if bool(in_bounds):
            continue
        err_type = classify_error_type(hit["table_x"], bounce["table_x"], bounce["table_y"])
        rows.append({"player_side": hit["player_side"], "error_type": err_type})

    if not rows:
        return pd.DataFrame(columns=["player_side", "error_type", "count"])

    df = pd.DataFrame(rows)
    return df.groupby(["player_side", "error_type"]).size().rename("count").reset_index()


def serve_fault(g):
    """Error type if the serve's first bounce misses the receiver's service
    box ("long" past the service line, "wide" outside the singles lines,
    "net" on the server's own half), else None. The serve = the rally's
    first event, a hit by a resolved side, bouncing before any other hit."""
    if len(g) < 2 or g.iloc[0]["event_type"] != "hit":
        return None
    serve, first = g.iloc[0], g.iloc[1]
    if serve["player_side"] not in OTHER_SIDE or first["event_type"] != "bounce":
        return None
    if first["frame"] - serve["frame"] > SERVE_MAX_FLIGHT_FRAMES:
        return None
    x, y = first["table_x"], first["table_y"]
    if pd.isna(x) or pd.isna(y):
        return None
    if serve["player_side"] == "far":           # box on the near half: service line .. net
        lo, hi = SERVICE_LINE, NET_X
        if x > NET_X + TOL:
            return "net"
        if x < lo - TOL:
            return "long"
    else:                                       # box on the far half: net .. far service line
        # Only "landed on the server's own half" is judged here. Far-half
        # bounce positions run long: both near-player serves in
        # ground_truth_points.csv that were in (points 8, 11 -- long rallies
        # followed) measured 50-120 cm past the far service line, so a long
        # or wide call there would be a guess.
        # 2026-10-21: that "runs long" came from a misplaced hand-marked
        # court; with the court found automatically point 8's serve lands
        # 2 m inside the box. Far-half positions still wobble with camera
        # sway, so only a clearly long serve is called.
        if x < NET_X - TOL:
            return "net"
        if FAR_BOX_LONG_MARGIN_CM is not None and x > COURT_W - SERVICE_LINE + FAR_BOX_LONG_MARGIN_CM:
            return "long"
        return None
    if y < -TOL or y > COURT_H + TOL:
        return "wide"
    return None


def _classify_rally_ending(g):
    if not bool(g.iloc[0].get("has_hit", True)):
        return {"winner": None, "loser": None, "reason": "no_hit_detected",
                "error_type": None, "final_table_x": None, "final_table_y": None}

    fault = serve_fault(g) if SERVE_BOX_CHECK else None
    if fault is not None and (g["event_type"] == "hit").sum() > SERVE_FAULT_MAX_HITS:
        fault = None                                # play went on: the serve bounce was misread
    if fault is not None:
        server = g.iloc[0]["player_side"]
        return {"winner": OTHER_SIDE[server], "loser": server,
                "reason": "opponent_error", "error_type": fault,
                "final_table_x": g.iloc[1]["table_x"], "final_table_y": g.iloc[1]["table_y"]}

    last = g.iloc[-1]

    if last["event_type"] == "net":
        # Ball stopped by the net (analysis.detect_net_events): the last hitter loses.
        prior_hits = g[(g["event_type"] == "hit") & (g["frame"] < last["frame"])]
        hitter = prior_hits.iloc[-1] if len(prior_hits) else None
        if hitter is None or hitter["player_side"] not in OTHER_SIDE:
            return {"winner": None, "loser": None, "reason": "ambiguous",
                    "error_type": "net", "final_table_x": None, "final_table_y": None}
        return {"winner": OTHER_SIDE[hitter["player_side"]], "loser": hitter["player_side"],
                "reason": "opponent_error", "error_type": "net",
                "final_table_x": last["table_x"], "final_table_y": None}

    if last["event_type"] == "hit":
        return {"winner": None, "loser": None, "reason": "ambiguous",
                "error_type": None, "final_table_x": None, "final_table_y": None}

    final_x, final_y = last["table_x"], last["table_y"]

    prior_hits = g[(g["event_type"] == "hit") & (g["frame"] < last["frame"])]
    if len(prior_hits) == 0:
        return {"winner": None, "loser": None, "reason": "ambiguous",
                "error_type": None, "final_table_x": None, "final_table_y": None}
    hitter = prior_hits.iloc[-1]
    if hitter["player_side"] in (None, "unknown"):
        return {"winner": None, "loser": None, "reason": "ambiguous",
                "error_type": None, "final_table_x": None, "final_table_y": None}

    in_bounds = last.get("in_bounds")
    if pd.isna(in_bounds):
        return {"winner": None, "loser": None, "reason": "ambiguous",
                "error_type": None, "final_table_x": None, "final_table_y": None}

    other_hits = g[
        (g["event_type"] == "hit")
        & g["player_side"].notna()
        & (g["player_side"] != "unknown")
        & (g["player_side"] != hitter["player_side"])
    ]
    if len(other_hits):
        opponent = other_hits["player_side"].iloc[-1]
    else:
        # Singles: once sides are resolved the opponent is simply the other
        # side, even when they never got a racket on the ball (ace, serve
        # fault). Before resolution (raw track ids) it stays unknown.
        opponent = OTHER_SIDE.get(hitter["player_side"], "unknown_opponent")

    if bool(in_bounds):
        return {"winner": hitter["player_side"], "loser": opponent,
                "reason": "opponent_no_return", "error_type": None,
                "final_table_x": final_x, "final_table_y": final_y}
    else:
        err_type = classify_error_type(hitter["table_x"], last["table_x"], last["table_y"],
                                       hitter_side=hitter["player_side"])
        return {"winner": opponent, "loser": hitter["player_side"],
                "reason": "opponent_error", "error_type": err_type,
                "final_table_x": final_x, "final_table_y": final_y}


def rally_outcomes(events_df):
    rows = []
    for rally_id, group in events_df.groupby("rally_id"):
        g = group.sort_values("frame").reset_index(drop=True)
        outcome = _classify_rally_ending(g)

        hits = g[g["event_type"] == "hit"]
        server = hits.iloc[0]["player_side"] if len(hits) else None

        rows.append({
            "rally_id": rally_id,
            "server": server,
            "winner": outcome["winner"],
            "loser": outcome["loser"],
            "reason": outcome["reason"],
            "error_type": outcome["error_type"],
            "final_table_x": outcome["final_table_x"],
            "final_table_y": outcome["final_table_y"],
            "serve_fault": bool(len(hits) <= SERVE_FAULT_MAX_HITS and outcome["reason"] == "opponent_error"
                                and server in OTHER_SIDE and outcome["loser"] == server),
            "start_frame": int(g["frame"].min()),
            "end_frame": int(g["frame"].max()),
            "n_hits": int(len(hits)),
        })
    out = pd.DataFrame(rows)
    if TWO_SERVES and len(out):
        out = mark_first_serve_faults(out)
    if DROP_BETWEEN_POINT_FEEDS and len(out):
        out = drop_between_point_feeds(out)
    return out


def drop_between_point_feeds(out):
    """An unreturned single shot from the wrong end in the middle of the
    other player's service game is the ball being hit back to the server
    between points, not an ace (2026-10-21: 2 of the 3 points the pipeline
    invented outside the labeled ones). Same "one player serves a whole
    game" test as serve_attempts; no winner, reason 'between_points'."""
    out = out.sort_values("start_frame").reset_index(drop=True)
    known = out[out["server"].isin(list(OTHER_SIDE))]
    s, idx = known["server"].tolist(), known.index.tolist()
    # Feeds cluster, so take out the most out-of-place one and repeat.
    while len(s) >= 3:
        def odd(k):            # most of the 2 rallies either side came from the other end
            nb = s[max(0, k - 2):k] + s[k + 1:k + 3]
            return sum(x != s[k] for x in nb) / len(nb) if len(nb) >= 2 else 0
        scores = [odd(k) for k in range(len(s))]
        worst = max(range(len(s)), key=lambda k: scores[k])
        if scores[worst] <= 0.5:
            break
        i = idx[worst]
        if out.loc[i, "n_hits"] == 1 and out.loc[i, "reason"] == "opponent_no_return":
            out.loc[i, ["winner", "loser"]] = None
            out.loc[i, "reason"] = "between_points"
        del s[worst], idx[worst]
    return out


def mark_first_serve_faults(out, fps=config.TRACKER_FRAME_RATE):
    """Re-label first-serve faults (see TWO_SERVES): reason
    'first_serve_fault', no winner/loser, error_type kept. A fault right
    after a first fault by the same server is a double fault and keeps its
    point."""
    out = out.sort_values("start_frame").reset_index(drop=True)
    max_gap = SECOND_SERVE_MAX_GAP_S * fps
    pending = None                                  # (server, end_frame) of an open first fault
    for i, r in out.iterrows():
        nxt = out.iloc[i + 1] if i + 1 < len(out) else None
        if r["serve_fault"]:
            if pending is not None and pending[0] == r["server"] and r["start_frame"] - pending[1] <= max_gap:
                pending = None                      # second serve also missed: double fault, point stands
                continue
            serves_again = (nxt is not None and nxt["server"] == r["server"]
                            and nxt["start_frame"] - r["end_frame"] <= max_gap)
            if serves_again:
                out.loc[i, ["winner", "loser"]] = None
                out.loc[i, "reason"] = "first_serve_fault"
                pending = (r["server"], r["end_frame"])
                continue
            # Lone serve fault: no first fault tracked before it and no
            # second serve after it. It may be a double fault, a first fault
            # whose second serve went untracked, or a ball fed back between
            # points (2026-10-06 audit: 7 of 10 such "double faults" matched
            # no labeled point). Don't charge anyone a point for it.
            out.loc[i, ["winner", "loser"]] = None
            out.loc[i, "reason"] = "serve_fault_unconfirmed"
        pending = None
    return out


def points_won_summary(outcomes_df):
    unknown_labels = {None, "unknown", "unknown_opponent"}

    known_players = set()
    for col in ("server", "winner", "loser"):
        known_players.update(outcomes_df[col].dropna().unique())
    known_players -= unknown_labels

    resolved = outcomes_df[
        outcomes_df["winner"].notna()
        & (~outcomes_df["winner"].isin(unknown_labels))
        & (~outcomes_df["loser"].isin(unknown_labels))
    ]

    if len(resolved) == 0:
        summary = pd.DataFrame(columns=["player_side", "points_won", "points_lost"])
    else:
        won = resolved.groupby("winner").size().rename("points_won")
        lost = resolved.groupby("loser").size().rename("points_lost")
        summary = pd.concat([won, lost], axis=1).fillna(0).astype(int).reset_index()
        summary = summary.rename(columns={"index": "player_side"})

    ambiguous_count = 0
    if len(known_players) == 2:
        ambiguous_mask = (
            (outcomes_df["reason"] == "ambiguous")
            & (
                outcomes_df["winner"].isna()
                | outcomes_df["winner"].isin(unknown_labels)
                | outcomes_df["loser"].isin(unknown_labels)
            )
        )
        ambiguous_count = int(ambiguous_mask.sum())

    all_players = set(summary["player_side"]) | known_players
    summary = summary.set_index("player_side").reindex(all_players).reset_index()
    for col in ("points_won", "points_lost"):
        summary[col] = summary[col].fillna(0).astype(int)
    summary["ambiguous_rallies_involved"] = ambiguous_count if len(known_players) == 2 else 0

    return summary[["player_side", "points_won", "points_lost", "ambiguous_rallies_involved"]]


def per_shot_outcomes(events_df):
    rows = []
    for hit, bounce in _consecutive_hit_bounce_pairs(events_df):
        in_bounds = bounce.get("in_bounds")
        if pd.isna(in_bounds):
            continue
        if hit["player_side"] in (None, "unknown"):
            continue
        rows.append({
            "rally_id": hit["rally_id"],
            "player_side": hit["player_side"],
            "hit_table_x": hit["table_x"],
            "hit_table_y": hit["table_y"],
            "in_bounds": bool(in_bounds),
        })
    return pd.DataFrame(rows, columns=["rally_id", "player_side", "hit_table_x", "hit_table_y", "in_bounds"])


def generate_outcomes_report(events_csv):
    events_df = pd.read_csv(events_csv)
    outcomes_df = rally_outcomes(events_df)

    real_rallies = outcomes_df[outcomes_df["reason"] != "no_hit_detected"]

    return {
        "rally_outcomes": outcomes_df,
        "points_won": points_won_summary(outcomes_df),
        "rally_accuracy": per_shot_accuracy(events_df),
        "error_location": error_location_stats(events_df),
        "per_shot_outcomes": per_shot_outcomes(events_df),
        "no_hit_detected_count": int((outcomes_df["reason"] == "no_hit_detected").sum()),
        "ambiguous_rate": (
            (real_rallies["reason"] == "ambiguous").mean() if len(real_rallies) else np.nan
        ),
    }


if __name__ == "__main__":
    report = generate_outcomes_report(config.EVENTS_CSV)

    outcomes_out_path = str(config.EVENTS_CSV).replace("rally_events.csv", "rally_outcomes.csv")
    report["rally_outcomes"].to_csv(outcomes_out_path, index=False)

    print(f"Rally outcomes: {len(report['rally_outcomes'])} rallies classified, "
          f"written to {outcomes_out_path}")
    print(f"  no_hit_detected: {report['no_hit_detected_count']}")
    print(f"  ambiguous_rate (of real, has_hit rallies): {report['ambiguous_rate']:.1%}"
          if pd.notna(report['ambiguous_rate']) else "  ambiguous_rate: n/a (no real rallies)")

    print("\nReason breakdown:")
    print(report["rally_outcomes"]["reason"].value_counts())

    print("\nPoints won/lost by player_side (track_id-level, pre-near/far resolution):")
    print(report["points_won"])

    print("\nPer-shot accuracy by player_side:")
    print(report["rally_accuracy"])

    print("\nError location breakdown:")
    print(report["error_location"])


def serve_attempts(outcomes_df, fps=config.TRACKER_FRAME_RATE):
    """One row per detected serve (2026-10-07). Serve stats must count EVERY
    serve the pipeline sees -- not only serves in points whose winner is
    known (that left 4 of a player's serves on the live run and showed 75%
    first serves in for a player who missed most of them).

    result: "fault" (serve-only fault: first, double or unconfirmed),
            "in" (the return was hit, or an unreturned serve), or
            "unknown" (only the serve was seen and the outcome is unclear).
    attempt: 2 if it follows a first-serve fault by the same server within
             SECOND_SERVE_MAX_GAP_S, else 1. An unconfirmed lone fault counts
             as a first serve (most faults are)."""
    o = outcomes_df.sort_values("start_frame").reset_index(drop=True)
    rows, prev = [], None
    for r in o.itertuples():
        if r.server not in OTHER_SIDE:
            prev = None
            continue
        shots = getattr(r, "n_hits", None)
        fault = bool(r.serve_fault) or r.reason in ("first_serve_fault", "serve_fault_unconfirmed")
        if fault:
            result = "fault"
        elif r.reason == "no_hit_detected":
            result = "unknown"
        elif shots is not None and shots >= 2:
            result = "in"
        elif r.reason == "opponent_no_return":
            result = "in"
        else:
            result = "unknown"
        second = (prev is not None and prev["server"] == r.server and prev["result"] == "fault"
                  and prev["attempt"] == 1 and r.start_frame - prev["end"] <= SECOND_SERVE_MAX_GAP_S * fps)
        row = {"rally_id": r.rally_id, "start_frame": r.start_frame, "end": r.end_frame,
               "server": r.server, "result": result, "attempt": 2 if second else 1}
        rows.append(row)
        prev = row
    df = pd.DataFrame(rows, columns=["rally_id", "start_frame", "end", "server", "result", "attempt"])
    # A serve needs a fresh ball and a toss: nothing starting within
    # MIN_SERVE_GAP_S of the previous serve's end is a serve (it's the ball
    # dribbling off the net or being picked up).
    keep, last_end = [], None
    for r in df.itertuples():
        keep.append(last_end is None or r.start_frame - last_end >= MIN_SERVE_GAP_S * fps)
        if keep[-1]:
            last_end = r.end
    df = df[keep].reset_index(drop=True)
    # One player serves a whole game, so "serves" from the other end in the
    # middle of someone's service game are the ball being hit back to the
    # server between points (labeled clip: none were serves). Several can
    # cluster, so drop the most out-of-place one and repeat until stable.
    while len(df) >= 3:
        s = df["server"].tolist()
        def odd(i):            # most of the 2 serves either side came from the other end
            nb = s[max(0, i - 2):i] + s[i + 1:i + 3]
            return sum(x != s[i] for x in nb) / len(nb) if len(nb) >= 2 else 0
        scores = [odd(i) for i in range(len(s))]
        worst = max(range(len(s)), key=lambda i: scores[i])
        if scores[worst] <= 0.5:
            break
        df = df.drop(index=worst).reset_index(drop=True)
    return df
