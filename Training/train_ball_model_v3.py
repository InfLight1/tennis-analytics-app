# Bigger model, same data and recipe as tennis_ball_v1-5/v2 (imgsz 1280), to test "bigger model = better ball finding".
import sys
from ultralytics import YOLO
DATA = r"C:\Users\rudra\Downloads\Projects\Tennis Performance App\Training\Tennis Ball.v4-4.yolov8\data.yaml"
if __name__ == "__main__":
    base = sys.argv[1] if len(sys.argv) > 1 else "yolo11m.pt"
    name = sys.argv[2] if len(sys.argv) > 2 else "tennis_ball_v3_11m"
    m = YOLO(base)
    r = m.train(data=DATA, epochs=80, imgsz=1280, batch=4, name=name, patience=15, save=True,
                val=True, plots=True, workers=0)
    print("SAVE_DIR", m.trainer.save_dir)
