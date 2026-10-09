"""
One-time calibration: click court reference points in a video's first frame,
then build and verify the perspective transform matrix that maps pixel
coordinates to real-world court coordinates.

Uses cv2.findHomography() (least-squares, RANSAC-guarded) over 9 points
(4 corners + service line + net) for a better far-court fit than a plain
4-point exact transform. 4-point fallback still supported if net posts
aren't visible.

Run standalone once per camera setup:
    python calibration.py

CLOUD/HEADLESS NOTE: select_court_points() opens a blocking matplotlib
window and is for LOCAL/INTERACTIVE use only. In a headless context
(Modal, a server process, etc.), use extract_calibration_frame() to get
the frame to serve to a client-side UI (e.g. the PWA), collect the
clicked-point dict there instead, and pass it directly to
build_perspective_transform() with display=False.
"""

import cv2
import numpy as np
import matplotlib.pyplot as plt

import config


# ---------------------------------------------------------------------------
# Reference-point schema. "near"/"far" = which baseline (near = camera side).
# "left"/"right" = camera's left/right. x = depth (baseline-to-baseline),
# y = width (sideline-to-sideline). Order matters -- defines click order.
# ---------------------------------------------------------------------------

CORE_CORNER_LABELS = [
    "baseline_near_left",
    "baseline_near_right",
    "baseline_far_right",
    "baseline_far_left",
]

EXTENDED_POINT_LABELS = CORE_CORNER_LABELS + [
    "service_line_near_left",
    "service_line_near_right",
    "net_center",
]

CLICK_INSTRUCTIONS = {
    "baseline_near_left": "Near baseline corner, camera-left",
    "baseline_near_right": "Near baseline corner, camera-right",
    "baseline_far_right": "Far baseline corner, camera-right",
    "baseline_far_left": "Far baseline corner, camera-left",
    "service_line_near_left": "Near service line x camera-left sideline",
    "service_line_near_right": "Near service line x camera-right sideline",
    "net_center": "Net center strap (where it touches ground)",
}


def get_reference_points_schema(court_w=config.TABLE_W, court_h=config.TABLE_H):
    """Known court reference points in court-space coords. Near baseline = x=0."""
    return {
        "baseline_near_left": (0, 0),
        "baseline_near_right": (0, court_h),
        "baseline_far_right": (court_w, court_h),
        "baseline_far_left": (court_w, 0),
        "service_line_near_left": (config.SERVICE_LINE_OFFSET_FROM_BASELINE, 0),
        "service_line_near_right": (config.SERVICE_LINE_OFFSET_FROM_BASELINE, court_h),
        "net_center": (config.NET_POSITION_OFFSET, court_h / 2),
    }


def extract_calibration_frame(video_path):
    """
    Reads the first frame of video_path, for use by a calibration UI
    (local matplotlib window, or in the cloud pipeline, served to the PWA
    for the user to click on directly).

    Returns
    -------
    np.ndarray
        The raw BGR frame (OpenCV's native format). Caller converts to
        RGB/JPEG/etc. as needed for its own display context.
    """
    cap = cv2.VideoCapture(str(video_path))
    ret, frame = cap.read()
    cap.release()

    if not ret:
        raise RuntimeError(f"Could not read video: {video_path}")

    return frame


def select_court_points(video_path, extended=True):
    """
    LOCAL/INTERACTIVE USE ONLY -- opens a blocking matplotlib window and
    lets the user click court reference points in a fixed order. Not
    callable from a headless/cloud context (Modal, etc.) -- there, the
    PWA collects the same click dict client-side from a frame served via
    extract_calibration_frame(), and that dict is passed directly to
    build_perspective_transform() instead of calling this function at all.

    Parameters
    ----------
    extended : bool
        If True (default), click all 9 points (recommended). If False,
        click only the 4 baseline corners (fallback if net posts aren't
        visible), which uses the exact-fit method instead.

    Returns
    -------
    dict[str, (float, float)]
        Pixel coordinates keyed by label, in click order.
    """
    labels = EXTENDED_POINT_LABELS if extended else CORE_CORNER_LABELS

    frame = extract_calibration_frame(video_path)
    frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

    clicks = {}
    click_order = []

    fig, ax = plt.subplots(figsize=(14, 8))
    ax.imshow(frame_rgb)

    def current_prompt():
        if len(click_order) >= len(labels):
            return "Done — all points selected. Close the window."
        next_label = labels[len(click_order)]
        return (f"Click point {len(click_order) + 1}/{len(labels)}: "
                f"{CLICK_INSTRUCTIONS[next_label]}")

    ax.set_title(current_prompt(), fontsize=11)

    def on_click(event):
        if event.xdata is None or event.ydata is None:
            return
        if len(click_order) >= len(labels):
            return

        label = labels[len(click_order)]
        x, y = float(event.xdata), float(event.ydata)
        clicks[label] = (x, y)
        click_order.append(label)

        ax.plot(x, y, "go", markersize=8)
        ax.annotate(
            f"{len(click_order)}: {CLICK_INSTRUCTIONS[label]}",
            xy=(x, y), xytext=(x + 15, y - 15),
            color="lime", fontsize=8,
            arrowprops=dict(arrowstyle="->", color="lime"),
        )
        ax.set_title(current_prompt(), fontsize=11)
        fig.canvas.draw()

    fig.canvas.mpl_connect("button_press_event", on_click)
    plt.tight_layout()
    plt.show()

    if len(click_order) != len(labels):
        raise RuntimeError(
            f"Expected {len(labels)} clicks, got {len(click_order)}. "
            f"Missing: {[l for l in labels if l not in clicks]}"
        )

    return clicks


