"""
Produces the two final deliverables of the MVP pipeline:
  1. An annotated video with ball trail + player boxes/IDs overlaid.
  2. A ball-placement heatmap split by player side.

CHECKED Day 3: no ping-pong-specific hardcoded values found here -- table_w/
table_h are already sourced from config.py (now real tennis dimensions), so
this file works for tennis as-is functionally. Only the "Ping Pong" text
labels below were stale; fixed. Net line in _draw_table is drawn at
x = table_w/2, which matches config.NET_POSITION_OFFSET's convention
(confirmed correct after the Day 3 axis fix in calibration.py).

Run this standalone after player_id.py:
    python output.py
"""

import cv2
import matplotlib.patches as patches
import matplotlib.pyplot as plt
import pandas as pd

import config


def render_annotated_video(video_path, match_csv_path, output_video_path):
    """
    Renders the source video with a fading ball trail, player bounding
    boxes + IDs, and a frame counter overlaid, saving to output_video_path.
    """
    df = pd.read_csv(match_csv_path)
    if df.empty:
        raise RuntimeError(f"{match_csv_path} is empty — nothing to render.")

    ball_by_frame = {}
    player_by_frame = {}

    for frame_num, group in df.groupby("frame"):
        ball_rows = group[group["type"] == "ball"]
        player_rows = group[group["type"] == "player"]

        if not ball_rows.empty:
            row = ball_rows.iloc[0]
            if pd.notna(row["pixel_x"]):
                ball_by_frame[frame_num] = (int(row["pixel_x"]), int(row["pixel_y"]))

        players = {}
        for _, row in player_rows.iterrows():
            if pd.notna(row["pixel_x"]) and pd.notna(row["track_id"]):
                players[int(row["track_id"])] = {
                    "center": (int(row["pixel_x"]), int(row["pixel_y"])),
                    "box": (int(row["x1"]), int(row["y1"]), int(row["x2"]), int(row["y2"])),
                }
        if players:
            player_by_frame[frame_num] = players

    cap = cv2.VideoCapture(str(video_path))
    fps = cap.get(cv2.CAP_PROP_FPS)
    w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    writer = cv2.VideoWriter(str(output_video_path), cv2.VideoWriter_fourcc(*"mp4v"), fps, (w, h))

    print(f"Rendering annotated video: {total} frames")

    frame_num = 0
    ball_trail = []  # rolling window of last 20 ball positions

    while cap.isOpened():
        ret, frame = cap.read()
        if not ret:
            break

        # ── Ball trail ─────────────────────────────────────────────────────
        ball_pos = ball_by_frame.get(frame_num)
        ball_trail.append(ball_pos)
        ball_trail = ball_trail[-20:]

        for i in range(1, len(ball_trail)):
            if ball_trail[i - 1] and ball_trail[i]:
                alpha = i / len(ball_trail)
                color = (0, int(255 * alpha), int(255 * alpha))
                thickness = max(1, int(3 * alpha))
                cv2.line(frame, ball_trail[i - 1], ball_trail[i], color, thickness)

        if ball_pos:
            cv2.circle(frame, ball_pos, 8, (0, 255, 255), -1)
            cv2.circle(frame, ball_pos, 10, (0, 180, 180), 2)

        # ── Players ────────────────────────────────────────────────────────
        players = player_by_frame.get(frame_num, {})
        colors = {1: (255, 100, 0), 2: (0, 180, 255)}  # P1=orange, P2=blue

        for tid, data in players.items():
            color = colors.get(tid, (200, 200, 200))
            x1, y1, x2, y2 = data["box"]
            cx, cy = data["center"]

            cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
            cv2.putText(frame, f"Player {tid}", (x1, y1 - 10),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.8, color, 2)
            cv2.circle(frame, (cx, cy), 5, color, -1)

        # ── Frame counter ─────────────────────────────────────────────────
        cv2.putText(frame, f"Frame {frame_num}", (20, 40),
                    cv2.FONT_HERSHEY_SIMPLEX, 1.0, (255, 255, 255), 2)

        writer.write(frame)
        frame_num += 1

        if frame_num % 500 == 0:
            print(f"  Rendered {frame_num}/{total} frames")

    cap.release()
    writer.release()
    print(f"\nSaved {output_video_path}")


