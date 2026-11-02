"""Players changing ends: the game-count rule (carries over between sets,
tiebreaks) and the walking-past-the-net check. Run: python test_end_changes.py"""

import pandas as pd

import config
import player_appearance as pa
import scoring

P1, P2 = "player_1", "player_2"


def check(ok, msg):
    print(("PASS  " if ok else "FAIL  ") + msg)
    if not ok:
        raise SystemExit(1)


def win_game(state, winner):
    loser = P2 if winner == P1 else P1
    for _ in range(4):           # no-ad or not, 4 straight points win a game
        scoring._apply_point(state, winner, loser)


def play_track(rows, tid, frames, x_from, x_to):
    for i, f in enumerate(frames):
        x = x_from + (x_to - x_from) * i / max(len(frames) - 1, 1)
        rows.append({"frame": f, "type": "player", "track_id": tid, "table_x": x, "table_y": 400})


if __name__ == "__main__":
    # ---- game-count rule -------------------------------------------------
    s = scoring._new_match_state((P1, P2))
    for g in range(9):           # set 1: 6-3, nine games
        win_game(s, P1 if g % 3 else P2)
    check(s["sets_won"][P1] == 1, "set 1 won 6-3")
    check(s["ends_swapped"], "after a 9-game set the players are at swapped ends")
    win_game(s, P1)
    check(not s["ends_swapped"], "set 2: change ends again after its first game")
    win_game(s, P2)
    check(not s["ends_swapped"], "set 2: no change after its second game")

    s = scoring._new_match_state((P1, P2))
    for g in range(12):          # 6-6
        win_game(s, P1 if g % 2 else P2)
    check(s["in_tiebreak"] and not s["ends_swapped"], "6-6: tiebreak starts, back at the starting ends")
    for i in range(6):
        scoring._apply_point(s, P1, P2)
    check(s["ends_swapped"], "tiebreak: change ends after 6 points")
    scoring._apply_point(s, P1, P2)  # 7-0 wins it
    check(s["sets_won"][P1] == 1 and not s["ends_swapped"], "tiebreak won: change ends once more")

    # ---- walking past the net --------------------------------------------
    fps, net = 30.0, config.NET_POSITION_OFFSET
    near, far = 300, config.TABLE_W - 300

    def match(break_s, walkers):
        """two rallies with a break of break_s seconds; walkers = [(from_x, to_x)]."""
        rows, ev = [], []
        r1_end, r2_start = 300, 300 + int(break_s * fps)
        for f in range(0, r1_end + 1, 10):
            ev.append({"rally_id": 1, "frame": f})
        for f in range(r2_start, r2_start + 301, 10):
            ev.append({"rally_id": 2, "frame": f})
        gap = list(range(r1_end + 1, r2_start))
        for i, (a, b) in enumerate(walkers):
            play_track(rows, 10 + i, gap, a, b)
        cols = ["frame", "type", "track_id", "table_x", "table_y"]
        return pd.DataFrame(rows, columns=cols), pd.DataFrame(ev)

    m, ev = match(60, [(near, far), (far, near)])
    check(pa.net_crossings(m, ev, fps)[0] == {2: "strong"}, "both players walk past the net: a change of ends")
    m, ev = match(60, [(near, far), (far, far - 50)])
    check(pa.net_crossings(m, ev, fps)[0] == {2: "weak"}, "one player seen crossing in a long break: a maybe")
    m, ev = match(10, [(near, far)])
    check(pa.net_crossings(m, ev, fps)[0] == {}, "one player crossing between two points: not a change of ends")
    m, ev = match(60, [(near, net - 100), (far, net + 100)])
    c, seen = pa.net_crossings(m, ev, fps)
    check(c == {} and seen, "players come close to the net but stay on their side: no change")
    m, ev = match(60, [])
    check(not pa.net_crossings(m, ev, fps)[1], "players not tracked in a long break: can't rule out a change")

    # ---- combining the signals -------------------------------------------
    ids = [1, 2, 3]
    check(pa.combine(ids, {2: "strong"}, True, None)[0] == {1: False, 2: True, 3: True},
          "a strong crossing flips the ends from that point on")
    check(pa.combine(ids, {2: "weak"}, True, {1: False, 2: False, 3: False})[0][3] is False,
          "a weak crossing the colours disagree with is ignored")
    check(pa.combine(ids, {2: "weak"}, True, {1: False, 2: True, 3: True})[0][3] is True,
          "a weak crossing the colours agree with counts")
    check(pa.combine(ids, {}, True, None) == ({1: False, 2: False, 3: False}, "walk"),
          "tracked through every break, nobody crossed: same ends all match")
    check(pa.combine(ids, {}, False, None) == (None, "game count"),
          "no crossings, gaps not watched, same outfits: fall back to the game-count rule")
    print("\nAll end-change checks passed.")
