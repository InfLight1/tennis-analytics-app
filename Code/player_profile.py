"""
player_profile.py -- per-player analysis for the report page and the LLM
suggestion layer (Week 2 #7/#8/#9, 2026-09-30).

One consistent source of truth per player: every number is counted from
POINT outcomes (rally_outcomes.rally_outcomes) mapped to player_1/player_2
with the same end-swap logic as scoring.score_match_near_far, so a
percentage can't exceed its own denominator (the legacy
prioritization/report mixed shot-level error counts with point-level
losses: "133% of lost points").

Output per player:
  - results: points won/lost, how they were won and lost
  - serve / return: first-serve %, double faults, aces, points won
  - rally length: points won/lost in short / medium / long rallies
  - shot mix + court position (volley share, depth behind the baseline)
  - strengths and weaknesses: ranked patterns with points gained/lost and a
    sample size; patterns below the minimum sample are kept but marked
    low_sample and never ranked
  - playstyle: tags + one sentence, derived from the numbers above

Usage (from Code/):
  python player_profile.py <rally_events_resolved.csv> [--match match_data.csv]
                           [--names "Alex,Sam"] [--out profile.json]
"""

import argparse
import json

import numpy as np
import pandas as pd

import config
import rally_outcomes
import scoring

COURT_W = config.TABLE_W
NET_X = config.NET_POSITION_OFFSET
SERVICE_LINE = config.SERVICE_LINE_OFFSET_FROM_BASELINE
SHORT_MAX = config.RALLY_LENGTH_SHORT_MAX_HITS      # <= 4 shots
LONG_MIN = config.RALLY_LENGTH_LONG_MIN_HITS        # >= 9 shots
PLAYERS = ("player_1", "player_2")

# A pattern is only ranked when it happened at least MIN_OCCURRENCES times
# out of at least MIN_SAMPLE chances. Below that it's an anecdote, not a
# pattern -- shown as "not enough data yet", never as a headline.
MIN_OCCURRENCES = 2
MIN_SAMPLE = 4
TOP_N = 3

ERROR_WORDS = {"net": "into the net", "long": "long (past the baseline)",
               "wide": "wide (outside the sideline)", "unclassified": "out (direction unclear)"}


def _pct(a, b):
    return None if not b else round(100.0 * a / b, 1)


def _player_maps(per_point_df):
    """rally_id -> {"near": player, "far": player} from scoring's end-swap logic."""
    return {int(r.rally_id): {"near": r.near_player, "far": r.far_player}
            for r in per_point_df.itertuples()}


def _hitter_depths(events, match_df, side_maps):
    """Per player, the hitter's distance behind their own baseline (cm,
    negative = inside the court) at each hit, from the player's tracked
    foot position. Returns {player: [depth_cm, ...]}."""
    out = {p: [] for p in PLAYERS}
    if match_df is None:
        return out
    pl = match_df[(match_df["type"] == "player") & match_df["table_x"].notna()]
    by_frame = {f: g for f, g in pl.groupby("frame")}
    for e in events[events["event_type"] == "hit"].itertuples():
        side = e.player_side
        if side != "near":
            # Far-end foot positions are too imprecise to report (one pixel
            # is 5-10 cm there; 09-30 run put a player 3.4 m behind the
            # baseline who wasn't). Use near-end hits only.
            continue
        player = side_maps.get(int(e.rally_id), {}).get(side)
        g = by_frame.get(int(e.frame))
        if player is None or g is None:
            continue
        half = g[g["table_x"] < NET_X] if side == "near" else g[g["table_x"] >= NET_X]
        if len(half) == 0:
            continue
        x = float(half["table_x"].median())
        out[player].append(-x if side == "near" else x - COURT_W)
    return out


