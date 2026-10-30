"""
aim_guide.py

Hands-free aiming (2026-10-29): the phone is up on the fence where nobody can see
its screen, so the page sends a small camera picture every few seconds and says
the answer out loud ("Tilt the phone up a little", "Good spot"). Uses the court
finder (court_detect.py) and then checks where the court sits in the picture.

aim_check(frame_bgr, doubles=False, feet=None) -> {"ok": bool, "code": str, "tip": str,
    "score": float, "points": the 7 marking points or None, "on_court": players or None,
    "H": the court fit (court cm -> picture) or None; not for the page}
"ok" is True only when the court is in view, the court finder is confident, and
the court is roughly centred and level: the same picture can then be used for
court marking without anyone checking it. Doubles (2026-10-29): the alleys are in
play, so the outer sidelines must be in view from the near service line on (the
near outer corners themselves often sit just off the picture, as in singles).

Doubles detection: `feet` are the bottom-middle points of the people the person
detector found (pixels). players_on_court counts those standing on the court
(alleys plus a margin behind the baselines); 3 or more means doubles.

Codes (one tip at a time, most important first): portrait, no_court, tilt_up,
tilt_down, too_close, turn_left, turn_right, too_small, level, unsure, good.

Run directly on a picture:  python Code/aim_guide.py frame.jpg
"""

import sys

import numpy as np

import court_detect as cd

# Corners that must be in view, court cm: near-left, near-right, far-right, far-left.
# Near: the singles corners (from the usual spot the near alleys often run off the sides,
# and court marking already allows that). Far: the outer (doubles) corners.
OUTER = np.array([[0, 0], [0, cd.COURT_H],
                  [cd.COURT_W, cd.COURT_H + cd.ALLEY], [cd.COURT_W, -cd.ALLEY]], float)
# Doubles also: where the near service line meets the outer sidelines (left, right).
DOUBLES_SIDES = np.array([[cd.SERVICE, -cd.ALLEY], [cd.SERVICE, cd.COURT_H + cd.ALLEY]], float)
BEHIND = 300.0       # cm behind each baseline still counted as on court (returners stand back)
BESIDE = 150.0       # cm outside the doubles sidelines still counted
DOUBLES_PLAYERS = 3  # this many on court -> doubles (one may be hidden behind another)
EDGE = 0.02          # corners must sit this far inside the picture (share of width/height)
CENTRE_OFF = 0.12    # court centre further than this from the picture centre -> turn
MIN_NEAR_W = 0.45    # near baseline narrower than this share of the width -> court too small
MAX_TILT_DEG = 4.0   # near baseline sloping more than this -> phone not level

TIPS = {
    "portrait": "Turn the phone sideways.",
    "no_court": "I can't see the court yet. Point the phone at the whole court from behind the baseline.",
    "tilt_up": "The far end is cut off. Tilt the phone up a little.",
    "tilt_down": "The near baseline is cut off. Tilt the phone down a little.",
    "too_close": "Both ends are cut off. Move the phone higher or further back.",
    "turn_left": "The court is cut off on the left. Turn the phone a little to the left.",
    "turn_right": "The court is cut off on the right. Turn the phone a little to the right.",
    "too_small": "The court looks small. Put the phone on the back fence, centred behind the baseline.",
    "level": "The phone is tilted sideways. Level it.",
    "unsure": "Almost. Hold still for a moment.",
    "good": "Good spot. Hold still.",
}


def _answer(code, score=0.0, points=None):
    return {"ok": code == "good", "code": code, "tip": TIPS[code], "score": round(float(score), 3), "points": points,
            "on_court": None, "H": None}


def players_on_court(H, feet):
    """How many of the feet points (image pixels) stand on the court, given H (court cm -> image)."""
    if H is None or feet is None or len(feet) == 0:
        return 0
    c = cd._project(np.linalg.inv(np.asarray(H, float)), np.asarray(feet, float).reshape(-1, 2))
    inside = ((c[:, 0] > -BEHIND) & (c[:, 0] < cd.COURT_W + BEHIND)
              & (c[:, 1] > -cd.ALLEY - BESIDE) & (c[:, 1] < cd.COURT_H + cd.ALLEY + BESIDE))
    return int(inside.sum())


def aim_check(frame_bgr, doubles=False, feet=None):
    h, w = frame_bgr.shape[:2]
    if h > w:
        return _answer("portrait")
    res = cd.detect_court(frame_bgr)
    if res["H"] is None:
        return _answer("no_court")
    out = _aim(res, w, h, doubles)
    out["H"] = res["H"]
    if feet is not None:
        out["on_court"] = players_on_court(res["H"], feet)
    return out


def _aim(res, w, h, doubles):
    c = cd._project(res["H"], OUTER)
    x, y = c[:, 0] / w, c[:, 1] / h
    # An unsure fit with a corner hugging the edge usually means the real line is just past it
    # (the finder took the next line in), so the margin is wider then.
    edge = EDGE if res["ok"] else 3 * EDGE
    near_cut = (y[0] > 1 - edge) or (y[1] > 1 - edge)
    far_cut = (y[2] < edge) or (y[3] < edge)
    if near_cut and far_cut:
        return _answer("too_close", res["score"])
    if far_cut:
        return _answer("tilt_up", res["score"])
    if near_cut:
        return _answer("tilt_down", res["score"])
    left_cut = (x[0] < EDGE) or (x[3] < EDGE)
    right_cut = (x[1] > 1 - EDGE) or (x[2] > 1 - EDGE)
    if doubles:
        sx = cd._project(res["H"], DOUBLES_SIDES)[:, 0] / w
        left_cut |= sx[0] < EDGE
        right_cut |= sx[1] > 1 - EDGE
    if left_cut and right_cut:
        return _answer("too_close", res["score"])
    if left_cut:
        return _answer("turn_left", res["score"])
    if right_cut:
        return _answer("turn_right", res["score"])
    mid = x.mean()
    if mid < 0.5 - CENTRE_OFF:
        return _answer("turn_left", res["score"])
    if mid > 0.5 + CENTRE_OFF:
        return _answer("turn_right", res["score"])
    if x[1] - x[0] < MIN_NEAR_W:
        return _answer("too_small", res["score"])
    slope = np.degrees(np.arctan2(c[1, 1] - c[0, 1], c[1, 0] - c[0, 0]))
    if abs(slope) > MAX_TILT_DEG:
        return _answer("level", res["score"])
    if not res["ok"]:
        return _answer("unsure", res["score"])
    return _answer("good", res["score"], res["points"])


if __name__ == "__main__":
    import time

    import cv2
    t0 = time.time()
    out = aim_check(cv2.imread(sys.argv[1]), doubles="--doubles" in sys.argv)
    print(f"{out['code']} (score {out['score']}) in {time.time() - t0:.1f}s: {out['tip']}")
