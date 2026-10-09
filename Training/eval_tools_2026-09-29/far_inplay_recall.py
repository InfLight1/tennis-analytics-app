# Recall on the hand-added in-play far balls (boxes NOT in the pre-labels) for held-out (valid+test) far crops.
import os, re, glob, sys
from ultralytics import YOLO
T = r"C:\Users\rudra\Downloads\Projects\Tennis Performance App\Training"
D, P = os.path.join(T, "Tennis Ball.v4-4.yolov8"), os.path.join(T, "far_player_batch1", "labels")
def boxes(p):
    return [tuple(map(float, l.split()[1:5])) for l in open(p) if l.strip()] if os.path.exists(p) else []
near = lambda b, o: abs(b[0]-o[0]) < 0.004 and abs(b[1]-o[1]) < 0.004
targets = []  # (img_path, [inplay boxes], [stray boxes])
for s in sys.argv[2].split(","):
    for f in glob.glob(f"{D}/{s}/labels/tennis1_clip2_f*.txt"):
        stem = re.sub(r"_jpg\.rf\..*", "", os.path.basename(f))
        new, pre = boxes(f), boxes(f"{P}/{stem}.txt")
        inplay = [b for b in new if not any(near(b, o) for o in pre)]
        targets.append((f.replace("labels", "images")[:-4] + ".jpg", inplay, pre))
m = YOLO(sys.argv[1])
for conf in (0.05, 0.15, 0.25):
    hit = tot = fp_imgs = 0
    for img, inplay, pre in targets:
        r = m(img, conf=conf, imgsz=1280, verbose=False)[0]
        W, H = r.orig_shape[1], r.orig_shape[0]
        dets = [((x1+x2)/2/W, (y1+y2)/2/H) for x1, y1, x2, y2 in r.boxes.xyxy.tolist()]
        for b in inplay:
            tot += 1
            hit += any(abs(d[0]-b[0]) < max(b[2], 0.01) and abs(d[1]-b[1]) < max(b[3], 0.015) for d in dets)
    print(f"conf {conf}: in-play far-ball recall {hit}/{tot}  ({len(targets)} imgs)")
