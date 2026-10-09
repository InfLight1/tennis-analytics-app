# usage: extract_with_model.py <weights.pt> <extract_raw_ball_detections args...>  (run from Code/)
import sys, runpy, pathlib
sys.path.insert(0, ".")
import config
config.BALL_MODEL_PATH = pathlib.Path(sys.argv[1])
sys.argv = ["extract_raw_ball_detections.py"] + sys.argv[2:]
runpy.run_path("extract_raw_ball_detections.py", run_name="__main__")
