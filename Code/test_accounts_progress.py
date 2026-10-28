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

    a.join_team(team["code"], "sam2", "password2", "Sam Lee")
    a.join_team(team["code"], "jo1", "password2", "Jo Park")
    check(a.match_names(team["id"], {"player_1": "rudra", "player_2": "jo"}) == {"player_1": "rudra", "player_2": "jo1"},
          "names match username or a unique first name")
    check(a.match_names(team["id"], {"player_1": "sam lee", "player_2": "Stranger"}) == {"player_1": "sam2"},
          "full name matches; strangers don't")
    check(a.match_names(team["id"], {"player_1": "Rudra", "player_2": "rudra"}) == {"player_1": "rudra"},
          "one player is never both sides")
    a.set_owner("job9", "rudra")
    a.auto_claim("job9", {"player_1": "Jo", "player_2": "Rudra"}, "2026-11-20")
    check(any(j["job_id"] == "job9" and j["slot"] == "player_2" for j in a.claims("rudra"))
          and a.can_see(a.user("jo1"), "job9"), "auto-claim: both named teammates get the match")
    a.set_result("jo1", "job9", "win")
    a.auto_claim("job9", {"player_1": "Jo", "player_2": "Someone"})
    check(not any(j["job_id"] == "job9" for j in a.claims("rudra"))
          and a.claims("jo1")[-1]["result"] == "win", "rename takes it off; a kept player's result stays")

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
    check(r["focus"]["id"] == "errors_net", "focus = the latest full match's #1 fix, like its report")
    tips = {"errors_net": {"headline": "Clear the net", "practice_drill": "Aim 1 m over the tape", "other": "x"}}
    r = progress.build([{"job_id": "a", "date": "2026-11-01", "player": _pl(8, 4, 20)},
                        {"job_id": "b", "date": "2026-11-08", "player": _pl(3, 4, 20), "advice": tips}])
    fx = r["fixes"]
    check(len(fx) == 1 and fx[0]["id"] == "errors_net" and fx[0]["job_id"] == "b", "fixes come from the latest report")
    check(fx[0]["advice"] == {"headline": "Clear the net", "practice_drill": "Aim 1 m over the tape"}
          and fx[0]["trend"] == "shrinking", "each fix carries its drill/tactic and trend")
    tf = progress.team_focus([
        {"name": "A", "fixes": [{"id": "errors_net", "title": "Net", "points": 3, "advice": {"practice_drill": "drill A"}},
                                {"id": "double_faults", "title": "DF", "points": 9}]},
        {"name": "B", "fixes": [{"id": "errors_net", "title": "Net", "points": 5, "advice": {"practice_drill": "drill B"}}]},
    ])
    check(tf[0]["id"] == "errors_net" and tf[0]["players"] == ["A", "B"] and tf[0]["points"] == 8,
          "team focus: the problem most players share comes first")
    check(tf[0]["drill"] == "drill B", "team drill = the one written for whoever lost most to it")
    finished = {"score": {"completed_sets": [[4, 6], [6, 3]], "match_winner": "player_2"}}
    pl = _pl(8, 4, 20) | {"strengths": [{"id": "winners", "title": "Winners", "detail": "3 of 10", "points": 3, "top": True}]}
    r = progress.build([{"job_id": "a", "date": "2026-11-01", "player": pl, "slot": "player_2", "match": finished},
                        {"job_id": "b", "date": "2026-11-08", "player": pl, "slot": "player_1", "result": "loss"},
                        {"job_id": "c", "date": "2026-11-09", "player": pl, "slot": "player_1"}])
    a, b, c = r["matches"]
    check(a["result"] == "win" and a["result_from"] == "app" and a["sets"] == ["6-4", "3-6"],
          "finished match: win and set scores from the player's side")
    check(b["result"] == "loss" and b["result_from"] == "player" and c["result"] is None,
          "player's own result; unknown stays blank (never guessed)")
    check(r["strengths"][0]["title"] == "Winners", "what went well = latest report's strengths")
    ts = progress.team_strengths([{"name": "A", "strengths": r["strengths"]}, {"name": "B", "strengths": r["strengths"]}])
    check(ts[0]["players"] == ["A", "B"], "team strengths pooled by player count")
    one = progress.build([{"job_id": "a", "date": "2026-11-01", "player": _pl(8, 4, 20)}])
    check(one["weaknesses"][0]["trend"] == "not enough yet", "one match: no trend claimed")
    check(progress.build([])["focus"] is None, "no matches: no focus")


if __name__ == "__main__":
    test_accounts()
    test_progress()
    print("\nAll account and progress checks passed.")
