"""Used Roboflow to annotate tennis ball and created frame dataset"""
from ultralytics import YOLO
import os
import shutil

"""Training"""
# Paths
DATA_YAML   = r"C:\Users\rudra\Downloads\Projects\Tennis Performance App\Training\Annotated Ball Pics\data.yaml"
SAVE_DIR    = r"C:\Users\rudra\Downloads\Projects\Tennis Performance App\Models"
RUN_NAME    = "tennis_ball_v1"


def main():
    # Train
    model = YOLO("yolov8s.pt")      # pretrained COCO weights as starting point

    results = model.train(
        data=DATA_YAML,
        epochs=100,
        imgsz=1280,
        batch=8,                    # drop to 4 for out-of-memory errors
        name=RUN_NAME,
        patience=15,                # stops early if val loss doesn't improve
        save=True,
        save_period=10,             # checkpoint every 10 epochs
        val=True,
        plots=True,                 # saves loss/mAP curves to results folder
    )

    # Save best model to project folder
    best_weights = os.path.join(results.save_dir, "weights", "best.pt")
    os.makedirs(SAVE_DIR, exist_ok=True)
    destination  = os.path.join(SAVE_DIR, "tennis_ball_v1.pt")

    shutil.copy(best_weights, destination)
    print(f"Best model saved to: {destination}")

    # Quick validation on test set (explicitly reload best.pt to be sure)
    print("\nRunning validation on test set...")
    best_model = YOLO(best_weights)
    test_results = best_model.val(
        data=DATA_YAML,
        split="test",
        imgsz=1280,
    )

    print(f"\nmAP@0.5:      {test_results.box.map50:.3f}")
    print(f"mAP@0.5-0.95: {test_results.box.map:.3f}")
    print(f"Precision:    {test_results.box.mp:.3f}")
    print(f"Recall:       {test_results.box.mr:.3f}")


if __name__ == "__main__":
    main()
