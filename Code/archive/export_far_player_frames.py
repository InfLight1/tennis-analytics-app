"""
export_far_player_frames.py -- build a labeling batch aimed at the
ball model's biggest remaining gap: the ball near the FAR player (serve
tosses, far-baseline strokes), where it currently outputs nothing even at
conf 0.05 (TennisPerfApp.md §5).

Picks frames during active play where a far-side player is on court and
the linked ball is either missing or over the far half, skips the labeled
evaluation spans (so the test sets stay clean), and writes:

  <out>/images/<video>_f<frame>.jpg   1920x1080 crop around the far player,
                                      at NATIVE 4K pixel scale
  <out>/labels/<same>.txt             YOLO pre-labels from the current model
                                      (all balls, conf >= PRELABEL_CONF) --
                                      import into Roboflow and CORRECT them
  <out>/data.yaml                     single class, same name as the
                                      existing dataset ("Tennis-Ball")

Why a native-scale crop: the model trains at imgsz 1280 on 1920px images
(a 1.5x downscale) and production runs 4K at imgsz 2560 (also 1.5x). A
1920x1080 crop of the 4K frame keeps the far ball exactly the size the model
will see in production, instead of shrinking it 2x by resizing the whole
frame.

Usage (inputs from extract_raw_ball_detections.py over the full video):
  python export_far_player_frames.py <video> <raw_ball_cands.csv> <players.csv> <matrix.npy> <out_dir>
      [--n 350] [--exclude 0-2800]
"""

import argparse
import os
import random

import cv2
import numpy as np
import pandas as pd

import ball_linker
import config

CROP_W, CROP_H = 1920, 1080
PRELABEL_CONF = 0.25
FAR_PLAYER_MIN_TABLE_X = config.NET_POSITION_OFFSET + 300   # clearly on the far side
ACTIVE_WINDOW = 45          # frames around any linked ball point = "during play"
MIN_SPACING = 4             # frames between exported samples


def _project(M, xs, ys):
    p = np.c_[xs, ys, np.ones(len(xs))] @ M.T
    return p[:, 0] / p[:, 2], p[:, 1] / p[:, 2]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("video"); ap.add_argument("cands"); ap.add_argument("players")
    ap.add_argument("matrix"); ap.add_argument("out_dir")
    ap.add_argument("--n", type=int, default=350)
    ap.add_argument("--exclude", action="append", default=[],
                    help="frame range to skip, e.g. 0-2800 (repeatable)")
    ap.add_argument("--seed", type=int, default=0)
    a = ap.parse_args()

    M = np.load(a.matrix)
    cands = pd.read_csv(a.cands)
    total = int(cands["frame"].max()) + 1

    ball = pd.DataFrame(ball_linker.link_ball_detections(cands, total))
    ball = ball[ball["pixel_x"].notna()]
    bx, _ = _project(M, ball["pixel_x"].to_numpy(float), ball["pixel_y"].to_numpy(float))
    ball_far = dict(zip(ball["frame"], bx > config.NET_POSITION_OFFSET))
    active = np.zeros(total, dtype=bool)
    for f in ball["frame"]:
        active[max(0, f - ACTIVE_WINDOW):f + ACTIVE_WINDOW + 1] = True

    pl = pd.read_csv(a.players)
    pl = pl[pl["type"] == "player"] if "type" in pl.columns else pl
    tx, ty = _project(M, ((pl["x1"] + pl["x2"]) / 2).to_numpy(float), pl["y2"].to_numpy(float))
    pl = pl.assign(table_x=tx, table_y=ty)
    far = pl[(pl["table_x"] > FAR_PLAYER_MIN_TABLE_X) & (pl["table_x"] < config.TABLE_W + 600)
             & (pl["table_y"] > -400) & (pl["table_y"] < config.TABLE_H + 400)]
    far = far.sort_values("confidence", ascending=False).drop_duplicates("frame").set_index("frame")

    excluded = np.zeros(total, dtype=bool)
    for r in a.exclude:
        lo, hi = map(int, r.split("-"))
        excluded[lo:hi + 1] = True

    pool = [f for f in far.index if f < total and active[f] and not excluded[f]
            and ball_far.get(f, True)]          # ball missing (the failure case) or on the far half
    random.Random(a.seed).shuffle(pool)
    chosen = []
    for f in pool:
        if all(abs(f - c) >= MIN_SPACING for c in chosen):
            chosen.append(f)
        if len(chosen) >= a.n:
            break
    chosen.sort()
    missing = sum(1 for f in chosen if f not in ball_far)
    print(f"{len(pool)} candidate frames -> exporting {len(chosen)} "
          f"({missing} with no linked ball = the model's failure case)")

    img_dir, lbl_dir = os.path.join(a.out_dir, "images"), os.path.join(a.out_dir, "labels")
    os.makedirs(img_dir, exist_ok=True); os.makedirs(lbl_dir, exist_ok=True)
    stem = os.path.splitext(os.path.basename(a.video))[0]
    by_frame = {f: g for f, g in cands[cands["confidence"] >= PRELABEL_CONF].groupby("frame")}

    cap = cv2.VideoCapture(a.video)
    targets, fn, n_boxes = set(chosen), 0, 0
    while targets:
        ok = cap.grab()
        if not ok:
            break
        if fn in targets:
            _, frame = cap.retrieve()
            H, W = frame.shape[:2]
            p = far.loc[fn]
            cx = (p["x1"] + p["x2"]) / 2
            x0 = int(np.clip(cx - CROP_W / 2, 0, W - CROP_W))
            y0 = int(np.clip(p["y2"] - 0.7 * CROP_H, 0, H - CROP_H))   # room above for serve tosses
            crop = frame[y0:y0 + CROP_H, x0:x0 + CROP_W]
            name = f"{stem}_f{fn:06d}"
            cv2.imwrite(os.path.join(img_dir, name + ".jpg"), crop, [cv2.IMWRITE_JPEG_QUALITY, 95])
            lines = []
            for r in by_frame.get(fn, pd.DataFrame()).itertuples():
                x1, x2 = max(r.x1 - x0, 0), min(r.x2 - x0, CROP_W)
                y1, y2 = max(r.y1 - y0, 0), min(r.y2 - y0, CROP_H)
                if x2 - x1 < 2 or y2 - y1 < 2:
                    continue
                lines.append(f"0 {(x1 + x2) / 2 / CROP_W:.6f} {(y1 + y2) / 2 / CROP_H:.6f} "
                             f"{(x2 - x1) / CROP_W:.6f} {(y2 - y1) / CROP_H:.6f}")
            with open(os.path.join(lbl_dir, name + ".txt"), "w") as f:
                f.write("\n".join(lines))
            n_boxes += len(lines)
            targets.discard(fn)
        fn += 1
    cap.release()

    with open(os.path.join(a.out_dir, "data.yaml"), "w") as f:
        f.write("train: images\nval: images\nnc: 1\nnames: ['Tennis-Ball']\n")
    print(f"Wrote {len(chosen)} crops + {n_boxes} pre-label boxes to {a.out_dir}")


if __name__ == "__main__":
    main()
