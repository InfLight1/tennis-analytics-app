"""
offline_full_report.py -- the whole CPU chain modal_app runs (linker ->
transform -> analysis -> shot_type -> identity -> outcomes -> scoring ->
report) from saved raw detections, locally, in ~1 minute. Use it to see what
the REPORT says after a change, not just event F1.

Usage:
  python offline_full_report.py --cands ../Diagnostics/raw_ball_cands_clip2_full_imgsz2560_fp16.csv \
      --players ../Diagnostics/raw_players_clip2_full.csv \
      --matrix ../Diagnostics/perspective_matrix_76a383379d90_4corner.npy \
      --frame-height 2160 --out-dir ../offline_report [--gt ../ground_truth_events.csv]
"""

import argparse
import importlib
import os

import pandas as pd

import config


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cands", required=True)
    ap.add_argument("--players", required=True)
    ap.add_argument("--matrix", required=True)
    ap.add_argument("--frame-height", type=int, required=True)
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--gt", help="optional event ground truth to score")
    ap.add_argument("--gt-points", help="optional ground_truth_points.csv to score outcomes")
    ap.add_argument("--video", help="video file: tell players apart by clothing colour")
    ap.add_argument("--names", help="player names: near end at the start, then far (comma-separated)")
    ap.add_argument("--fps", type=float, help="video frame rate: adds video times for each pattern")
    a = ap.parse_args()

    config.FRAME_HEIGHT = a.frame_height
    import analysis, detection_merge, transform, shot_type, player_identity, rally_outcomes, scoring, report
    analysis = importlib.reload(analysis)

    os.makedirs(a.out_dir, exist_ok=True)
    P = {k: os.path.join(a.out_dir, v) for k, v in dict(
        raw="raw_detection.csv", match="match_data.csv", events="rally_events.csv",
        resolved="rally_events_resolved.csv", stable="rally_events_stable.csv",
        rj="match_report.json", rt="match_report.txt").items()}

    cands = pd.read_csv(a.cands)
    players = pd.read_csv(a.players)
    total = int(max(cands["frame"].max(), players["frame"].max())) + 1
    detection_merge.merge_and_link([(cands.to_dict("records"), players.to_dict("records"))], total, P["raw"])
    transform.interpolate_and_transform(P["raw"], a.matrix, P["match"])
    analysis.run_analysis(P["match"], output_path=P["events"])

    classified = shot_type.classify_shot_types(pd.read_csv(P["events"]))
    labels, qa = player_identity.compute_rally_near_far_labels(pd.read_csv(P["match"]), classified)
    resolved = player_identity.relabel_events_to_near_far(classified, labels)
    resolved.to_csv(P["resolved"], index=False)
    outcomes = rally_outcomes.rally_outcomes(resolved)
    swaps = None
    if a.video:
        import player_appearance
        swaps = player_appearance.rally_end_swaps(a.video, pd.read_csv(P["match"]), resolved)
    per_point, summary = scoring.score_match_near_far(outcomes, swaps)
    stable_labels = {int(r.rally_id): {"near": r.near_player, "far": r.far_player} for r in per_point.itertuples()}
    stable = resolved.copy()
    stable["player_side"] = [stable_labels.get(rid, {}).get(v, v)
                             for rid, v in zip(stable["rally_id"], stable["player_side"])]
    stable.to_csv(P["stable"], index=False)
    report.generate_report(P["stable"], player_csv=None, json_path=P["rj"], summary_path=P["rt"])
    import json, player_profile
    names = dict(zip(player_profile.PLAYERS, [n.strip() for n in a.names.split(",")])) if a.names else {}
    profile = player_profile.build_profiles(resolved, pd.read_csv(P["match"]), names, swaps, fps=a.fps)
    with open(os.path.join(a.out_dir, "profile.json"), "w", encoding="utf-8") as f:
        json.dump(profile, f, indent=2, default=str)

    print("\n=== PIPELINE HEALTH ===")
    print(f"identity resolved: {len(labels)}/{len(qa)} rallies")
    print(f"rally outcomes:    {outcomes['reason'].value_counts().to_dict()}")
    print(f"points scored:     {summary.get('rallies_scored')}/{summary.get('total_rallies')}")
    print(f"shot types:        {shot_type.shot_type_summary(classified)['counts']}")
    if a.gt:
        import evaluate_events
        evaluate_events.print_summary("events vs " + os.path.basename(a.gt), evaluate_events.evaluate(P["stable"], a.gt))
    if a.gt_points:
        import evaluate_rally_outcomes
        evaluate_rally_outcomes.evaluate(P["resolved"], a.gt_points)
    print(f"\nReport: {P['rt']}")


if __name__ == "__main__":
    main()
