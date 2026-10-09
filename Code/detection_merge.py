"""
detection_merge.py -- second half of chunked detection: combine every
chunk's raw output (detection.detect_chunk) and run the ball linker ONCE
over the whole video, then write raw_detection.csv in the usual schema.

CPU-only (numpy/pandas via ball_linker) -- deliberately does not import
detection.py, whose supervision/ultralytics imports only exist in the GPU
image (see modal_app._import_pipeline).
"""

import csv

import ball_linker

RAW_COLUMNS = ["frame", "type", "track_id", "pixel_x", "pixel_y",
               "x1", "y1", "x2", "y2", "confidence"]


def plan_chunks(total_frames, chunk_frames):
    """[(start, end), ...] covering range(total_frames) in chunk_frames steps."""
    return [(s, min(s + chunk_frames, total_frames)) for s in range(0, total_frames, chunk_frames)]


def merge_and_link(chunk_results, total_frames, raw_csv_path, debug_dump_path=None):
    """chunk_results: iterable of (ball_candidates, player_rows) per chunk."""
    ball_candidates, player_rows = [], []
    for balls, players in chunk_results:
        ball_candidates.extend(balls)
        player_rows.extend(players)

    ball_rows = ball_linker.link_ball_detections(
        ball_candidates, total_frames, debug_dump_path=debug_dump_path
    )
    rows = ball_rows + player_rows
    rows.sort(key=lambda r: (r["frame"], r["type"]))
    with open(raw_csv_path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(RAW_COLUMNS)
        for r in rows:
            w.writerow([r[c] for c in RAW_COLUMNS])
    print(f"Merged {len(player_rows)} player rows + linked ball over {total_frames} frames "
          f"-> {raw_csv_path}")
    return len(rows)
