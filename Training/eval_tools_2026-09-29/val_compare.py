from ultralytics import YOLO
SP = r"C:\Users\rudra\Downloads\Projects\Tennis Performance App\Training\eval_tools_2026-09-29"
M = {"old": r"Training/runs/detect/tennis_ball_v1-5/weights/best.pt", "new": r"Training/runs/detect/tennis_ball_v2/weights/best.pt"}
SETS = [("v4 test split (old may have trained on some)", r"Training/Tennis Ball.v4-4.yolov8/data.yaml", "test"),
        ("clean held-out, original footage", SP + r"\clean_eval\orig.yaml", "val"),
        ("clean held-out, far-player crops", SP + r"\clean_eval\far.yaml", "val")]
if __name__ == "__main__":
    for sn, y, split in SETS:
        for mn, w in M.items():
            r = YOLO(w).val(data=y, split=split, imgsz=1280, batch=8, workers=0, verbose=False, plots=False, project=SP + r"\valruns")
            print(f"RES {sn:48s} {mn}: mAP50 {r.box.map50:.3f}  mAP50-95 {r.box.map:.3f}  P {r.box.mp:.3f}  R {r.box.mr:.3f}", flush=True)
