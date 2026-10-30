"""
test_usage_limits.py

Checks the daily spend guard (usage_limits.py): the whole-app cap, the per-player
cap, re-marking the same match not counting twice, and a new day starting fresh.

Run directly:
    python Code/test_usage_limits.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from usage_limits import UsageLimits  # noqa: E402

ok = True


def check(name, cond):
    global ok
    ok &= bool(cond)
    print(f"{'PASS' if cond else 'FAIL'}  {name}")


if __name__ == "__main__":
    store = {}
    u = UsageLimits(store, per_day=5, per_player_day=2)
    D = "2026-11-01"
    check("first match starts", u.try_start("job000000001", "rudra", D)[0])
    check("marking the same match again doesn't count", u.try_start("job000000001", "rudra", D)[0] and u.today(D)["total"] == 1)
    check("second match starts", u.try_start("job000000002", "rudra", D)[0])
    ok3, msg = u.try_start("job000000003", "rudra", D)
    check("third match for one player is refused", not ok3 and "daily limit" in msg)
    check("another player can still start", u.try_start("job000000004", "sam", D)[0])
    check("passcode users count toward the whole-app cap only", u.try_start("job000000005", None, D)[0])
    check("passcode user again", u.try_start("job000000006", None, D)[0])
    ok7, msg = u.try_start("job000000007", "coachk", D)
    check("whole-app cap reached refuses everyone", not ok7 and "Today's limit" in msg)
    check("a new day starts fresh", u.try_start("job000000008", "rudra", "2026-11-02")[0])
    check("today() reports counts", u.today(D)["total"] == 5 and u.today(D)["users"] == {"rudra": 2, "sam": 1})
    print("ALL PASS" if ok else "SOME FAILED")
    sys.exit(0 if ok else 1)
