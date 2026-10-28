"""Checks for accounts.py and progress.py (no server, no Modal).
Run: python test_accounts_progress.py"""

import accounts
import progress

accounts.PW_ROUNDS = 1000   # fast for tests


def check(ok, msg):
    print(("PASS  " if ok else "FAIL  ") + msg)
    if not ok:
        raise SystemExit(1)


def raises(fn):
    try:
        fn()
    except accounts.AccountError:
        return True
    return False


def test_accounts():
    clock = [1000.0]
    a = accounts.Accounts({}, now=lambda: clock[0])
    coach, team = a.create_team("Varsity", "coachk", "secret123", "Coach K")
    check(coach["role"] == "coach" and len(team["code"]) == 6, "coach creates a team with a 6-letter code")
    p1 = a.join_team(team["code"].lower(), "Rudra", "password1", "Rudra")
    p2 = a.join_team(team["code"], "sam", "password2", "Sam")
    check(p1["username"] == "rudra" and a.team(team["id"])["players"] == ["rudra", "sam"], "players join by code")
    check(raises(lambda: a.join_team("ZZZZZZ", "x1y", "password", "X")), "wrong team code refused")
    check(raises(lambda: a.join_team(team["code"], "sam", "password3", "Sam")), "taken username refused")
    check(raises(lambda: a.join_team(team["code"], "short", "pw", "S")), "short password refused")
    check("pw" not in accounts.public_user(p1), "password hash never sent to the page")

    tok = a.sign_in("RUDRA", "password1")
    check(a.session_user(tok)["username"] == "rudra", "sign in works, username not case-sensitive")
    check(raises(lambda: a.sign_in("rudra", "nope")), "wrong password refused")
    check(raises(lambda: a.sign_in("ghost", "password1")), "unknown user refused")
    clock[0] += accounts.SESSION_DAYS * 86400 + 1
    check(a.session_user(tok) is None, "session expires")

    a.set_owner("job1", "rudra")
    a.claim("rudra", "job1", "player_1", "2026-11-01")
    a.claim("sam", "job2", "player_2", "2026-11-01")
    other_coach, _ = a.create_team("Other", "coachz", "secret123", "Coach Z")
    check(a.can_see(p1, "job1") and not a.can_see(p2, "job1"), "players see only their own reports")
    check(a.can_see(coach, "job1") and a.can_see(coach, "job2"), "coach sees the team's reports")
    check(not a.can_see(other_coach, "job1"), "another team's coach can't")
    check(a.can_change(coach, "job1") and not a.can_change(p2, "job1"), "only uploader or coach can delete")

    a.reset_password(coach, "sam", "newpass99")
    check(bool(a.sign_in("sam", "newpass99")), "coach resets a player's password")
    check(raises(lambda: a.reset_password(other_coach, "sam", "hackhack1")), "not for other teams' players")


def _pl(net, beaten, played, fsi=50.0):
    return {"stats": {"points_played": played, "points_won_pct": 50.0,
                      "serve": {"first_serve_in_pct": fsi, "second_serve_in_pct": 80.0, "double_faults": 1}},
            "weaknesses": [w for w in (
                {"id": "errors_net", "title": "Errors into the net", "points": net, "top": True},
                {"id": "opponent_winners", "title": "Beaten", "points": beaten, "top": False}) if w["points"]]}


def test_progress():
    r = progress.build([
        {"job_id": "b", "date": "2026-11-08", "player": _pl(net=3, beaten=4, played=20)},
        {"job_id": "a", "date": "2026-11-01", "player": _pl(net=8, beaten=4, played=20)},
        {"job_id": "c", "date": "2026-11-15", "player": _pl(net=2, beaten=0, played=4)},
    ])
    check([m["job_id"] for m in r["matches"]] == ["a", "b", "c"], "matches sorted oldest first")
    net = next(w for w in r["weaknesses"] if w["id"] == "errors_net")
    check(net["rates"] == [4.0, 1.5] and net["trend"] == "shrinking", "net errors per 10 points shrink 4.0 -> 1.5")
    beaten = next(w for w in r["weaknesses"] if w["id"] == "opponent_winners")
    check(beaten["trend"] == "about the same", "same rate = about the same")
    check(not r["matches"][2]["enough"], "a 4-point match is too small to count in trends")
    check(r["focus"]["id"] == "opponent_winners", "focus = biggest cost in the latest usable match")
    one = progress.build([{"job_id": "a", "date": "2026-11-01", "player": _pl(8, 4, 20)}])
    check(one["weaknesses"][0]["trend"] == "not enough yet", "one match: no trend claimed")
    check(progress.build([])["focus"] is None, "no matches: no focus")


if __name__ == "__main__":
    test_accounts()
    test_progress()
    print("\nAll account and progress checks passed.")
