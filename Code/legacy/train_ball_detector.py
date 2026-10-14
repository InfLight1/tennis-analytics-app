"""
train_ball_detector.py
Day 4 (no-footage) deliverable -- trains the custom tennis ball detector
once Roboflow frames are ready. NOT runnable yet: DATASET_YAML is a
placeholder until the confirmed camera-angle footage is labeled and
exported (PROJECT.md TODO: "label more frames from the confirmed...
footage...then run first YOLOv8 training pass").

Editable top-of-file variables, same convention as extract_frames.py --
no CLI args, run directly once DATASET_YAML is set.

Expects a standard Roboflow YOLOv8 export:
    <dataset_root>/
        data.yaml
        train/images, train/labels
        valid/images, valid/labels
        test/images,  test/labels   (optional)

Output weights land at PROJECT_DIR / RUN_NAME / "weights" / "best.pt",
which is set below to match config.BALL_MODEL_PATH exactly -- once
training finishes, config.py needs no changes for main.py to pick up the
new model.
"""

from pathlib import Path
from ultralytics import YOLO

import config

# ── Editable top-of-file variables ─────────────────────────────────────────
# TODO (BLOCKING): set this once the Roboflow export is downloaded for the
# confirmed camera-angle footage. Placeholder path only -- see PROJECT.md
# "Now" TODO list.
DATASET_YAML = Path("PLACEHOLDER_roboflow_export/data.yaml")

BASE_MODEL = "yolov8n.pt"     # nano: fastest to iterate with ~70-200 labeled frames; move to yolov8s.pt if accuracy is the bottleneck once real training starts
EPOCHS = 100
IMGSZ = config.INFERENCE_IMGSZ   # 1280 -- matches inference imgsz in config.py so train/inference resolution match
BATCH = 8                        # conservative default for a small custom dataset; raise if GPU headroom allows
PATIENCE = 20                    # early-stopping patience (epochs with no val improvement)

# Matches config.BALL_MODEL_PATH's expected structure exactly:
# CODE_DIR / "runs" / "detect" / "tennis_ball_v1" / "weights" / "best.pt"
PROJECT_DIR = config.CODE_DIR / "runs" / "detect"
RUN_NAME = "tennis_ball_v1"


def train():
    if not DATASET_YAML.exists():
        raise FileNotFoundError(
            f"{DATASET_YAML} not found. This is expected until the Roboflow "
            f"export for the confirmed camera-angle footage is downloaded -- "
            f"update DATASET_YAML at the top of this file first. See "
            f"PROJECT.md 'Now' TODO list."
        )

    model = YOLO(BASE_MODEL)

    print(f"Training on {DATASET_YAML}")
    print(f"Base model: {BASE_MODEL} | epochs={EPOCHS} | imgsz={IMGSZ} | batch={BATCH}")
    print(f"Weights will be saved under: {PROJECT_DIR / RUN_NAME / 'weights'}")

    results = model.train(
        data=str(DATASET_YAML),
        epochs=EPOCHS,
        imgsz=IMGSZ,
        batch=BATCH,
        patience=PATIENCE,
        project=str(PROJECT_DIR),
        name=RUN_NAME,
        exist_ok=True,      # allows re-running without manually clearing the run dir
        single_cls=True,    # safeguard matching PROJECT.md's multi-ball decision: all balls
                             # are one class at detection stage, disambiguation happens
                             # downstream in detection.py's track-based filtering, not via
                             # extra classes here -- redundant if the Roboflow project only
                             # ever had one class, but cheap insurance if it didn't
    )

    best_weights = PROJECT_DIR / RUN_NAME / "weights" / "best.pt"
    if best_weights != config.BALL_MODEL_PATH:
        print(
            f"\nWARNING: trained weights at {best_weights} but "
            f"config.BALL_MODEL_PATH is {config.BALL_MODEL_PATH} -- "
            f"main.py won't pick this model up until PROJECT_DIR/RUN_NAME "
            f"above and config.py agree."
        )
    else:
        print(f"\nDone. Best weights: {best_weights}")
        print("config.BALL_MODEL_PATH already points here -- no config change needed.")

    return results


def validate():
    """
    Optional standalone re-check of an already-trained model against the
    validation split. Not part of train() since Ultralytics already
    validates every epoch -- this is a final sanity check at default
    confidence thresholds only.
    """
    if not config.BALL_MODEL_PATH.exists():
        raise FileNotFoundError(f"No trained weights at {config.BALL_MODEL_PATH} yet -- run train() first.")
    model = YOLO(str(config.BALL_MODEL_PATH))
    metrics = model.val(data=str(DATASET_YAML))
    print(metrics)
    return metrics


if __name__ == "__main__":
    train()
