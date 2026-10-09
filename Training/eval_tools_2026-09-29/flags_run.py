# usage: flags_run.py "USE_NET_EVENTS=0,USE_OVERHEAD_HITS=1" <script.py> args...   (run from Code/)
import sys, runpy, importlib
sys.path.insert(0, ".")
import analysis
sets = dict(kv.split("=") for kv in sys.argv[1].split(",") if kv)
_reload = importlib.reload
def patched_reload(m):
    r = _reload(m)
    if getattr(m, "__name__", "") == "analysis":
        for k, v in sets.items(): setattr(m, k, type(getattr(m, k))(float(v)) if not isinstance(getattr(m, k), bool) else bool(int(v)))
    return r
importlib.reload = patched_reload
patched_reload(analysis)
sys.argv = sys.argv[2:]
runpy.run_path(sys.argv[0], run_name="__main__")