def _draw_table(ax, table_w, table_h, title=None):
    """Shared helper to draw the table outline, net line, and center line."""
    ax.set_xlim(0, table_w)
    ax.set_ylim(0, table_h)
    ax.set_facecolor("#1a6b2e")
    ax.set_aspect("equal")
    ax.add_patch(patches.Rectangle((0, 0), table_w, table_h, linewidth=3,
                                    edgecolor="white", facecolor="none"))
    ax.axvline(x=table_w / 2, color="white", linewidth=3)  # net
    ax.axhline(y=table_h / 2, color="white", linewidth=1, linestyle="--", alpha=0.4)
    if title:
        ax.set_title(title, color="white", fontsize=12, pad=10)
    ax.tick_params(colors="white")


def generate_heatmap(match_csv_path, output_path, table_w=config.TABLE_W, table_h=config.TABLE_H):
    """
    Builds a 3-panel heatmap (full match, Player 1's side, Player 2's side)
    of ball placement and saves it to output_path.
    """
    df = pd.read_csv(match_csv_path)
    ball = df[df["type"] == "ball"].dropna(subset=["table_x", "table_y"])
    ball = ball[
        (ball["table_x"] >= 0) & (ball["table_x"] <= table_w) &
        (ball["table_y"] >= 0) & (ball["table_y"] <= table_h)
    ].copy()

    p1_side = ball[ball["table_x"] <= table_w / 2]
    p2_side = ball[ball["table_x"] > table_w / 2]

    print(f"Ball positions on P1 side: {len(p1_side)}")
    print(f"Ball positions on P2 side: {len(p2_side)}")

    fig, axes = plt.subplots(1, 3, figsize=(22, 7))
    fig.patch.set_facecolor("#1a1a1a")

    # Panel 1 — full match
    _draw_table(axes[0], table_w, table_h, "Full Match — Ball Placement")
    hb = axes[0].hexbin(ball["table_x"], ball["table_y"], gridsize=30,
                         cmap="YlOrRd", alpha=0.85, mincnt=1)
    plt.colorbar(hb, ax=axes[0]).ax.yaxis.label.set_color("white")
    axes[0].text(table_w * 0.25, table_h * 0.95, "Player 1", ha="center", color="white", fontsize=9, alpha=0.8)
    axes[0].text(table_w * 0.75, table_h * 0.95, "Player 2", ha="center", color="white", fontsize=9, alpha=0.8)

    # Panel 2 — Player 1's side (where P2 lands shots)
    _draw_table(axes[1], table_w, table_h, "Player 1's Side\n(P2's shot placement)")
    if len(p1_side) > 0:
        axes[1].hexbin(p1_side["table_x"], p1_side["table_y"], gridsize=20,
                        cmap="Blues", alpha=0.85, mincnt=1)
    axes[1].text(table_w * 0.25, table_h * 0.5, f"{len(p1_side)} shots",
                 ha="center", va="center", color="white", fontsize=10)

    # Panel 3 — Player 2's side (where P1 lands shots)
    _draw_table(axes[2], table_w, table_h, "Player 2's Side\n(P1's shot placement)")
    if len(p2_side) > 0:
        axes[2].hexbin(p2_side["table_x"], p2_side["table_y"], gridsize=20,
                        cmap="Oranges", alpha=0.85, mincnt=1)
    axes[2].text(table_w * 0.75, table_h * 0.5, f"{len(p2_side)} shots",
                 ha="center", va="center", color="white", fontsize=10)

    plt.suptitle("Tennis Match Analysis", color="white", fontsize=15, fontweight="bold", y=1.02)
    plt.tight_layout(pad=2.0)
    plt.savefig(output_path, dpi=150, bbox_inches="tight", facecolor="#1a1a1a")
    plt.show()
    print(f"Saved {output_path}")


if __name__ == "__main__":
    render_annotated_video(config.VIDEO_PATH, config.MATCH_CSV, config.OUTPUT_VIDEO)
    generate_heatmap(config.MATCH_CSV, config.HEATMAP_PATH)
