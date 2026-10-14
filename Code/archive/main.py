"""
Single entry point for the tennis performance pipeline.
Ported from the ping pong project's main.py (Day 1 skeleton copy) --
this is the first pass actually updating it for tennis (Day 3): calibration
now calls the reworked multi-point calibration.py, and the stats stage
calls match_stats.py instead of ping pong's metrics.py (tennis's stats
engine is net-new, see PROJECT.md §7).

Runs calibration (once), detection, transform, player ID cleanup, and
output generation in sequence.

Usage:
    python main.py
    python main.py --video "path/to/video.mp4"
    python main.py --video "path/to/video.mp4" --output-dir "path/to/results"
"""

import argparse
from pathlib import Path

import config
from calibration import select_court_points, build_perspective_transform
from detection import run_detection
from transform import interpolate_and_transform
from player_id import assign_player_ids
from output import render_annotated_video, generate_heatmap
import analysis
import match_stats


def parse_args():
    parser = argparse.ArgumentParser(description="Tennis Performance Pipeline")
    parser.add_argument(
        "--video", type=Path, default=config.VIDEO_PATH,
        help=f"Path to input video (default: {config.VIDEO_PATH})",
    )
    parser.add_argument(
        "--output-dir", type=Path, default=config.CODE_DIR,
        help=f"Directory to write all pipeline outputs (default: {config.CODE_DIR})",
    )
    return parser.parse_args()


def _run_stage(name, fn, *args, **kwargs):
    """
    Runs a pipeline stage with a clear name, so any failure reports exactly
    which stage broke instead of a raw traceback.
    """
    print(f"\n=== {name} ===")
    try:
        return fn(*args, **kwargs)
    except Exception as e:
        print(f"\n[FAILED] Stage '{name}' raised an error:")
        raise RuntimeError(f"Pipeline stopped at stage '{name}': {e}") from e


def main():
    args = parse_args()

    # ── Apply CLI overrides ─────────────────────────────────────────────────
    video_path = args.video
    output_dir = args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    raw_csv       = output_dir / config.RAW_CSV.name
    match_csv     = output_dir / config.MATCH_CSV.name
    output_video  = output_dir / config.OUTPUT_VIDEO.name
    heatmap_path  = output_dir / config.HEATMAP_PATH.name
    events_csv    = output_dir / config.EVENTS_CSV.name
    metrics_csv   = output_dir / config.METRICS_CSV.name

    print(f"Video:      {video_path}")
    print(f"Output dir: {output_dir}")

    # ── Step 1: one-time calibration ──────────────────────────────────────
    # Matrix path/logic unchanged — still one shared matrix per camera setup.
    if not config.MATRIX_PATH.exists():
        print("No perspective matrix found — running calibration...")
        points = _run_stage(
            "Calibration — selecting court reference points",
            select_court_points, video_path, extended=True,
        )
        _run_stage(
            "Calibration — building perspective transform",
            build_perspective_transform,
            clicked_points_px=points,
            video_path=video_path,
            matrix_path=config.MATRIX_PATH,
            birdeye_check_path=config.BIRDEYE_CHECK,
            court_w=config.TABLE_W,
            court_h=config.TABLE_H,
        )
    else:
        print(f"Using existing perspective matrix: {config.MATRIX_PATH}")

    # ── Step 2: detection ──────────────────────────────────────────────────
    _run_stage(
        "Running detection",
        run_detection,
        video_path=video_path,
        ball_model_path=config.BALL_MODEL_PATH,
        player_model_path=config.PLAYER_MODEL_PATH,
        raw_csv_path=raw_csv,
    )

    # ── Step 3: interpolate + transform to table coordinates ───────────────
    _run_stage(
        "Running interpolation + transform",
        interpolate_and_transform,
        raw_csv_path=raw_csv,
        matrix_path=config.MATRIX_PATH,
        output_csv_path=match_csv,
    )

    # ── Step 4: resolve player IDs ──────────────────────────────────────────
    _run_stage("Resolving player IDs", assign_player_ids, match_csv)

    # ── Step 5: outputs ──────────────────────────────────────────────────────
    print("\n=== Generating outputs ===")
    _run_stage(
        "Rendering annotated video",
        render_annotated_video,
        video_path, match_csv, output_video,
    )
    _run_stage(
        "Generating heatmap",
        generate_heatmap,
        match_csv, heatmap_path,
    )

    # ── Step 6: event detection (rally/shot/bounce segmentation) ────────────
    _run_stage(
        "Running event detection",
        analysis.run_analysis,
        match_csv, output_path=events_csv,
    )

    # ── Step 7: match statistics (net-new for tennis, not a ping pong port) ──
    _run_stage(
        "Deriving match statistics",
        match_stats.run_statistics,
        events_csv, output_path=metrics_csv,
    )

    print("\nPipeline complete.")


if __name__ == "__main__":
    main()