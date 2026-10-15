"""
court_detect.py

Finds the tennis court in one frame (camera behind one baseline) so the player
doesn't have to tap 7 points: the app pre-places them and the player only
checks the lines and drags any point that is off (2026-10-14).

How it works (classic line-based court fitting, no trained model):
1. White-line mask: pixels whiter than their surroundings (a "top-hat" on the
   darkest colour channel), so the painted lines stay and large white areas
   (walls, sky, shirts) mostly drop out.
2. Straight segments (Hough) are merged into lines and split into two
   families: across the court (baselines, service lines) and along it
   (sidelines).
3. Every pairing of two "across" lines with two "along" lines, matched to
   every pairing of real court lines, gives 4 corners -> a court-to-image
   homography. Each guess is scored by how much of the whole painted court
   it puts on white pixels.
4. The best guess is refined by snapping its projected lines to nearby white
   pixels and refitting.

Court coordinates (cm) as in calibration.py / config.py: x = depth from the
near baseline (0..2377), y = across from the camera-left SINGLES sideline
(0..823); doubles sidelines at -137 and 960.

detect_court(frame_bgr) -> dict with "points" (the 7 calibration points in
frame pixels), "score" (0..1, share of the court's lines found on white
paint), "ok" (score high enough to pre-place), "H" (court -> image).

Run directly to test on an image and write an overlay next to it:
    python Code/court_detect.py path/to/frame.jpg [out.jpg]
"""

import itertools
import sys

import cv2
import numpy as np

COURT_W, COURT_H, SERVICE, ALLEY = 2377.0, 823.0, 549.0, 137.0
NET = COURT_W / 2
ACROSS = [0.0, SERVICE, COURT_W - SERVICE, COURT_W]          # x of baselines and service lines
ALONG = [-ALLEY, 0.0, COURT_H, COURT_H + ALLEY]              # y of doubles/singles sidelines
OK_SCORE = 0.85                                              # tested 10-14: right fits 0.89-0.94, a wrong one 0.70; below this the app falls back to tapping

# Painted lines (court cm) used for scoring and refinement.
PAINTED = [
    ((0, -ALLEY), (COURT_W, -ALLEY)), ((0, COURT_H + ALLEY), (COURT_W, COURT_H + ALLEY)),   # doubles sidelines
    ((0, 0), (COURT_W, 0)), ((0, COURT_H), (COURT_W, COURT_H)),                             # singles sidelines
    ((0, -ALLEY), (0, COURT_H + ALLEY)), ((COURT_W, -ALLEY), (COURT_W, COURT_H + ALLEY)),   # baselines
    ((SERVICE, 0), (SERVICE, COURT_H)), ((COURT_W - SERVICE, 0), (COURT_W - SERVICE, COURT_H)),  # service lines
    ((SERVICE, COURT_H / 2), (COURT_W - SERVICE, COURT_H / 2)),                             # centre service line
]

POINTS = {   # the 7 calibration points (calibration.EXTENDED_POINT_LABELS)
    "baseline_near_left": (0, 0), "baseline_near_right": (0, COURT_H),
    "baseline_far_right": (COURT_W, COURT_H), "baseline_far_left": (COURT_W, 0),
    "service_line_near_left": (SERVICE, 0), "service_line_near_right": (SERVICE, COURT_H),
    "net_center": (NET, COURT_H / 2),
}

WORK_W = 1280   # detection runs on a copy this wide


def _samples(step=20.0):
    pts = []
    for (x1, y1), (x2, y2) in PAINTED:
        n = max(2, int(np.hypot(x2 - x1, y2 - y1) / step))
        t = np.linspace(0, 1, n)
        pts.append(np.stack([x1 + (x2 - x1) * t, y1 + (y2 - y1) * t], 1))
    return np.concatenate(pts).astype(np.float64)


SAMPLES = _samples()
# The near half is always clearest (the far half hides behind the net, its band and the far wall),
# so it counts double.
WEIGHTS = np.where(SAMPLES[:, 0] < NET, 2.0, 1.0)


def white_line_mask(img):
    """Thin, whiter-than-surroundings pixels."""
    darkest = img.min(axis=2)                       # white is bright in every channel; blue/green court is not
    k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (15, 15))
    tophat = cv2.morphologyEx(darkest, cv2.MORPH_TOPHAT, k)
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    # Lines in shade look bluish (lit by the sky), so strong top-hat pixels may be more saturated.
    mask = (((tophat > 35) & (hsv[..., 1] < 90)) | ((tophat > 55) & (hsv[..., 1] < 150))).astype(np.uint8)
    # Painted lines are thin and sparse; leaves, fences and brick walls make dense white texture.
    density = cv2.boxFilter(mask.astype(np.float32), -1, (25, 25))
    return ((mask > 0) & (density < 0.3)).astype(np.uint8) * 255