def build_profiles(events_df, match_df=None, names=None, end_swaps=None, fps=None):
    """events_df: rally_events_resolved.csv (player_side near/far). Returns
    a JSON-ready dict: {"match": {...}, "coverage": {...}, "players": {...}}.
    fps: the video's frame rate; when given, every pattern lists "moments"
    (seconds into the video where each of its points starts)."""
    events = events_df.sort_values(["rally_id", "frame"]).reset_index(drop=True)
    outcomes = rally_outcomes.rally_outcomes(events)
    per_point, score = scoring.score_match_near_far(outcomes, end_swaps)
    side_maps = _player_maps(per_point)
    names = names or {}

    hits = events[events["event_type"] == "hit"]
    n_hits = hits.groupby("rally_id").size()
    rally_start = events.groupby("rally_id")["frame"].min()

    # ---- one row per rally, in player terms --------------------------------
    rows = []
    for o in outcomes.itertuples():
        rid = int(o.rally_id)
        m = side_maps.get(rid, {})
        server = m.get(o.server) if o.server in ("near", "far") else None
        rows.append({
            "rally_id": rid, "reason": o.reason, "error_type": o.error_type,
            "serve_fault": bool(o.serve_fault),
            "server": server,
            "receiver": next((p for p in PLAYERS if server and p != server), None),
            "winner": m.get(o.winner) if o.winner in ("near", "far") else None,
            "loser": m.get(o.loser) if o.loser in ("near", "far") else None,
            "shots": int(n_hits.get(rid, 0)),
            "start_frame": int(rally_start.get(rid, 0)),
        })
    R = pd.DataFrame(rows)
    points = R[R["winner"].isin(PLAYERS) & R["loser"].isin(PLAYERS)].copy()
    first_faults = R[R["reason"] == "first_serve_fault"]
    unconfirmed = R[R["reason"] == "serve_fault_unconfirmed"]

    def bucket(n):
        return "short" if n <= SHORT_MAX else "long" if n >= LONG_MIN else "medium"
    points["bucket"] = points["shots"].map(bucket)
    # Second-serve points: the rally right after a first-serve fault by the
    # same server. A serve-only fault that LOSES the point is a double fault
    # even when its first fault went undetected (then that first fault is
    # implied, so first-serve stats stay consistent: faults >= double faults).
    prev = R.shift(1)
    after_first = (prev["reason"] == "first_serve_fault") & (prev["server"] == R["server"])
    points["after_first_fault"] = after_first.reindex(points.index).fillna(False).astype(bool)
    points["double_fault"] = points["serve_fault"] & (points["loser"] == points["server"])
    points["second_serve"] = points["after_first_fault"] | points["double_fault"]
    points["ace"] = (points["reason"] == "opponent_no_return") & (points["shots"] == 1) \
        & (points["winner"] == points["server"])

    depths = _hitter_depths(events, match_df, side_maps)

    # Every detected serve (not just decided points), in player terms.
    SA = rally_outcomes.serve_attempts(outcomes)
    SA["player"] = [side_maps.get(int(r), {}).get(sv) for r, sv in zip(SA["rally_id"], SA["server"])]
    SA = SA[SA["player"].isin(PLAYERS) & (SA["result"] != "unknown")]

    players = {}
    for p in PLAYERS:
        opp = PLAYERS[1] if p == PLAYERS[0] else PLAYERS[0]
        won = points[points["winner"] == p]
        lost = points[points["loser"] == p]
        served = points[points["server"] == p]
        returned = points[points["receiver"] == p]
        # every served point starts with a first serve; detected first faults
        # plus double faults whose first fault went unseen
        first_serves = len(served)
        n_first_faults = int((first_faults["server"] == p).sum()
                             + (served["double_fault"] & ~served["after_first_fault"]).sum())
        second_serve_pts = served[served["second_serve"]]

        own_errors = lost[(lost["reason"] == "opponent_error") & ~lost["double_fault"]]
        err_by_type = own_errors["error_type"].fillna("unclassified").value_counts().to_dict()
        winners = won[(won["reason"] == "opponent_no_return") & ~won["ace"]]
        opp_errors = won[(won["reason"] == "opponent_error") & ~won["double_fault"]]
        beaten = lost[lost["reason"] == "opponent_no_return"]

        my_hits = []
        for e in hits.itertuples():
            if side_maps.get(int(e.rally_id), {}).get(e.player_side) == p:
                my_hits.append(e.shot_type if isinstance(e.shot_type, str) else "unknown")
        mix = pd.Series(my_hits).value_counts().to_dict() if my_hits else {}
        rally_shots = sum(v for k, v in mix.items() if k != "serve")
        d = np.array(depths[p]) if depths[p] else np.array([])

        my_sa = SA[SA["player"] == p]
        my_first = my_sa[my_sa["attempt"] == 1]
        stats = {
            "points_played": int(len(won) + len(lost)),
            "points_won": int(len(won)), "points_lost": int(len(lost)),
            "points_won_pct": _pct(len(won), len(won) + len(lost)),
            "won_by": {"winners": int(len(winners)), "aces": int(won["ace"].sum()),
                       "opponent_errors": int(len(opp_errors)),
                       "opponent_double_faults": int(won["double_fault"].sum())},
            "lost_by": {"own_errors": {k: int(v) for k, v in err_by_type.items()},
                        "double_faults": int(lost["double_fault"].sum()),
                        "opponent_winners": int(len(beaten))},
            "serve": {
                # counted over EVERY tracked serve (rally_outcomes.serve_attempts)
                "serves_tracked": int(len(my_sa)),
                "serves_in": int((my_sa["result"] == "in").sum()),
                "serves_in_pct": _pct((my_sa["result"] == "in").sum(), len(my_sa)),
                "first_serves": int(len(my_first)),
                "first_serve_faults": int((my_first["result"] == "fault").sum()),
                "first_serve_in_pct": _pct((my_first["result"] == "in").sum(), len(my_first)),
                "second_serves": int((my_sa["attempt"] == 2).sum()),
                "points_served": int(first_serves),
                # missed serves where it's unknown whether it was the first or second serve
                "unconfirmed_serve_faults": int((unconfirmed["server"] == p).sum()),
                "double_faults": int(lost["double_fault"].sum()),
                "aces": int(won["ace"].sum()),
                "service_points_won_pct": _pct((served["winner"] == p).sum(), len(served)),
                "second_serve_points": int(len(second_serve_pts)),
                "second_serve_points_won_pct": _pct((second_serve_pts["winner"] == p).sum(),
                                                    len(second_serve_pts)),
            },
            "return": {"return_points": int(len(returned)),
                       "return_points_won_pct": _pct((returned["winner"] == p).sum(), len(returned))},
            # shots per decided point (serve included); the same match for both players
            "avg_rally_shots": round(float(points["shots"].mean()), 1) if len(points) else None,
            "short_point_max_shots": SHORT_MAX,
            "rally_length": {b: {"played": int((points["bucket"] == b).sum()),
                                 "won": int(((points["bucket"] == b) & (points["winner"] == p)).sum())}
                             for b in ("short", "medium", "long")},
            "shot_mix": {k: int(v) for k, v in mix.items()},
            # unreliable (see _playstyle) -- reported, never used for conclusions
            "volley_share_pct_unreliable": _pct(mix.get("volley", 0), rally_shots),
            "position": {
                "hits_with_position": int(len(d)),
                "median_depth_behind_baseline_cm": None if not len(d) else int(np.median(d)),
                # "at the net" = inside the service line
                "net_share_pct": None if not len(d) else _pct(int((d < -(NET_X - SERVICE_LINE)).sum()), len(d)),
            },
        }
        players[p] = {
            "id": p,
            "name": names.get(p) or ("Player 1" if p == PLAYERS[0] else "Player 2"),
            "start_end": "near" if p == PLAYERS[0] else "far",
            "stats": stats,
        }
        weaknesses, strengths = _patterns(stats)
        if fps:
            # Which points each pattern counts, so the report can say where
            # to look in the video ("see the moments").
            bucket_lost = {b: lost[lost["bucket"] == b] for b in ("short", "long")}
            bucket_won = {b: won[won["bucket"] == b] for b in ("short", "long")}
            # first-serve faults from the same serve list the percentage uses
            fault_rallies = my_first.loc[my_first["result"] == "fault", "rally_id"]
            first_fault_rows = pd.DataFrame({"start_frame": [int(rally_start.get(int(r), 0)) for r in fault_rallies]})
            weak_rows = {
                **{f"errors_{k}": own_errors[own_errors["error_type"].fillna("unclassified") == k] for k in err_by_type},
                "double_faults": lost[lost["double_fault"]],
                "opponent_winners": beaten,
                "first_serve_pct": first_fault_rows,
                "serve_points": served[served["loser"] == p],
                "rally_short": bucket_lost["short"], "rally_long": bucket_lost["long"],
            }
            strong_rows = {
                "winners": winners, "aces": won[won["ace"]], "draws_errors": opp_errors,
                "serve_points": served[served["winner"] == p],
                "return_points": returned[returned["winner"] == p],
                "rally_short": bucket_won["short"], "rally_long": bucket_won["long"],
            }
            for pats, rows_by_id in ((weaknesses, weak_rows), (strengths, strong_rows)):
                for pat in pats:
                    if pat["id"] in rows_by_id:
                        pat["moments"] = _moments(rows_by_id[pat["id"]], fps)
        players[p]["weaknesses"] = weaknesses
        players[p]["strengths"] = strengths
        players[p]["playstyle"] = _playstyle(stats)

    decided = len(points)
    coverage = {
        "rallies_detected": int(len(R)),
        "points_decided": int(decided),
        "first_serve_faults": int(len(first_faults)),
        "unconfirmed_serve_faults": int(len(unconfirmed)),
        "rallies_undecided": int(len(R) - decided - len(first_faults) - len(unconfirmed)),
        "notes": [
            f"Point winner determined for {decided} of {len(R) - len(first_faults) - len(unconfirmed)} detected points "
            f"({_pct(decided, len(R) - len(first_faults) - len(unconfirmed))}%); the rest are left out of every number below.",
            f"{len(unconfirmed)} missed serves couldn't be confirmed as first or second serves, so they aren't counted as "
            f"double faults or lost points.",
            "In/out calls for balls landing on the far half of the court are less precise "
            "(positions there can be off by up to about a metre), so depth placement on that side is not shown.",
            "Where a player stands is only measured while they're at the end closest to the camera.",
        ],
    }
    match = {
        "score": {"sets_won": score.get("sets_won"), "completed_sets": score.get("completed_sets"),
                  "match_winner": score.get("match_winner")},
        "points_scored": int(score.get("rallies_scored", 0)),
    }
    return {"match": match, "coverage": coverage, "players": players,
            "min_sample": {"occurrences": MIN_OCCURRENCES, "chances": MIN_SAMPLE}}


