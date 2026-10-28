"""End-to-end checks of the web app's account routes, run locally without
Modal: the accounts store becomes a plain dict and job files go to a temp
folder. Needs fastapi + httpx (the project .venv has them).
Run: ..\\.venv\\Scripts\\python.exe test_web_accounts.py  (from Code/)"""

import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "Code"))
os.environ["APP_PASSCODE"] = "test-1234"

import modal  # noqa: E402

_store = {}
modal.Dict.from_name = staticmethod(lambda *a, **k: _store)

import modal_app  # noqa: E402
import accounts  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

accounts.PW_ROUNDS = 1000
tmp = tempfile.mkdtemp()
modal_app.JOBS_DIR = tmp
modal_app._job_paths.__globals__["JOBS_DIR"] = tmp
modal_app.volume = type("V", (), {"reload": lambda s: None, "commit": lambda s: None})()
modal_app._start_r2_puller = lambda job_id: None
modal_app._r2 = lambda: None

client = TestClient(modal_app.web_app.get_raw_f()())


def check(ok, msg):
    print(("PASS  " if ok else "FAIL  ") + msg)
    if not ok:
        raise SystemExit(1)


def form(path, data, **headers):
    return client.post(path, data=data, headers=headers)


def fake_report(job_id, net):
    d = Path(tmp) / job_id
    d.mkdir(parents=True, exist_ok=True)
    player = {"name": "P", "stats": {"points_played": 20, "points_won_pct": 50.0, "serve": {}},
              "weaknesses": [{"id": "errors_net", "title": "Errors into the net", "points": net, "top": True}]}
    (d / "profile.json").write_text(json.dumps({"players": {"player_1": player, "player_2": player}}))


if __name__ == "__main__":
    team_form = {"team_name": "Varsity", "username": "coachk", "password": "secret123", "name": "Coach K"}
    r = form("/api/auth/create-team", team_form, **{"x-passcode": "wrong"})
    check(r.status_code == 401, "creating a team needs the app passcode")
    r = form("/api/auth/create-team", team_form, **{"x-passcode": "test-1234"})
    coach = r.json()["session"]
    code = client.get("/api/me", headers={"x-session": coach}).json()["team"]["code"]
    check(r.status_code == 200 and len(code) == 6, "coach signs up and sees the team code")

    rudra = form("/api/auth/join", {"code": code, "username": "rudra", "password": "password1"}).json()["session"]
    sam = form("/api/auth/join", {"code": code, "username": "sam", "password": "password2"}).json()["session"]
    check(bool(rudra and sam), "two players join with the code")
    r = form("/api/auth/create-team", {**team_form, "username": "sneaky"}, **{"x-session": rudra})
    check(r.status_code == 401, "a signed-in player can't create a team without the passcode")
    check(client.get("/api/me").json() == {"error": "passcode required"}, "no session, no passcode: locked")

    r = form("/api/upload/init", {"size": 100, "chunk_size": 50}, **{"x-session": rudra})
    job = r.json()["job_id"]
    check(r.status_code == 200, "a signed-in player can start an upload (no passcode)")
    fake_report(job, net=8)
    check(client.get(f"/api/profile/{job}", headers={"x-session": rudra}).status_code == 200, "uploader opens the report")
    check(client.get(f"/api/profile/{job}", headers={"x-session": sam}).status_code == 403, "teammate can't")
    check(client.get(f"/api/profile/{job}", headers={"x-session": coach}).status_code == 200, "coach can")
    check(client.delete(f"/api/job/{job}", headers={"x-session": sam}).status_code == 403, "teammate can't delete it")

    form("/api/me/claim", {"job_id": job, "slot": "player_1", "date": "2026-11-01"}, **{"x-session": rudra})
    r2 = form("/api/upload/init", {"size": 100, "chunk_size": 50}, **{"x-session": rudra}).json()["job_id"]
    fake_report(r2, net=3)
    form("/api/me/claim", {"job_id": r2, "slot": "player_1", "date": "2026-11-08"}, **{"x-session": rudra})
    prog = client.get("/api/progress", headers={"x-session": rudra}).json()
    check(prog["weaknesses"][0]["trend"] == "shrinking", "progress: net errors shrinking over two matches")
    check(client.get("/api/progress?player=rudra", headers={"x-session": sam}).status_code == 403,
          "a teammate can't see someone else's progress")

    team = client.get("/api/team", headers={"x-session": coach}).json()
    rp = next(p for p in team["players"] if p["username"] == "rudra")
    check(rp["matches"] == 2 and rp["latest"]["top_fix"]["id"] == "errors_net", "coach team view: latest #1 fix")
    check(client.get("/api/team", headers={"x-session": rudra}).status_code == 403, "players have no team view")

    check(client.get(f"/api/profile/{job}", headers={"x-passcode": "test-1234"}).status_code == 200,
          "the passcode still opens everything (beta + checks)")
    check(form("/api/auth/signin", {"username": "rudra", "password": "nope"}).status_code == 400, "wrong password")
    print("\nAll web account checks passed.")
