"""The tip step, with a stand-in for the AI (no network, no cost).
Run: python Code/test_insights.py"""
import json
import os
import sys
from types import SimpleNamespace as NS

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import insights

failed = []


def check(ok, what):
    print(("ok   " if ok else "FAIL ") + what)
    if not ok:
        failed.append(what)


def pattern(pid, kind):
    return {"id": pid, "kind": kind, "title": pid, "detail": "d", "points": 4, "occurrences": 4, "chances": 10}


PROFILE = {
    "coverage": {"notes": ["a note"]},
    "players": {"player_1": {
        "playstyle": {"summary": "baseline"},
        "stats": {"points_won": 10, "points_lost": 10, "rally_length": {"short": {"played": 15, "won": 6}},
                  "lost_by": {"double_faults": 1}, "won_by": {"aces": 1}, "serve": {"first_serves": 14}, "return": {}},
        "weaknesses": [pattern("errors_net", "weakness")],
        "strengths": [pattern("winners", "strength")],
    }},
}
GOOD = {"players": [
    {"player_id": "player_1", "game_summary": "s", "insights": [
        {"pattern_id": "errors_net", "headline": "h", "try_this": "t", "match_strategy": "m", "habit": "b", "practice_drill": "p"},
        {"pattern_id": "made_up", "headline": "h", "try_this": "t", "match_strategy": "m", "habit": "b", "practice_drill": "p"}]},
    {"player_id": "nobody", "game_summary": "s", "insights": []}]}


class Fake:
    """Answers in order; each answer is a stop reason, or an exception to raise."""
    def __init__(self, *answers):
        self.answers, self.models = list(answers), []
        self.messages = self

    def create(self, **kw):
        self.models.append(kw["model"])
        a = self.answers.pop(0)
        if isinstance(a, Exception):
            raise a
        return NS(stop_reason=a, content=[NS(type="thinking"), NS(type="text", text=json.dumps(GOOD))],
                  usage=NS(input_tokens=1, output_tokens=2))


sent = insights.build_llm_input(PROFILE)["players"][0]
check(sent["match_context"]["rally_length"]["short"]["played"] == 15, "the AI sees how long the points were")
rule = insights.SYSTEM.split("Never restate")[1].split("\n")[0]
check("hit higher" in rule, "the instructions ban tips that only state the obvious")
check("racket" not in rule, "a racket's length is still allowed as a way to explain a height")

r = insights.generate_insights(PROFILE, client=Fake("end_turn"))
check(r["model"] == insights.MODEL and r["version"] == insights.VERSION, "Sonnet writes the tips when it works")
check([i["pattern_id"] for i in r["players"]["player_1"]["insights"]] == ["errors_net"], "tips for made-up patterns are dropped")
check(list(r["players"]) == ["player_1"], "tips for unknown players are dropped")

f = Fake("refusal", "end_turn")
r = insights.generate_insights(PROFILE, client=f)
check(f.models == [insights.MODEL, insights.BACKUP_MODEL] and r["model"] == insights.BACKUP_MODEL, "if Sonnet declines, the backup writes the tips")
r = insights.generate_insights(PROFILE, client=Fake(RuntimeError("down"), "end_turn"))
check(r and r["model"] == insights.BACKUP_MODEL, "if Sonnet errors, the backup writes the tips")
check(insights.generate_insights(PROFILE, client=Fake(RuntimeError("a"), RuntimeError("b"))) is None, "if both fail, the job still finishes with no tips")

print("\nAll insight checks passed." if not failed else f"\n{len(failed)} FAILED")
sys.exit(1 if failed else 0)
