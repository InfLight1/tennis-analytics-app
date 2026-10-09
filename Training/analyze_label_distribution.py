"""Analyze existing YOLO ball labels: distribution of vertical position (proxy for
grounded vs. airborne) and box aspect ratio (proxy for motion blur/streaking).
No manual review needed — reads label .txt files directly."""
import os
import glob

# Editable
LABELS_DIR = r"C:\Users\rudra\Downloads\Projects\Tennis Performance App\Training\Annotated Ball Pics\train\labels"

# Bucket edges for normalized y-center (0 = top of frame, 1 = bottom)
# Adjust based on your camera angle if the court fills a different vertical band
LOW_BAND    = 0.66   # below this y is treated as "ground-level band"
MID_BAND    = 0.33   # between LOW_BAND and MID_BAND is "mid-air band"
                      # above MID_BAND is "high/elevated band"


def main():
    label_files = glob.glob(os.path.join(LABELS_DIR, "*.txt"))
    print(f"Found {len(label_files)} label files\n")

    y_positions = []
    aspect_ratios = []

    for path in label_files:
        with open(path, "r") as f:
            for line in f:
                parts = line.strip().split()
                if len(parts) < 5:
                    continue
                # YOLO format: class x_center y_center width height (all normalized 0-1)
                _, x_c, y_c, w, h = parts[:5]
                y_c, w, h = float(y_c), float(w), float(h)
                y_positions.append(y_c)
                if h > 0:
                    aspect_ratios.append(w / h)

    total = len(y_positions)
    if total == 0:
        print("No ball annotations found — check LABELS_DIR path.")
        return

    ground_band = sum(1 for y in y_positions if y >= LOW_BAND)
    mid_band    = sum(1 for y in y_positions if MID_BAND <= y < LOW_BAND)
    high_band   = sum(1 for y in y_positions if y < MID_BAND)

    print("=== Vertical position distribution (proxy for grounded vs. airborne) ===")
    print(f"Ground-level band (y >= {LOW_BAND}):  {ground_band:5d}  ({100*ground_band/total:.1f}%)")
    print(f"Mid-air band      ({MID_BAND}-{LOW_BAND}): {mid_band:5d}  ({100*mid_band/total:.1f}%)")
    print(f"High/elevated band (y < {MID_BAND}):   {high_band:5d}  ({100*high_band/total:.1f}%)")

    # Aspect ratio: a near-circular ball should be close to 1.0.
    # Values far from 1.0 suggest motion streaking/blur elongating the box.
    elongated = sum(1 for r in aspect_ratios if r > 1.5 or r < 0.67)
    print(f"\n=== Aspect ratio (proxy for blur/streaking) ===")
    print(f"Total boxes:               {len(aspect_ratios)}")
    print(f"Elongated boxes (>1.5x or <0.67x): {elongated}  ({100*elongated/len(aspect_ratios):.1f}%)")
    print("Low elongated % likely means blurred balls are being labeled as small/tight")
    print("boxes rather than true motion streaks — worth spot-checking a few directly.")


if __name__ == "__main__":
    main()
