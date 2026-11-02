# Make a labeling batch from a new match video (e.g. a Sunday training video), pre-labeled by today's model,
# so Rudra only fixes boxes instead of drawing every one.
#
# Picks frames spread over the whole video, half of them "hard" (the model finds no confident ball), and saves
#   full/  : whole frame scaled to 1920x1080 (same as the old Tennis1 frames)
#   far/   : top part of the frame at native 4K pixel scale, 1920x1080 crop centred (the far court, where the ball is tiny)
# each with YOLO pre-labels (labels/) and a data.yaml, ready to upload to the Roboflow project as a new batch.
#
# Usage (from the project folder, Windows: a script file, not stdin):
#   .venv\Scripts\python.exe Training\make_label_batch.py Videos\raw\2026-11-01\video1.mov Training\batch_2026-11-01 --n 300
# Never use frames from held-out test matches (Nov 15 - Dec 13 Sundays) for training batches.
import argparse, os, random
import cv2
from ultralytics import YOLO

MODEL = r"Training/runs/detect/tennis_ball_v1-5/weights/best.pt"  # = Models/tennis_ball_v1.pt (production)


def write_set(root, name, img, boxes):
    """boxes: list of (cx, cy, w, h) in img pixels."""
    H, W = img.shape[:2]
    os.makedirs(f"{root}/images", exist_ok=True); os.makedirs(f"{root}/labels", exist_ok=True)
    cv2.imwrite(f"{root}/images/{name}.jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 95])
    with open(f"{root}/labels/{name}.txt", "w") as f:
        for cx, cy, w, h in boxes:
            f.write(f"0 {cx / W:.6f} {cy / H:.6f} {w / W:.6f} {h / H:.6f}\n")
    with open(f"{root}/data.yaml", "w") as f:
        f.write("train: images\nval: images\nnc: 1\nnames: ['Tennis-Ball']\n")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("video"); ap.add_argument("out")
    ap.add_argument("--n", type=int, default=300, help="frames to pick (each gives a full + a far image)")
    ap.add_argument("--stride", type=int, default=15, help="look at every Nth frame")
    ap.add_argument("--conf", type=float, default=0.25, help="pre-label confidence")
    ap.add_argument("--hard-share", type=float, default=0.5)
    ap.add_argument("--max-frames", type=int, default=10**9)
    ap.add_argument("--seed", type=int, default=0)
    a = ap.parse_args()
    random.seed(a.seed)
    m = YOLO(MODEL)
    cap = cv2.VideoCapture(a.video)
    total = min(int(cap.get(cv2.CAP_PROP_FRAME_COUNT)), a.max_frames)
    W, H = int(cap.get(3)), int(cap.get(4))
    stem = os.path.splitext(os.path.basename(a.video))[0]
    print(f"{a.video}: {W}x{H}, {total} frames")

    # Pass 1: score every Nth frame (sequential read, no seeking)
    scored = []  # (frame_no, [(x, y, conf)])
    fn = 0
    while fn < total:
        ok = cap.grab()
        if not ok: break
        if fn % a.stride == 0:
            ok, fr = cap.retrieve()
            r = m(fr, conf=0.05, imgsz=2560 if W >= 3000 else 1280, verbose=False, half=True)[0]
            scored.append((fn, [((x1 + x2) / 2, (y1 + y2) / 2, c) for (x1, y1, x2, y2), c in zip(r.boxes.xyxy.tolist(), r.boxes.conf.tolist())]))
        fn += 1
    # "hard" = no confident ball that moved (balls lying still on court show up in the next/previous look too)
    def moving_conf(k):
        near = [d for j in (k - 1, k + 1) if 0 <= j < len(scored) for d in scored[j][1]]
        return max((c for x, y, c in scored[k][1] if not any(abs(x - a) < 8 and abs(y - b) < 8 for a, b, _ in near)), default=0.0)
    hard = [scored[k][0] for k in range(len(scored)) if moving_conf(k) < 0.3]
    easy = [scored[k][0] for k in range(len(scored)) if moving_conf(k) >= 0.3]
    n_hard = min(len(hard), int(a.n * a.hard_share))
    pick = sorted(random.sample(hard, n_hard) + random.sample(easy, min(len(easy), a.n - n_hard)))
    print(f"scored {len(scored)} frames: {len(hard)} hard, {len(easy)} easy -> picked {len(pick)}")

    # Pass 2: save the picked frames with pre-labels
    cap = cv2.VideoCapture(a.video)
    want = set(pick); fn = 0
    while want and fn < total:
        ok = cap.grab()
        if not ok: break
        if fn in want:
            ok, fr = cap.retrieve()
            want.discard(fn)
            name = f"{stem}_f{fn:06d}"
            full = cv2.resize(fr, (1920, 1080), interpolation=cv2.INTER_AREA) if (W, H) != (1920, 1080) else fr
            r = m(full, conf=a.conf, imgsz=1280, verbose=False, half=True)[0]
            write_set(f"{a.out}/full", name, full, [((x1 + x2) / 2, (y1 + y2) / 2, x2 - x1, y2 - y1) for x1, y1, x2, y2 in r.boxes.xyxy.tolist()])
            if W >= 3000:  # far-court crop at native 4K scale
                x0 = (W - 1920) // 2
                crop = fr[0:1080, x0:x0 + 1920]
                r = m(crop, conf=a.conf, imgsz=1280, verbose=False, half=True)[0]
                write_set(f"{a.out}/far", name, crop, [((x1 + x2) / 2, (y1 + y2) / 2, x2 - x1, y2 - y1) for x1, y1, x2, y2 in r.boxes.xyxy.tolist()])
        fn += 1
    print(f"saved to {a.out} (full/ and far/). Upload each folder to Roboflow as a new batch; fix boxes; every ball is one class.")


if __name__ == "__main__":
    main()
