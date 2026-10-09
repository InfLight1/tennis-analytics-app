# usage: score_all.sh <tag> <clip2_0-2800 cands> <clip1 cands> <clip2 full cands>
cd "/c/Users/rudra/Downloads/Projects/Tennis Performance App/Code"
export PYTHONIOENCODING=utf-8; PY=../.venv/Scripts/python.exe
J=$($PY offline_eval.py --cands "$2" --players ../raw_detection_pad20.csv --matrix ../Diagnostics/perspective_matrix_76a383379d90_4corner.npy --gt ../ground_truth_events.csv --frame-height 2160 --max-frame 2800 2>&1 | grep "frame + type" | sed 's/.*F1/F1/')
H=$($PY offline_eval.py --cands "$3" --players ../Diagnostics/raw_players_clip1.csv --matrix ../Diagnostics/perspective_matrix_76a383379d90_as_saved.npy --gt ground_truth_events.csv --frame-height 2160 2>&1 | grep "frame + type" | sed 's/.*F1/F1/')
O=$($PY offline_full_report.py --cands "$4" --players ../Diagnostics/raw_players_clip2_full.csv --matrix ../Diagnostics/perspective_matrix_76a383379d90_4corner.npy --frame-height 2160 --out-dir "/c/Users/rudra/Downloads/Projects/Tennis Performance App/Training/eval_tools_2026-09-29/rep_$1" --gt-points ../ground_truth_points.csv 2>&1 | grep -E "END-TO-END|winner OK|decided" | sed 's/ *(rest.*//; s/ *<-.*//' | tr -s ' ' | paste -sd'|')
echo "$1 | job typed $J | hold-out typed $H | $O"
