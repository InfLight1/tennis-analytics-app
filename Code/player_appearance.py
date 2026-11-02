"""
player_appearance.py -- which player is at which end (2026-10-06; walking
across the net added 2026-11-01).

scoring.score_match_near_far used to assume the players change ends every
odd game, counting games from DETECTED points. Points get missed, so the
swaps landed at the wrong moments, and in casual play nobody changes ends
at all (tennis1_clip2: the same player is at the near end for all 12
minutes). Either way one player's stats got filed under the other.

Two signals, best first:
1. Walking past the net. Players are tracked between points too, so a
   changeover shows up as a player track that goes from one half to the
   other in the break between two points. Works when both players wear the
   same colours. On tennis1_clip2 (no changeovers, 54 breaks) no track ever
   crossed; the closest anyone came to the net between points was 58 cm.
2. Clothing colour: for each rally, sample a few frames, take the colour of
   each player's upper body (near end and far end), and compare with the
   two players' reference colours from the first rallies. Swaps are
   smoothed (a single odd rally is noise).

rally_end_swaps returns {rally_id: swapped} where swapped = player_1 is at
the FAR end, or None when neither signal can be trusted; scoring then falls
back to the game-count rule.
"""

import cv2
import numpy as np
import pandas as pd

import config

NET_X = config.NET_POSITION_OFFSET
FRAMES_PER_RALLY = 4
MIN_OUTFIT_DISTANCE = 18.0   # Lab units between the two players' reference colours
SMOOTH = 2                   # majority over +/-2 rallies

CROSS_MARGIN_CM = 200        # a crossing track is seen this far past the net on both sides
SIDE_MARGIN_CM = 600         # people further outside the sidelines (other courts) are ignored
LONG_BREAK_S = 30            # breaks this long can be changeovers (between points: ~12 s)
MIN_SEEN_SHARE = 0.6         # "no crossing" only counts if players were tracked this much of a long break


def _torso_colour(frame, box):
    x1, y1, x2, y2 = [int(round(v)) for v in box]
    h, w = y2 - y1, x2 - x1
    if h < 20 or w < 8:
        return None
    # upper body: 20-50% of the box height, middle 60% of its width
    crop = frame[max(y1 + int(0.2 * h), 0):max(y1 + int(0.5 * h), 1),
                 max(x1 + int(0.2 * w), 0):max(x1 + int(0.8 * w), 1)]
    if crop.size == 0:
        return None
    lab = cv2.cvtColor(crop, cv2.COLOR_BGR2LAB).reshape(-1, 3).astype(float)
    return np.median(lab, axis=0)


def _rally_spans(events_df):
    return events_df.groupby("rally_id")["frame"].agg(["min", "max"]).sort_index()


def net_crossings(match_df, events_df, fps=30.0):
    """For each break between two rallies: who walked past the net.
    Returns ({rally_id_after_the_break: "strong" | "weak"}, breaks_seen_ok)
    strong = tracks crossed in both directions (both players changed ends),
    weak = one direction only, in a break long enough to be a changeover.
    breaks_seen_ok = players were tracked through every long break, so
    finding no crossing really means nobody changed ends."""
    players = match_df[(match_df["type"] == "player") & match_df["table_x"].notna()
                       & match_df["table_y"].between(-SIDE_MARGIN_CM, config.TABLE_H + SIDE_MARGIN_CM)]
    spans = _rally_spans(events_df)
    out, seen_ok = {}, True
    for (_, prev), (rid, nxt) in zip(spans.iloc[:-1].iterrows(), spans.iloc[1:].iterrows()):
        lo, hi = prev["max"], nxt["min"]
        g = players[(players["frame"] > lo) & (players["frame"] < hi)]
        long_break = (hi - lo) / fps >= LONG_BREAK_S
        if long_break and g["frame"].nunique() < MIN_SEEN_SHARE * (hi - lo - 1):
            seen_ok = False
        dirs = set()
        for _, t in g.sort_values("frame").groupby("track_id"):
            x = t["table_x"].to_numpy()
            if x.min() < NET_X - CROSS_MARGIN_CM and x.max() > NET_X + CROSS_MARGIN_CM:
                dirs.add(1 if x[-1] > x[0] else -1)
        if len(dirs) == 2:
            out[int(rid)] = "strong"
        elif dirs and long_break:
            out[int(rid)] = "weak"
    return out, seen_ok


