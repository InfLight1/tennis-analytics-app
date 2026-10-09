# Far-player labeling batch 1 (made 2026-09-27)

**Why:** the ball model's biggest remaining gap is the ball near the far player (serve tosses, far-baseline strokes). Most missed hits are there, and the model outputs nothing even at conf 0.05.

**What's here:**
- 300 crops (1920×1080) from `tennis1_clip2.mp4`, frames 2800+.
  - Frames 0–2800 are excluded because they're the evaluation truth set. Never label those.
  - 221 of them are frames where the pipeline currently finds no ball.
- `labels/`: YOLO pre-labels from the current model. They are mostly the stray balls on the court and are usually **missing the in-play ball**.
- Crops are at native 4K pixel scale, which matches production: 4K runs at imgsz 2560 and the model trains at 1280 on 1920px images, both 1.5×.

**How to label (Roboflow):**
1. Upload `images/` + `labels/` + `data.yaml` to the existing project as a new batch. Roboflow imports the YOLO labels.
2. For each image, draw a box on the **in-play ball** if it's visible anywhere: in the toss, on the racket, blurred mid-flight. Same rules as before: every ball is one class, including stray balls (the pre-labels cover most of those; fix any that are wrong).
3. If the in-play ball is genuinely invisible (hidden behind the player), leave the image with just the stray-ball boxes. A negative example is still useful.
4. Blur rule: box the visible streak/blob tightly, as in earlier batches.

**Then:**
1. Retrain as before (`Training/train_ball_model.py`, imgsz 1280), adding this batch to train only.
2. Evaluate the new `best.pt` on **both** truth sets **before** uploading it to Modal:
   1. Re-extract raw detections with the new model (`Code/extract_raw_ball_detections.py ... --imgsz 2560 --half`).
   2. Run `Code/offline_eval.py`. Keep the new model only if typed F1 improves on both clips.

   Current, with gap-hit inference: job clip 0.62, hold-out 0.62.