def _line_from_segment(x1, y1, x2, y2):
    """(a, b, c) with a*x + b*y = c, (a, b) unit normal."""
    a, b = y2 - y1, x1 - x2
    n = np.hypot(a, b)
    a, b = a / n, b / n
    return np.array([a, b, a * x1 + b * y1])


def find_lines(mask):
    segs = cv2.HoughLinesP(mask, 1, np.pi / 360, threshold=50, minLineLength=45, maxLineGap=10)
    if segs is None:
        return [], []
    groups = []   # each: {"theta", "rho", "pts": [...], "len"}
    for x1, y1, x2, y2 in segs.reshape(-1, 4).astype(float):
        ln = _line_from_segment(x1, y1, x2, y2)
        if ln[1] < 0 or (ln[1] == 0 and ln[0] < 0):
            ln = -ln
        theta, rho = np.arctan2(ln[1], ln[0]), ln[2]
        length = np.hypot(x2 - x1, y2 - y1)
        for g in groups:
            if abs(theta - g["theta"]) < np.radians(1.5) and abs(rho - g["rho"]) < 6:
                g["pts"] += [(x1, y1), (x2, y2)]
                g["len"] += length
                break
        else:
            groups.append({"theta": theta, "rho": rho, "pts": [(x1, y1), (x2, y2)], "len": length})
    across, along = [], []
    for g in groups:
        p = np.array(g["pts"], np.float32)
        vx, vy, x0, y0 = cv2.fitLine(p, cv2.DIST_L2, 0, 0.01, 0.01).ravel()
        ln = _line_from_segment(x0, y0, x0 + vx, y0 + vy)
        tilt = np.degrees(np.arctan2(abs(vy), abs(vx)))   # 0 = horizontal in the image
        (across if tilt < 14 else along if tilt > 16 else []).append((g["len"], ln))
    across.sort(key=lambda t: -t[0])
    along.sort(key=lambda t: -t[0])
    return [l for _, l in across[:16]], [l for _, l in along[:12]]


def _meet(l1, l2):
    A = np.array([l1[:2], l2[:2]])
    if abs(np.linalg.det(A)) < 1e-6:
        return None
    return np.linalg.solve(A, np.array([l1[2], l2[2]]))


def _project(H, pts):
    p = np.hstack([pts, np.ones((len(pts), 1))]) @ H.T
    return p[:, :2] / p[:, 2:3]


def _score(H, hit, w, h):
    p = _project(H, SAMPLES)
    inside = (p[:, 0] >= 0) & (p[:, 0] < w) & (p[:, 1] >= 0) & (p[:, 1] < h)
    if inside.sum() < len(SAMPLES) * 0.4:          # most of the court must be in view
        return -1e9, 0.0
    q = p[inside].astype(int)
    # Each pixel counts once, so a court squeezed onto a few white pixels can't score well.
    q, first = np.unique(q[:, 1] * w + q[:, 0], return_index=True)
    wt = WEIGHTS[inside][first]
    on = hit.ravel()[q] > 0
    hits = float(wt[on].sum())
    return hits - 0.5 * float(wt[~on].sum()), hits / float(wt.sum())


def _plausible(H, w, h):
    """A camera behind one baseline: near baseline low in the picture and wide, far baseline
    higher and narrower (but not a sliver), court roughly centred, net between them."""
    c = _project(H, np.array([[0, 0], [0, COURT_H], [COURT_W, COURT_H], [COURT_W, 0], [NET, COURT_H / 2]]))
    near_w, far_w = c[1, 0] - c[0, 0], c[2, 0] - c[3, 0]
    near_y, far_y = (c[0, 1] + c[1, 1]) / 2, (c[2, 1] + c[3, 1]) / 2
    mid_x = (c[0, 0] + c[1, 0] + c[2, 0] + c[3, 0]) / 4
    return (near_w > w * 0.25 and 0.15 * near_w < far_w < 0.95 * near_w
            and near_y > h * 0.35 and near_y - far_y > h * 0.15 and far_y > -h * 0.05
            and -0.1 * w < mid_x < 1.1 * w and far_y < c[4, 1] < near_y)


CORNERS = np.array([[0, 0], [0, COURT_H], [COURT_W, COURT_H], [COURT_W, 0]], np.float32)


