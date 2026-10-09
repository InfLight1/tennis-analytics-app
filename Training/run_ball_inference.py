"""Standalone qualitative check: run the trained ball detector on a real clip
and save an annotated output video for visual review (gaps, jitter, false positives)."""
from ultralytics import YOLO

# Paths — editable
MODEL_PATH  = r"C:\Users\rudra\Downloads\Projects\Tennis Performance App\Models\tennis_ball_v1.pt"
CLIP_PATH   = r"C:\Users\rudra\Downloads\Projects\Tennis Performance App\Videos\tennis1_clip.mp4"
PROJECT_DIR = r"C:\Users\rudra\Downloads\Projects\Tennis Performance App\Training\runs\detect"
RUN_NAME    = "qual_check_lowconf"

# Inference settings
IMGSZ = 1280
CONF  = 0.1   # lower to ~0.1 to also see borderline/low-confidence detections
LINE_WIDTH = 2 # thin box outline so it doesn't swallow a small ball


def main():
    model = YOLO(MODEL_PATH)

    model.predict(
        source=CLIP_PATH,
        imgsz=IMGSZ,
        conf=CONF,
        save=True,              # writes annotated output video
        project=PROJECT_DIR,
        name=RUN_NAME,
        line_width=LINE_WIDTH,
        show_labels=False,      # no "ball 0.87" text — just the box
        show_conf=False,
    )

    print(f"Annotated video saved under: {PROJECT_DIR}\\{RUN_NAME}")


if __name__ == "__main__":
    main()
