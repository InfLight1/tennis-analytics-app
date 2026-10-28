"""Doubles in/out: rally shots in the alleys are in; serves still need the
singles service box. Run: python test_doubles.py"""

import config
import analysis
import rally_outcomes


def check(ok, msg):
    print(("PASS  " if ok else "FAIL  ") + msg)
    if not ok:
        raise SystemExit(1)


if __name__ == "__main__":
    alley_y = -80          # 80 cm into the near-left alley
    far_x = config.TABLE_W - 300
    for mode, want_in in (("singles", False), ("doubles", True)):
        config.MATCH_TYPE = mode
        check(analysis.is_on_table(far_x, alley_y) == want_in, f"{mode}: rally ball in the alley is {'in' if want_in else 'out'}")
        err = rally_outcomes.classify_error_type(100, far_x, alley_y, hitter_side="near")
        check((err == "wide") != want_in, f"{mode}: alley bounce {'not ' if want_in else ''}called wide")
    config.MATCH_TYPE = "doubles"
    check(not analysis.is_on_table(far_x, -200), "doubles: past the doubles sideline is out")
    config.MATCH_TYPE = "singles"
    print("\nAll doubles checks passed.")
