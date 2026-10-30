"""
test_people_finder.py

Checks doubles detection (people_finder.py + aim_guide.players_on_court) on the
hand-checked test frame at the size hands-free sends (1280 wide): the singles
match must count 2 players on court, and the same picture with both players
copied to the other half of their end (a doubles-like picture) must count 4.
Skips if ultralytics, the test frame or yolov8n.pt isn't there.

Run directly:
    python Code/test_people_finder.py
"""

import os
import sys

import cv2

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
MAIN = os.path.join(HERE, "..", "..", "Tennis Performance App")
FRAME = next((p for p in [os.path.join(HERE, "..", "Diagnostics", "calib_test_frame_clip2.jpg"),
                          os.path.join(MAIN, "Diagnostics", "calib_test_frame_clip2.jpg")] if os.path.exists(p)), None)
MODEL = next((p for p in [os.path.join(HERE, "yolov8n.pt"), os.path.join(MAIN, "Code", "yolov8n.pt")]
              if os.path.exists(p)), None)

if __name__ == "__main__":
    try:
        import ultralytics  # noqa: F401
    except ImportError:
        print("SKIP: ultralytics not installed")
        sys.exit(0)
    if not FRAME or not MODEL:
        print("SKIP: test frame or yolov8n.pt not found")
        sys.exit(0)
    import aim_guide
    import people_finder

    img = cv2.resize(cv2.imread(FRAME), (1280, 720))
    feet = people_finder.feet(img, MODEL)
    found = aim_guide.aim_check(img, feet=feet)["on_court"]
    ok = found == 2
    print(f"{'PASS' if ok else 'FAIL'}  singles picture: {found} players on court, want 2")

    # Copy each player (box from the finder) across their end of the court.
    r = people_finder._models[MODEL].predict(img, imgsz=people_finder.IMGSZ, conf=people_finder.CONF,
                                             classes=[0], device="cpu", verbose=False)[0]
    dbl = img.copy()
    for x1, y1, x2, y2 in [[int(v) for v in b] for b in r.boxes.xyxy.tolist()]:
        shift = -int(0.35 * 1280) if x1 > 640 else int(0.08 * 1280)
        dbl[y1:y2, x1 + shift:x2 + shift] = img[y1:y2, x1:x2]
    found = aim_guide.aim_check(dbl, feet=people_finder.feet(dbl, MODEL))["on_court"]
    good = found == 4
    ok &= good
    print(f"{'PASS' if good else 'FAIL'}  doubles-like picture: {found} players on court, want 4")
    print("ALL PASS" if ok else "SOME FAILED")
    sys.exit(0 if ok else 1)
