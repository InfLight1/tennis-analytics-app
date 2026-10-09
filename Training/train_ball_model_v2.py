# Same recipe as tennis_ball_v1-5 (yolov8s, imgsz 1280, 100 ep, batch 8, patience 15), new v4 dataset.
from ultralytics import YOLO
DATA = r"C:\Users\rudra\Downloads\Projects\Tennis Performance App\Training\Tennis Ball.v4-4.yolov8\data.yaml"
if __name__ == "__main__":
    m = YOLO("yolov8s.pt")
    r = m.train(data=DATA, epochs=100, imgsz=1280, batch=8, name="tennis_ball_v2",
                patience=15, save=True, save_period=10, val=True, plots=True)
    print("SAVE_DIR", r.save_dir if hasattr(r, "save_dir") else m.trainer.save_dir)