def _refine(H, hit, w, h):
    """Nudge the four court corners in the picture, a few pixels at a time, keeping each
    nudge that puts more of the painted court on white (finer mask than the search)."""
    img = _project(H, CORNERS.astype(float)).astype(np.float32)
    best = _score(H, hit, w, h)[0]
    for step in (6, 3, 2, 1, 0.5):
        improved = True
        while improved:
            improved = False
            for k in range(8):
                for d in (step, -step):
                    trial = img.copy()
                    trial[k // 2, k % 2] += d
                    H2 = cv2.getPerspectiveTransform(CORNERS, trial).astype(np.float64)
                    if not _plausible(H2, w, h):
                        continue
                    sc = _score(H2, hit, w, h)[0]
                    if sc > best:
                        best, img, H, improved = sc, trial, H2, True
    return H


def detect_court(frame_bgr):
    h0, w0 = frame_bgr.shape[:2]
    s = WORK_W / w0
    img = cv2.resize(frame_bgr, (WORK_W, int(round(h0 * s))), interpolation=cv2.INTER_AREA)
    h, w = img.shape[:2]
    white = white_line_mask(img)
    hit = cv2.dilate(white, np.ones((5, 5), np.uint8))
    across, along = find_lines(white)
    best = (-1e9, None)
    model_across = list(itertools.combinations(range(4), 2))
    model_along = list(itertools.combinations(range(4), 2))
    for a1, a2 in itertools.combinations(across, 2):
        # lower line in the image = nearer the camera
        ya = lambda l: (l[2] - l[0] * w / 2) / l[1] if abs(l[1]) > 1e-6 else 1e9
        near_l, far_l = (a1, a2) if ya(a1) > ya(a2) else (a2, a1)
        for s1, s2 in itertools.combinations(along, 2):
            ref_y = ya(near_l)
            xa = lambda l: (l[2] - l[1] * ref_y) / l[0] if abs(l[0]) > 1e-6 else 1e9
            left_l, right_l = (s1, s2) if xa(s1) < xa(s2) else (s2, s1)
            corners = [_meet(near_l, left_l), _meet(near_l, right_l), _meet(far_l, right_l), _meet(far_l, left_l)]
            if any(c is None for c in corners):
                continue
            img_pts = np.array(corners, np.float32)
            for i, j in model_across:
                for k, m in model_along:
                    court_pts = np.array([[ACROSS[i], ALONG[k]], [ACROSS[i], ALONG[m]],
                                          [ACROSS[j], ALONG[m]], [ACROSS[j], ALONG[k]]], np.float32)
                    H = cv2.getPerspectiveTransform(court_pts, img_pts).astype(np.float64)
                    if not _plausible(H, w, h):
                        continue
                    sc, _ = _score(H, hit, w, h)
                    if sc > best[0]:
                        best = (sc, H)
    if best[1] is None:
        return {"ok": False, "score": 0.0, "points": None, "H": None}
    fine = cv2.dilate(white, np.ones((3, 3), np.uint8))
    H = _refine(best[1], fine, w, h)
    _, frac = _score(H, hit, w, h)
    S = np.diag([1 / s, 1 / s, 1.0])                 # back to full-size pixels
    H_full = S @ H
    H_full /= H_full[2, 2]
    pts = _project(H_full, np.array(list(POINTS.values())))
    return {"ok": frac >= OK_SCORE, "score": round(float(frac), 3), "H": H_full,
            "points": {k: [round(float(x), 1), round(float(y), 1)] for k, (x, y) in zip(POINTS, pts)}}


def draw(frame_bgr, result):
    out = frame_bgr.copy()
    if result["H"] is None:
        return out
    for a, b in PAINTED:
        p = _project(result["H"], np.array([a, b], float)).astype(int)
        cv2.line(out, tuple(p[0]), tuple(p[1]), (238, 211, 34), 3)
    for name, (x, y) in result["points"].items():
        cv2.circle(out, (int(x), int(y)), 12, (128, 222, 74), -1)
    cv2.putText(out, f"score {result['score']}", (40, 80), cv2.FONT_HERSHEY_SIMPLEX, 2.2, (255, 255, 255), 5)
    return out


if __name__ == "__main__":
    import time
    path = sys.argv[1]
    frame = cv2.imread(path)
    t0 = time.time()
    res = detect_court(frame)
    print(f"ok={res['ok']} score={res['score']} in {time.time() - t0:.1f}s")
    if res["points"]:
        for k, v in res["points"].items():
            print(f"  {k}: {v}")
    out = sys.argv[2] if len(sys.argv) > 2 else path.rsplit(".", 1)[0] + "_court.jpg"
    cv2.imwrite(out, draw(frame, res))
    print("overlay:", out)