MOMENT_LEAD_S = 2   # start a moment a little before the serve, to see the set-up


def _moments(rows, fps):
    """Seconds into the video where these points start, in order."""
    return sorted({max(0, int(f / fps) - MOMENT_LEAD_S) for f in rows["start_frame"]})


def _pattern(pid, kind, tier, title, detail, points, occurrences, chances):
    confident = occurrences >= MIN_OCCURRENCES and chances >= MIN_SAMPLE
    return {"id": pid, "kind": kind, "tier": tier, "title": title, "detail": detail,
            "points": int(points), "occurrences": int(occurrences), "chances": int(chances),
            "low_sample": not confident}


def _patterns(s):
    """Two tiers.
    headline: categories that PARTITION the player's lost points (own
      errors by type, double faults, opponent winners) and won points
      (winners, aces, opponent errors). They never double-count, so the
      ranking honestly answers "what cost / won this player the most points"
      and the points add up to the total.
    context: rates that explain the headline (first-serve %, serve and return
      points won, rally length). They overlap with the headline points, so
      they're shown as supporting insights, never ranked against them."""
    W, S = [], []
    lost, won = s["points_lost"], s["points_won"]
    sv, rt, rl = s["serve"], s["return"], s["rally_length"]

    # ---- headline weaknesses (partition of points lost) -------------------
    for etype, n in s["lost_by"]["own_errors"].items():
        W.append(_pattern(f"errors_{etype}", "weakness", "headline", f"Errors {ERROR_WORDS.get(etype, etype)}",
                          f"{n} of {lost} points lost were their own shot going {ERROR_WORDS.get(etype, etype)}.",
                          n, n, lost))
    if sv["double_faults"]:
        fs = (f"; only {sv['first_serve_in_pct']}% of first serves went in"
              if sv["first_serve_in_pct"] is not None else "")
        W.append(_pattern("double_faults", "weakness", "headline", "Double faults",
                          f"{sv['double_faults']} double faults in {sv['points_served']} service points{fs}.",
                          sv["double_faults"], sv["double_faults"], sv["points_served"]))
    if s["lost_by"]["opponent_winners"]:
        n = s["lost_by"]["opponent_winners"]
        W.append(_pattern("opponent_winners", "weakness", "headline", "Beaten by shots they couldn't return",
                          f"{n} of {lost} points lost were opponent shots they didn't get back.", n, n, lost))

    # ---- headline strengths (partition of points won) ---------------------
    wb = s["won_by"]
    if wb["winners"]:
        S.append(_pattern("winners", "strength", "headline", "Hitting shots the opponent can't return",
                          f"{wb['winners']} of {won} points won were rally shots the opponent didn't get back.",
                          wb["winners"], wb["winners"], won))
    if wb["aces"]:
        S.append(_pattern("aces", "strength", "headline", "Unreturned serves",
                          f"{wb['aces']} of {won} points won were serves the opponent didn't return.",
                          wb["aces"], wb["aces"], won))
    if wb["opponent_errors"]:
        S.append(_pattern("draws_errors", "strength", "headline",
                          "Keeping the ball in play until the opponent misses",
                          f"{wb['opponent_errors']} of {won} points won came from opponent errors in a rally.",
                          wb["opponent_errors"], wb["opponent_errors"], won))

    # ---- context insights --------------------------------------------------
    if sv["first_serves"]:
        fs_in = sv["first_serve_in_pct"]
        if fs_in is not None and fs_in < 60:
            n2 = sv["second_serve_points"]
            l2 = n2 - round((sv["second_serve_points_won_pct"] or 0) * n2 / 100)
            W.append(_pattern("first_serve_pct", "weakness", "context", "Missing first serves",
                              f"Only {sv['first_serves'] - sv['first_serve_faults']} of {sv['first_serves']} first serves "
                              f"went in ({fs_in}%)" + (f"; lost {l2} of {n2} points played on a second serve." if n2 else "."),
                              max(l2, 0), sv["first_serve_faults"], sv["first_serves"]))
        elif fs_in is not None and fs_in >= 65:  # noqa
            S.append(_pattern("first_serve_pct", "strength", "context", "Reliable first serve",
                              f"{fs_in}% of first serves went in.", 0,
                              sv["first_serves"] - sv["first_serve_faults"], sv["first_serves"]))
        pw = sv["service_points_won_pct"]
        n = round((pw or 0) * sv["points_served"] / 100)
        if pw is not None and pw >= 55:
            S.append(_pattern("serve_points", "strength", "context", "Winning on serve",
                              f"Won {pw}% of service points ({n} of {sv['points_served']}).", n, n, sv["points_served"]))
        elif pw is not None and pw < 45:
            W.append(_pattern("serve_points", "weakness", "context", "Losing on serve",
                              f"Won only {pw}% of service points ({n} of {sv['points_served']}).",
                              sv["points_served"] - n, sv["points_served"] - n, sv["points_served"]))
    if rt["return_points"]:
        pw = rt["return_points_won_pct"]
        n = round((pw or 0) * rt["return_points"] / 100)
        if pw is not None and pw >= 50:
            S.append(_pattern("return_points", "strength", "context", "Winning on return",
                              f"Won {pw}% of return points ({n} of {rt['return_points']}).", n, n, rt["return_points"]))
    for b, label in (("short", f"short points ({SHORT_MAX} shots or fewer)"), ("long", f"long rallies ({LONG_MIN}+ shots)")):
        played, w = rl[b]["played"], rl[b]["won"]
        if played and (played - w) / played >= 0.6:
            W.append(_pattern(f"rally_{b}", "weakness", "context", f"Losing {label}",
                              f"Lost {played - w} of {played} {label}.", played - w, played - w, played))
        elif played and w / played >= 0.6:
            S.append(_pattern(f"rally_{b}", "strength", "context", f"Winning {label}",
                              f"Won {w} of {played} {label}.", w, w, played))

    def rank(lst):
        out = []
        for tier in ("headline", "context"):
            t = [p for p in lst if p["tier"] == tier]
            ranked = sorted([p for p in t if not p["low_sample"]], key=lambda p: (-p["points"], -p["occurrences"]))
            for i, p in enumerate(ranked):
                p["rank"] = i + 1
                p["top"] = tier == "headline" and i < TOP_N
            out += ranked + [p for p in t if p["low_sample"]]
        return out
    return rank(W), rank(S)