def _colour_swaps(video_path, match_df, events_df):
    players = match_df[(match_df["type"] == "player") & match_df["table_x"].notna()]
    by_frame = {f: g for f, g in players.groupby("frame")}
    rallies = _rally_spans(events_df)

    cap = cv2.VideoCapture(str(video_path))
    sigs = {}
    try:
        for rid, (lo, hi) in rallies.iterrows():
            near, far = [], []
            for f in np.linspace(lo, hi, FRAMES_PER_RALLY).astype(int):
                g = by_frame.get(int(f))
                if g is None:
                    continue
                cap.set(cv2.CAP_PROP_POS_FRAMES, int(f))
                ok, frame = cap.read()
                if not ok:
                    continue
                for half, out in ((g[g["table_x"] < NET_X], near), (g[g["table_x"] >= NET_X], far)):
                    if len(half):
                        r = half.loc[((half["x2"] - half["x1"]) * (half["y2"] - half["y1"])).idxmax()]
                        c = _torso_colour(frame, (r["x1"], r["y1"], r["x2"], r["y2"]))
                        if c is not None:
                            out.append(c)
            if near and far:
                sigs[int(rid)] = (np.median(near, axis=0), np.median(far, axis=0))
    finally:
        cap.release()

    if len(sigs) < 3:
        return None
    ids = sorted(sigs)
    # references: player_1 = near at the start (first few rallies)
    ref1 = np.median([sigs[r][0] for r in ids[:3]], axis=0)
    ref2 = np.median([sigs[r][1] for r in ids[:3]], axis=0)
    if np.linalg.norm(ref1 - ref2) < MIN_OUTFIT_DISTANCE:
        print(f"[appearance] outfits too similar ({np.linalg.norm(ref1 - ref2):.1f})")
        return None

    raw = {}
    for r in ids:
        n, f = sigs[r]
        same = np.linalg.norm(n - ref1) + np.linalg.norm(f - ref2)
        flip = np.linalg.norm(n - ref2) + np.linalg.norm(f - ref1)
        raw[r] = flip < same
    vals = [raw[r] for r in ids]
    swaps = {}
    for i, r in enumerate(ids):
        win = vals[max(0, i - SMOOTH):i + SMOOTH + 1]
        swaps[r] = sum(win) * 2 > len(win)
    # rallies without a reading inherit the nearest earlier one
    out, last = {}, False
    for rid in rallies.index:
        last = swaps.get(int(rid), last)
        out[int(rid)] = bool(last)
    print(f"[appearance] outfit distance {np.linalg.norm(ref1 - ref2):.1f}; "
          f"player 1 at the far end in {sum(out.values())} of {len(out)} rallies")
    return out


def combine(rally_ids, crossings, seen_ok, colour):
    """rally_ids in order; crossings/seen_ok from net_crossings; colour from
    _colour_swaps (or None). Walking past the net wins when it was seen
    (it can't be fooled by light or matching outfits); a weak crossing
    counts only if the colour agrees or there's no colour to ask."""
    if crossings:
        out, swapped = {}, False
        for rid in rally_ids:
            kind = crossings.get(int(rid))
            if kind == "strong" or (kind == "weak" and (colour is None or colour.get(int(rid)) != swapped)):
                swapped = not swapped
            out[int(rid)] = swapped
        return out, "walk"
    if colour is not None:
        return colour, "colour"
    if seen_ok:
        # players were watched through every long break and nobody crossed
        return {int(r): False for r in rally_ids}, "walk"
    return None, "game count"


def rally_end_swaps(video_path, match_df, events_df, fps=None):
    if fps is None:
        cap = cv2.VideoCapture(str(video_path))
        fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
        cap.release()
    crossings, seen_ok = net_crossings(match_df, events_df, fps)
    colour = _colour_swaps(video_path, match_df, events_df)
    swaps, how = combine(list(_rally_spans(events_df).index), crossings, seen_ok, colour)
    changes = sum(1 for a, b in zip(list(swaps.values())[:-1], list(swaps.values())[1:]) if a != b) if swaps else None
    print(f"[appearance] ends: {how}; crossings {crossings}; changes of ends {changes}")
    return swaps
