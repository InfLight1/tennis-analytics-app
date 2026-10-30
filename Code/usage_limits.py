"""
usage_limits.py

Spend guard (2026-10-29): a cap on how many match analyses can start per day, for
the whole app and per signed-in player, so a bug, a misunderstanding or a shared
passcode can't run up the GPU bill. Checked when the court is marked (before
filming, for Record match), so a player hears "limit reached" before playing,
not after. Marking the same match again doesn't count twice.

The hard money cap is Modal's own workspace budget (Settings -> Usage); this is the
friendly first line. Limits come from env vars at deploy time:
  MAX_ANALYSES_PER_DAY         whole app, default 40
  MAX_ANALYSES_PER_PLAYER_DAY  each signed-in player or coach, default 4
Days are California days.

UsageLimits(store).try_start(job_id, who) -> (ok, message)
  store: a dict-like (Modal Dict in the app, a plain dict in tests)
  who:   the signed-in username, or None for passcode users (whole-app cap only)
"""

import datetime
import os

DEFAULT_PER_DAY = 40
DEFAULT_PER_PLAYER_DAY = 4


def today_ca():
    try:
        from zoneinfo import ZoneInfo
        return datetime.datetime.now(ZoneInfo("America/Los_Angeles")).date().isoformat()
    except Exception:            # no time zone data: UTC is close enough
        return datetime.datetime.utcnow().date().isoformat()


class UsageLimits:
    def __init__(self, store, per_day=None, per_player_day=None):
        self.store = store
        self.per_day = int(per_day if per_day is not None else os.environ.get("MAX_ANALYSES_PER_DAY", DEFAULT_PER_DAY))
        self.per_player_day = int(per_player_day if per_player_day is not None
                                  else os.environ.get("MAX_ANALYSES_PER_PLAYER_DAY", DEFAULT_PER_PLAYER_DAY))

    def _day(self, day):
        return self.store.get(f"usage:{day}") or {"total": 0, "users": {}, "jobs": []}

    def try_start(self, job_id, who=None, day=None):
        day = day or today_ca()
        d = self._day(day)
        if job_id in d["jobs"]:
            return True, ""
        if d["total"] >= self.per_day:
            return False, ("Today's limit for new match analyses is reached (it keeps the team's costs in check). "
                           "Please try again tomorrow.")
        if who and d["users"].get(who, 0) >= self.per_player_day:
            return False, (f"You've started {self.per_player_day} match analyses today, the daily limit. "
                           "Please try again tomorrow.")
        d["total"] += 1
        if who:
            d["users"][who] = d["users"].get(who, 0) + 1
        d["jobs"].append(job_id)
        self.store[f"usage:{day}"] = d
        return True, ""

    def today(self, day=None):
        """{"total", "users", "limit_total", "limit_player"} for the coach/tester to see."""
        d = self._day(day or today_ca())
        return {"day": day or today_ca(), "total": d["total"], "users": d["users"],
                "limit_total": self.per_day, "limit_player": self.per_player_day}
