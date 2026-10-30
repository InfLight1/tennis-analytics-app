"""
test_aim_guide.py

Checks the hands-free aiming tips (aim_guide.py) on the hand-checked test frame
Diagnostics/calib_test_frame_clip2.jpg (skips if that local file isn't there):
the real view must be "good", and pictures cut or shifted from it must get the
right tip (far end cut off -> tilt up, and so on). The same in doubles, plus the
player count used to notice a doubles match (feet placed on and off the court).

Run directly:
    python Code/test_aim_guide.py
"""

import os
import sys
import time

import cv2
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import aim_guide  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
FRAME_CANDIDATES = [os.path.join(HERE, "..", "Diagnostics", "calib_test_frame_clip2.jpg"),
                    os.path.join(HERE, "..", "..", "Tennis Performance App", "Diagnostics", "calib_test_frame_clip2.jpg")]


def shifted(img, dx, dy):
    """The same view with the camera aimed elsewhere: content moved by (dx, dy) share of the picture."""
    h, w = img.shape[:2]
    M = np.float32([[1, 0, dx * w], [0, 1, dy * h]])
    return cv2.warpAffine(img, M, (w, h), borderValue=(40, 40, 40))


if __name__ == "__main__":
    path = next((p for p in FRAME_CANDIDATES if os.path.exists(p)), None)
    if not path:
        print("SKIP: test frame not found")
        sys.exit(0)
    img = cv2.imread(path)
    cases = [
        ("real view", img, {"good"}),
        ("phone upright", cv2.rotate(img, cv2.ROTATE_90_CLOCKWISE), {"portrait"}),
        ("aimed too low (far end cut off)", shifted(img, 0, -0.30), {"tilt_up"}),
        ("aimed too high (near baseline cut off)", shifted(img, 0, 0.35), {"tilt_down", "no_court"}),
        ("aimed too far left (court cut off on the right)", shifted(img, 0.30, 0), {"turn_right"}),
        ("aimed too far right (court cut off on the left)", shifted(img, -0.30, 0), {"turn_left"}),
        ("blank picture", np.full_like(img, 90), {"no_court"}),
    ]
    cases += [(f"doubles: {n}", f, w, True) for n, f, w in cases if n != "phone upright"]
    ok = True
    for name, frame, want, *dbl in cases:
        t0 = time.time()
        out = aim_guide.aim_check(frame, doubles=bool(dbl))
        good = out["code"] in want
        ok &= good
        print(f"{'PASS' if good else 'FAIL'}  {name}: {out['code']} (score {out['score']}, {time.time() - t0:.1f}s), want {sorted(want)}")
    # Doubles detection: feet put at court spots (cm) through the court the finder found.
    import court_detect as cd
    H = cd.detect_court(img)["H"]
    at = lambda *spots: cd._project(H, np.array(spots, float)).tolist()
    count_cases = [
        ("singles: one player each end", at((-80, 400), (2450, 500)), 2),
        ("doubles: four players, two in the alleys", at((-50, -60), (-50, 700), (1800, 880), (2300, 100)), 4),
        ("someone at the back fence and one beside the court", at((-600, 400), (1000, 1300)), 0),
    ]
    for name, feet, want in count_cases:
        out = aim_guide.aim_check(img, feet=feet)
        good = out["on_court"] == want
        ok &= good
        print(f"{'PASS' if good else 'FAIL'}  players on court, {name}: {out['on_court']}, want {want}")
    print("ALL PASS" if ok else "SOME FAILED")
    sys.exit(0 if ok else 1)