def build_perspective_transform(
    clicked_points_px,
    video_path,
    matrix_path,
    birdeye_check_path,
    court_w=config.TABLE_W,
    court_h=config.TABLE_H,
    display=True,
):
    """
    Fits the pixel -> court-space transform from clicked points, verifies
    reprojection error, saves the matrix, and saves a bird's-eye sanity
    check image.

    If 4 points were clicked, falls back to exact-fit
    cv2.getPerspectiveTransform(). With more points, fits with
    cv2.findHomography() (RANSAC-guarded least-squares).

    Parameters
    ----------
    clicked_points_px : dict[str, (float, float)]
        Output of select_court_points() (local) or a PWA-collected click
        dict with the same shape (cloud) -- pixel coords keyed by label.
    court_w, court_h : int
        Court dimensions in court-space units (tennis singles: 2377 x 823).
    display : bool
        If True (default, local dev), shows the bird's-eye sanity-check
        image in a blocking window. Set False for any non-interactive
        caller (Modal, a server process, etc.) -- the check image is
        still always saved to birdeye_check_path regardless of this flag,
        so headless callers lose nothing except the interactive pop-up.

    Returns
    -------
    np.ndarray, shape (3, 3)
        The perspective transform matrix M.
    """
    schema = get_reference_points_schema(court_w, court_h)

    labels = [l for l in clicked_points_px if l in schema]
    if not all(c in labels for c in CORE_CORNER_LABELS):
        raise ValueError("All 4 baseline corners are required, even in fallback mode.")

    image_pts = np.array([clicked_points_px[l] for l in labels], dtype=np.float32)
    court_pts = np.array([schema[l] for l in labels], dtype=np.float32)

    if len(labels) == 4:
        print("4 points provided — using exact-fit getPerspectiveTransform.")
        M = cv2.getPerspectiveTransform(image_pts, court_pts)
    else:
        print(f"{len(labels)} points provided — using findHomography (plain least-squares).")
        # Plain least-squares (method=0), not RANSAC. Real footage showed a
        # small, consistent skew across ALL points (~40-70cm), not one bad
        # outlier -- likely mild lens distortion. RANSAC actively fights
        # that (rejects points as "outliers" and fits from a poorly-
        # distributed leftover subset), which caused wild extrapolation.
        # Revisit if a future click session produces one genuinely bad
        # point instead of this uniform-skew pattern.
        M, mask = cv2.findHomography(image_pts, court_pts, 0)
        if M is None:
            raise RuntimeError("Homography fit failed — check clicked points for errors.")

    print(f"Transform matrix computed successfully\nM =\n{M}\n")

    # ── Verify every clicked point maps back correctly ────────────────────
    print("── Point verification ──────────────────────────────────────────────")
    all_correct = True
    max_error = 0.0
    for label, img_pt, court_pt in zip(labels, image_pts, court_pts):
        pt = np.array([[[img_pt[0], img_pt[1]]]], dtype=np.float32)
        result = cv2.perspectiveTransform(pt, M)[0][0]
        error = abs(result[0] - court_pt[0]) + abs(result[1] - court_pt[1])
        max_error = max(max_error, error)
        status = "✓" if error < 75.0 else "✗ CHECK THIS"
        print(f"  {CLICK_INSTRUCTIONS.get(label, label):38s} "
              f"pixel ({img_pt[0]:.0f}, {img_pt[1]:.0f}) → "
              f"court ({result[0]:.1f}, {result[1]:.1f})  "
              f"target ({court_pt[0]:.0f}, {court_pt[1]:.0f})  {status}")
        if error >= 75.0:
            all_correct = False

    print(f"\nMax reprojection error across all points: {max_error:.1f} court-space units")
    if all_correct:
        print("All points map within tolerance — transform is good")
    else:
        print("WARNING: some points are off — re-click or check for a systematic error")

    np.save(matrix_path, M)
    print(f"Saved {matrix_path}")

    # ── Bird's-eye-view sanity check image ────────────────────────────────
    cap = cv2.VideoCapture(str(video_path))
    ret, frame = cap.read()
    cap.release()

    if not ret:
        raise RuntimeError(f"Could not read video frame: {video_path}")

    warped = cv2.warpPerspective(frame, M, (court_w, court_h))
    display_img = cv2.resize(warped, (1096, 610))
    display_rgb = cv2.cvtColor(display_img, cv2.COLOR_BGR2RGB)

    plt.figure(figsize=(14, 8))
    plt.imshow(display_rgb)
    plt.title("Bird's-Eye View — verify court looks flat and rectangular", fontsize=12)
    plt.axis("off")
    plt.tight_layout()
    plt.savefig(birdeye_check_path, dpi=150, bbox_inches="tight")
    if display:
        plt.show()
    plt.close()
    print(f"Saved {birdeye_check_path}")

    return M


if __name__ == "__main__":
    points = select_court_points(config.VIDEO_PATH, extended=True)
    build_perspective_transform(
        clicked_points_px=points,
        video_path=config.VIDEO_PATH,
        matrix_path=config.MATRIX_PATH,
        birdeye_check_path=config.BIRDEYE_CHECK,
    )
