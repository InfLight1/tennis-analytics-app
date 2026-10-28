"""
dev_server.py -- the real web app (modal_app.web_app) on this computer, for
checking pages and account flows without Modal or a deploy.

Fakes: the accounts store is a plain dict (lost on restart), job files live
in a temp folder, R2 is off, no GPU (uploads can't be analysed). Passcode
is test-1234. `--demo` seeds a team (coach "coachk", players "rudra" and
"sam", every password "password1") with three example matches for rudra,
copied from a local profile.json, so the progress and team pages have data.

Run from Code/ with the project .venv:
  ..\\..\\Tennis Performance App\\.venv\\Scripts\\python.exe dev_server.py [--port 8770] [--demo PROFILE.json]
"""

import argparse
import copy
import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "Code"))
os.environ.setdefault("APP_PASSCODE", "test-1234")

import fastapi.responses  # noqa: E402
import modal  # noqa: E402

_store = {}
modal.Dict.from_name = staticmethod(lambda *a, **k: _store)


class _LocalFile(fastapi.responses.FileResponse):
    """Serve /root/web/... from this checkout."""
    def __init__(self, path, *a, **k):
        p = str(path)
        if p.startswith("/root/web/assets/"):
            p = str(ROOT / "web_assets" / p.rsplit("/", 1)[1])
        elif p.startswith("/root/web/"):
            p = str(ROOT / p.rsplit("/", 1)[1])
        super().__init__(p, *a, **k)


fastapi.responses.FileResponse = _LocalFile

import modal_app  # noqa: E402
import accounts  # noqa: E402

TMP = tempfile.mkdtemp(prefix="advantage_dev_")
modal_app._job_paths.__globals__["JOBS_DIR"] = TMP
modal_app.volume = type("V", (), {"reload": lambda s: None, "commit": lambda s: None})()
modal_app._start_r2_puller = lambda job_id: None
modal_app._r2 = lambda: None


def seed(profile_path):
    a = accounts.Accounts(_store)
    _, team = a.create_team("Varsity", "coachk", "password1", "Coach K")
    a.join_team(team["code"], "rudra", "password1", "Rudra")
    a.join_team(team["code"], "sam", "password1", "Sam")
    base = json.loads(Path(profile_path).read_text(encoding="utf-8"))
    # three matches: the real one, then two where net errors shrink (made-up dev data, never shown publicly)
    for i, (job, scale) in enumerate((("dev000000001", 1.0), ("dev000000002", 0.6), ("dev000000003", 0.3))):
        pf = copy.deepcopy(base)
        for w in pf["players"]["player_1"]["weaknesses"]:
            if w["id"] == "errors_net":
                w["points"] = max(1, round(w["points"] * scale))
        d = Path(TMP) / job
        d.mkdir(parents=True, exist_ok=True)
        (d / "profile.json").write_text(json.dumps(pf), encoding="utf-8")
        a.set_owner(job, "rudra")
        a.claim("rudra", job, "player_1", f"2026-11-0{1 + 7 * i}" if i == 0 else f"2026-11-{1 + 7 * i:02d}")
    print(f"Demo team code {team['code']}; sign in as coachk / rudra / sam with password1")


if __name__ == "__main__":
    import uvicorn
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8770)
    ap.add_argument("--demo", help="profile.json to seed demo matches from")
    a = ap.parse_args()
    if a.demo:
        accounts.PW_ROUNDS = 1000
        seed(a.demo)
    uvicorn.run(modal_app.web_app.get_raw_f()(), host="127.0.0.1", port=a.port, log_level="warning")
