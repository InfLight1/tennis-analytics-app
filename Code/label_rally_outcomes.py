"""
label_rally_outcomes.py

Point-level ground truth for the part of the pipeline that drives the
diagnosis: who won each point and how it ended. Same frame-stepping viewer
and frame numbering as label_ground_truth.py, so frames line up with
rally_events*.csv. Scored by evaluate_rally_outcomes.py.

Workflow per point:
    s  at the serve (ball toss / serve contact)  -> then n or f = who SERVED
    e  when the point is decided (ball dead)     -> then n or f = who WON
                                                 -> then how it ended:
         w = winner (in, not returned)   t = into the net
         l = long                         i = wide
         x = other / unsure (let, double bounce, can't see)

"near" = the player on the camera's side of the net during THAT point
(players change ends, so this is per point -- exactly what the pipeline's
near/far labels mean).

Navigation (window must be focused):
    d / RIGHT  next frame        a / LEFT  previous frame
    D / A      +/- 10 frames     J / K     +/- 100 frames
    u          undo last completed point (or cancel the one in progress)
    q / ESC    save and quit

Saved after every completed point, so closing the window loses nothing.
Label 20-30 points; skip warm-up/feeding with J.
"""

import csv
from pathlib import Path

import cv2

# ── Editable top-of-file variables (project convention: no CLI args) ──────
VIDEO_PATH = r"C:\Users\rudra\Downloads\Projects\Tennis Performance App\Videos\tennis1_clip2.mp4"
OUTPUT_CSV = str(Path(__file__).resolve().parent.parent / "ground_truth_points.csv")
DISPLAY_MAX_WIDTH = 1280

ENDINGS = {ord("w"): "winner", ord("t"): "net", ord("l"): "long", ord("i"): "wide", ord("x"): "other"}
SIDES = {ord("n"): "near", ord("f"): "far"}
FIELDS = ["point_id", "start_frame", "end_frame", "server", "winner", "ending"]


def _load(path):
    if not Path(path).exists():
        return []
    with open(path, newline="") as f:
        return [dict(r) for r in csv.DictReader(f)]


def _save(points, path):
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        for i, p in enumerate(points, 1):
            w.writerow({**p, "point_id": i})


def _put(img, text, y, color):
    cv2.putText(img, text, (10, y), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 0), 4, cv2.LINE_AA)
    cv2.putText(img, text, (10, y), cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 1, cv2.LINE_AA)


def main():
    cap = cv2.VideoCapture(VIDEO_PATH)
    if not cap.isOpened():
        raise RuntimeError(f"Could not open video: {VIDEO_PATH}")
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0

    points = _load(OUTPUT_CSV)
    if points:
        print(f"Resuming: {len(points)} points already in {OUTPUT_CSV}")
    current = None          # point in progress
    awaiting = None         # "server" | "winner" | "ending"
    frame_num = int(points[-1]["end_frame"]) + 1 if points else 0

    def read(n):
        n = max(0, min(n, total - 1))
        cap.set(cv2.CAP_PROP_POS_FRAMES, n)
        ok, fr = cap.read()
        return n, (fr if ok else None)

    frame_num, frame = read(frame_num)
    win = "Rally Outcome Labeler"
    cv2.namedWindow(win, cv2.WINDOW_NORMAL)

    while frame is not None:
        disp = frame.copy()
        h, w = disp.shape[:2]
        if w > DISPLAY_MAX_WIDTH:
            disp = cv2.resize(disp, (DISPLAY_MAX_WIDTH, int(h * DISPLAY_MAX_WIDTH / w)))
        _put(disp, f"Frame {frame_num}/{total - 1}  t={frame_num / fps:.2f}s   points labeled: {len(points)}", 28, (0, 255, 0))
        _put(disp, "d/a=+-1  D/A=+-10  J/K=+-100  s=serve  e=point over  u=undo  q=quit", 54, (0, 255, 0))
        prompt = {"server": "WHO SERVED?  n=near  f=far",
                  "winner": "WHO WON THE POINT?  n=near  f=far",
                  "ending": "HOW DID IT END?  w=winner  t=net  l=long  i=wide  x=other"}.get(awaiting)
        if current and not prompt:
            prompt = f"point in progress: serve@{current['start_frame']} by {current['server']} -- press e when it's over"
        if prompt:
            _put(disp, prompt, 84, (0, 220, 255))
        for k, p in enumerate(points[-4:]):
            _put(disp, f"#{len(points) - len(points[-4:]) + k + 1}: {p['start_frame']}-{p['end_frame']} "
                       f"serve {p['server']}, won by {p['winner']} ({p['ending']})",
                 disp.shape[0] - 90 + 22 * k, (255, 200, 0))
        cv2.imshow(win, disp)
        key = cv2.waitKey(0) & 0xFF

        if key in (ord("q"), 27):
            break
        if awaiting == "server" and key in SIDES:
            current["server"] = SIDES[key]; awaiting = None; continue
        if awaiting == "winner" and key in SIDES:
            current["winner"] = SIDES[key]; awaiting = "ending"; continue
        if awaiting == "ending" and key in ENDINGS:
            current["ending"] = ENDINGS[key]
            points.append(current); _save(points, OUTPUT_CSV)
            print(f"Saved point {len(points)}: {current}")
            current, awaiting = None, None
            continue
        if key == ord("u"):
            if current:
                current, awaiting = None, None; print("Cancelled point in progress")
            elif points:
                print(f"Removed point {len(points)}: {points.pop()}"); _save(points, OUTPUT_CSV)
            continue
        if awaiting:
            continue                                    # waiting for a valid answer
        if key == ord("s"):
            current = {"start_frame": frame_num, "end_frame": "", "server": "", "winner": "", "ending": ""}
            awaiting = "server"
        elif key == ord("e") and current:
            current["end_frame"] = frame_num; awaiting = "winner"
        elif key in (ord("d"), 83):
            frame_num, frame = read(frame_num + 1)
        elif key in (ord("a"), 81):
            frame_num, frame = read(frame_num - 1)
        elif key == ord("D"):
            frame_num, frame = read(frame_num + 10)
        elif key == ord("A"):
            frame_num, frame = read(frame_num - 10)
        elif key == ord("J"):
            frame_num, frame = read(frame_num + 100)
        elif key == ord("K"):
            frame_num, frame = read(frame_num - 100)

    cap.release()
    cv2.destroyAllWindows()
    _save(points, OUTPUT_CSV)
    print(f"\nSaved {len(points)} points to {OUTPUT_CSV}")


if __name__ == "__main__":
    main()
