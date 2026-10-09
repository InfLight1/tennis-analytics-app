"""
offline_eval.py -- rerun the CPU half of the pipeline (ball linking ->
transform -> analysis) against a saved dump of RAW, untracked ball
detections, and score the events against a ground-truth CSV. No GPU, no
Modal round-trip: change a threshold, rerun, see the effect in seconds.

Raw detections come from extract_raw_ball_detections.py (one row per model
detection, low confidence, no tracking). Player rows come from any
existing raw_detection.csv for the same video.

Usage:
  python offline_eval.py --cands raw_ball_cands.csv --players raw_detection.csv \
      --matrix perspective_matrix.npy --gt ../ground_truth_events.csv \
      --frame-height 2160 [--out-dir some/dir] [-v]
"""

import argparse
import importlib
import os
import tempfile

import pandas as pd

import config


def run(cands_path, players_path, matrix_path, gt_path, frame_height,
        out_dir=None, verbose=False, max_frame=None):
    config.FRAME_HEIGHT = frame_height
    import analysis
    import ball_linker
    import transform
    import evaluate_events
    analysis = importlib.reload(analysis)

    out_dir = out_dir or tempfile.mkdtemp(prefix="offline_eval_")
    os.makedirs(out_dir, exist_ok=True)

    cands = pd.read_csv(cands_path)
    players = pd.read_csv(players_path)
    players = players[players["type"] == "player"]
    if max_frame is None:
        max_frame = int(cands["frame"].max())
    players = players[players["frame"] <= max_frame]
    total = max_frame + 1

    ball_rows = pd.DataFrame(ball_linker.link_ball_detections(cands, total))
    raw = pd.concat([ball_rows, players], ignore_index=True).sort_values(["frame", "type"])
    raw_path = os.path.join(out_dir, "raw_detection.csv")
    raw[["frame", "type", "track_id", "pixel_x", "pixel_y", "x1", "y1", "x2", "y2",
         "confidence"]].to_csv(raw_path, index=False)

    match_path = os.path.join(out_dir, "match_data.csv")
    events_path = os.path.join(out_dir, "rally_events.csv")
    transform.interpolate_and_transform(raw_path, matrix_path, match_path)
    analysis.run_analysis(match_path, output_path=events_path)

    res = evaluate_events.evaluate(events_path, gt_path, verbose=verbose)
    evaluate_events.print_summary(events_path, res)
    return res


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--cands", required=True)
    ap.add_argument("--players", required=True)
    ap.add_argument("--matrix", required=True)
    ap.add_argument("--gt", required=True)
    ap.add_argument("--frame-height", type=int, required=True)
    ap.add_argument("--max-frame", type=int)
    ap.add_argument("--out-dir")
    ap.add_argument("-v", "--verbose", action="store_true")
    a = ap.parse_args()
    run(a.cands, a.players, a.matrix, a.gt, a.frame_height, a.out_dir, a.verbose, a.max_frame)