def _playstyle(s):
    # Position comes from the player's tracked feet. The shot-type "volley"
    # label is NOT used: it means "no bounce detected before the hit", so
    # every missed bounce makes a false volley (job clip: 26% "volleys",
    # 0% of shots from inside the service line).
    tags, bits = [], []
    pos = s["position"]
    if pos["median_depth_behind_baseline_cm"] is not None and pos["hits_with_position"] >= 5:
        depth = pos["median_depth_behind_baseline_cm"]
        net = pos["net_share_pct"] or 0
        if net >= 35:
            tags.append("Net player")
            bits.append(f"comes forward a lot ({net}% of shots from inside the service line)")
        elif net >= 15:
            tags.append("All-court player")
            bits.append(f"mixes baseline play with trips forward ({net}% of shots from inside the service line)")
        else:
            tags.append("Baseline player")
            where = ("right around the baseline" if abs(depth) < 75 else
                     f"about {round(abs(depth) / 100)} big steps {'behind' if depth >= 0 else 'inside'} the baseline")
            bits.append(f"stays back, typically hitting from {where}")
    rl = s["rally_length"]
    played = sum(v["played"] for v in rl.values())
    if played >= MIN_SAMPLE:
        short_share = rl["short"]["played"] / played
        if short_share >= 0.7:
            tags.append("Short points")
            bits.append(f"most points ({round(100 * short_share)}%) are over within {SHORT_MAX} shots")
        elif rl["long"]["played"] / played >= 0.3:
            tags.append("Grinder")
            bits.append("plays plenty of long rallies")
    errs = s["lost_by"]["own_errors"]
    if sum(errs.values()) >= MIN_OCCURRENCES:
        top = max(errs, key=errs.get)
        bits.append(f"misses most often {ERROR_WORDS.get(top, top)}")
    sv = s["serve"]
    if sv["first_serves"] >= MIN_SAMPLE and sv["first_serve_in_pct"] is not None:
        bits.append(f"lands {sv['first_serve_in_pct']}% of first serves")
    summary = (tags[0] + ": " if tags else "") + "; ".join(bits)
    return {"tags": tags, "summary": (summary[0].upper() + summary[1:] + ".") if summary else
            "Not enough tracked points to describe a playstyle yet."}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("events")
    ap.add_argument("--match", help="match_data.csv (player positions)")
    ap.add_argument("--names", help="comma-separated: player at the near end at the start, then far")
    ap.add_argument("--out")
    ap.add_argument("--fps", type=float, help="video frame rate: adds video times for each pattern")
    a = ap.parse_args()
    names = {}
    if a.names:
        n = [x.strip() for x in a.names.split(",")]
        names = {PLAYERS[i]: n[i] for i in range(min(2, len(n))) if n[i]}
    match_df = pd.read_csv(a.match) if a.match else None
    prof = build_profiles(pd.read_csv(a.events), match_df, names, fps=a.fps)
    text = json.dumps(prof, indent=2, default=str)
    if a.out:
        open(a.out, "w", encoding="utf-8").write(text)
    print(text)


if __name__ == "__main__":
    main()
