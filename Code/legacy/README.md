# Legacy code

Earlier code kept for history. **Nothing here is used by the app** (`modal_app.py`) or by the testing tools in `Code/`, and it is not uploaded when the app is deployed.

- **First pipeline:** `Process.py` (the first prototype), `main.py`, `output.py`, `player_id.py`, `statistics.py`, `metrics.py`, `train_ball_detector.py`. Replaced by the current chain in `modal_app.py` (detection → `transform.py` → `analysis.py` → … → `player_profile.py` → `insights.py`).
- **Synthetic data:** `generate_synthetic_data.py` and its outputs `synthetic_match_report.*`, used before real footage existed.
- **One-off debugging scripts** from the ball-tracking and accuracy work: `diagnose_*.py`, `diff_pipeline_stages.py`, `find_trailing_bounce.py`, `export_far_player_frames.py`, `run_real_report.py`.
- `ground_truth_events.csv`: an older copy of the hand labels. The current labels are in `ground_truth_events.csv` at the project root.

Scripts here import modules from `Code/`. To run one again, move it back into `Code/` first.
