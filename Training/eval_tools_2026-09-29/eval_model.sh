# usage: eval_model.sh <weights.pt> <tag> [--half]
set -e
SP="$(cd "$(dirname "$0")" && pwd)"; W="$1"; TAG="$2"; H="$3"
cd "$SP/../../Code"
export PYTHONIOENCODING=utf-8; PY=../.venv/Scripts/python.exe
$PY "$SP/extract_with_model.py" "$W" ../Videos/tennis1_clip2.mp4 "$SP/cands_clip2_$TAG.csv" --end-frame 2800 --imgsz 2560 $H | tail -2
$PY "$SP/extract_with_model.py" "$W" ../Videos/tennis1_clip.mp4 "$SP/cands_clip1_$TAG.csv" --imgsz 2560 $H | tail -2
echo "== $TAG job clip (clip2 0-2800)"
$PY offline_eval.py --cands "$SP/cands_clip2_$TAG.csv" --players ../raw_detection_pad20.csv --matrix ../Diagnostics/perspective_matrix_76a383379d90_4corner.npy --gt ../ground_truth_events.csv --frame-height 2160 --max-frame 2800 2>&1 | grep -E "Impulse|frame-only|frame \+ type|per-type"
echo "== $TAG hold-out (clip1)"
$PY offline_eval.py --cands "$SP/cands_clip1_$TAG.csv" --players ../Diagnostics/raw_players_clip1.csv --matrix ../Diagnostics/perspective_matrix_76a383379d90_as_saved.npy --gt ground_truth_events.csv --frame-height 2160 2>&1 | grep -E "Impulse|frame-only|frame \+ type|per-type"
