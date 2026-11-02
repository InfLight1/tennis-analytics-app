"""
watch_data.py -- the ball's position in every frame, for the report's video
player to draw a marker on the ball (2026-11-01: the ball is hard to see in
the small player).

ball_track(match_df, width, height, fps) -> {"fps", "f": [frame...],
"x": [...], "y": [...], "s": [...]} with x and y in thousandths of the
picture's width and height, so they fit the smaller watch copy too, and s
the ball's width in ten-thousandths of the picture's width (so the marker is
the ball's own size; frames filled in between detections borrow the nearest
size). Only frames where the ball's position is known.
"""

import numpy as np


def ball_track(match_df, width, height, fps):
    b = match_df[(match_df["type"] == "ball") & match_df["pixel_x"].notna() & match_df["pixel_y"].notna()]
    b = b.sort_values("frame").drop_duplicates("frame")
    x = np.clip(np.round(1000 * b["pixel_x"].to_numpy() / width), 0, 1000).astype(int)
    y = np.clip(np.round(1000 * b["pixel_y"].to_numpy() / height), 0, 1000).astype(int)
    size = (b["x2"] - b["x1"]) if {"x1", "x2"} <= set(b.columns) else None
    size = size.ffill().bfill().fillna(0) if size is not None else np.zeros(len(b))
    s = np.round(10000 * np.asarray(size, dtype=float) / width).astype(int)
    return {"fps": float(fps), "f": b["frame"].astype(int).tolist(), "x": x.tolist(), "y": y.tolist(), "s": s.tolist()}
