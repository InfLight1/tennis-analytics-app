"""
player_appearance.py -- which player is at which end, by clothing colour
(2026-10-06).

scoring.score_match_near_far used to assume the players change ends every
odd game, counting games from DETECTED points. Points get missed, so the
swaps landed at the wrong moments, and in casual play nobody changes ends
at all (tennis1_clip2: the same player is at the near end for all 12
minutes). Either way one player's stats got filed under the other.

Here: for each rally, sample a few frames, take the colour of each player's
upper body (near end and far end), and compare with the two players'
reference colours from the first rallies. Returns {rally_id: swapped} where
swapped = player_1 is at the FAR end. Swaps are smoothed (a changeover lasts
a while; a single odd rally is noise). If the two outfits aren't clearly
different, returns None and scoring falls back to the game-count rule.
"""

import cv2
import numpy as np
import pandas as pd

import config

NET_X = config.NET_POSITION_OFFSET
FRAMES_PER_RALLY = 4
MIN_OUTFIT_DISTANCE = 18.0   # Lab units between the two players' reference colours
SMOOTH = 2                   # majority over +/-2 rallies


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


def rally_end_swaps(video_path, match_df, events_df):
    players = match_df[(match_df["type"] == "player") & match_df["table_x"].notna()]
    by_frame = {f: g for f, g in players.groupby("frame")}
    rallies = events_df.groupby("rally_id")["frame"].agg(["min", "max"]).sort_index()

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
        print(f"[appearance] outfits too similar ({np.linalg.norm(ref1 - ref2):.1f}); using game-count end swaps")
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
