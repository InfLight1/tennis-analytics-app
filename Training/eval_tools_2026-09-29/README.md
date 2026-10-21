# Model / pipeline evaluation tools (2026-09-29)

Used to compare ball model v1-5 (production) vs v2 (far-player retrain) and to score pipeline changes. Results are in TennisPerfApp.md §5.

- `score_all.sh <tag> <clip2_0-2800 cands> <clip1 cands> <clip2 full cands>`: one line with job-clip typed F1, hold-out typed F1, and point outcomes vs ground_truth_points.csv. Example (v1-5):
  `bash score_all.sh v1 ../Diagnostics/raw_ball_cands_clip2_0-2800_imgsz2560.csv ../Diagnostics/raw_ball_cands_clip1_imgsz2560.csv ../Diagnostics/raw_ball_cands_clip2_full_imgsz2560_fp16.csv`
  (v2 dumps: the same names with `_v2model`). Paths are relative to Code/, where the script cd's.
- `flags_run.py "USE_NET_EVENTS=0,..." offline_eval.py ...`: run with analysis.py flags toggled (ablations). Run from Code/.
- `extract_with_model.py <weights.pt> <extract_raw_ball_detections args>`: raw detection dump with any model. Run from Code/.
- `val_compare.py`: mAP for both models on the v4 test split and the clean held-out sets in `clean_eval/` (built by `build_clean.py`: v4 valid+test images neither model trained on).
- `far_inplay_recall.py <weights> valid,test`: recall on the hand-added in-play far balls.

Windows: run YOLO val/train from a script file (not `python -` via stdin) and set PYTHONIOENCODING=utf-8.

**2026-10-21:** `score_all.sh` now uses the court found by `Code/court_detect.py` (`Diagnostics/perspective_matrix_76a383379d90_auto.npy`, `perspective_matrix_clip1_auto.npy`). The old hand-marked courts were off by ~40 px (2-3 m at the far baseline on the job clip). The hold-out labels live in `Code/legacy/ground_truth_events.csv`. Result: job F1 0.68, hold-out F1 0.70, points 18/20 offline (the live app, with its own ball detections, gets 17/20; that is the number used everywhere else).
