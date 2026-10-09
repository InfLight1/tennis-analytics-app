"""
scoring.py (reconstructed from session content for local diagnostic use)
"""

import math

import pandas as pd

import config

NO_AD_SCORING = config.NO_AD_SCORING
GAMES_TO_WIN_SET = config.GAMES_TO_WIN_SET
TIEBREAK_AT_GAMES = config.TIEBREAK_AT_GAMES
TIEBREAK_POINTS_TO_WIN = config.TIEBREAK_POINTS_TO_WIN
TIEBREAK_WIN_BY = config.TIEBREAK_WIN_BY
SETS_TO_WIN_MATCH = config.SETS_TO_WIN_MATCH
MATCH_TIEBREAK_FINAL_SET = config.MATCH_TIEBREAK_FINAL_SET
MATCH_TIEBREAK_POINTS_TO_WIN = config.MATCH_TIEBREAK_POINTS_TO_WIN

UNKNOWN_LABELS = {None, "unknown", "unknown_opponent"}


def _norm(v):
    return None if pd.isna(v) else v


def _wins_game(my_points, opp_points, no_ad=NO_AD_SCORING):
    if my_points < 4:
        return False
    lead = my_points - opp_points
    return lead >= (1 if no_ad else 2)


def _wins_tiebreak(my_points, opp_points, target):
    return my_points >= target and (my_points - opp_points) >= TIEBREAK_WIN_BY


def _wins_set(my_games, opp_games):
    return my_games >= GAMES_TO_WIN_SET and (my_games - opp_games) >= 2


def _is_deciding_set(sets_won):
    return all(v == SETS_TO_WIN_MATCH - 1 for v in sets_won.values())


def format_game_score(my_points, opp_points, no_ad=NO_AD_SCORING):
    labels = ["0", "15", "30", "40"]
    if my_points < 4 and opp_points < 4:
        return f"{labels[my_points]}-{labels[opp_points]}"
    if no_ad:
        return f"{my_points}-{opp_points}"
    if my_points == opp_points:
        return "deuce"
    return "AD" if my_points > opp_points else "-AD"


def _new_match_state(players):
    p1, p2 = players
    return {
        "players": (p1, p2),
        "game_points": {p1: 0, p2: 0},
        "set_games": {p1: 0, p2: 0},
        "sets_won": {p1: 0, p2: 0},
        "completed_sets": [],
        "in_tiebreak": False,
        "match_winner": None,
    }


def _close_out_set(state, set_winner):
    p1, p2 = state["players"]
    events = [f"set_won:{set_winner}"]
    state["completed_sets"].append((state["set_games"][p1], state["set_games"][p2]))
    state["sets_won"][set_winner] += 1
    state["set_games"] = {p1: 0, p2: 0}
    state["game_points"] = {p1: 0, p2: 0}
    state["in_tiebreak"] = False

    if state["sets_won"][set_winner] >= SETS_TO_WIN_MATCH:
        state["match_winner"] = set_winner
        events.append(f"match_won:{set_winner}")
    return events


def _apply_point(state, winner, loser):
    events = []

    if state["in_tiebreak"]:
        state["game_points"][winner] += 1
        my_pts, opp_pts = state["game_points"][winner], state["game_points"][loser]
        target = (
            MATCH_TIEBREAK_POINTS_TO_WIN
            if MATCH_TIEBREAK_FINAL_SET and _is_deciding_set(state["sets_won"])
            else TIEBREAK_POINTS_TO_WIN
        )
        if _wins_tiebreak(my_pts, opp_pts, target):
            state["set_games"][winner] += 1
            events.append(f"tiebreak_won:{winner}")
            events += _close_out_set(state, winner)
        return events

    state["game_points"][winner] += 1
    my_pts, opp_pts = state["game_points"][winner], state["game_points"][loser]
    if _wins_game(my_pts, opp_pts):
        state["set_games"][winner] += 1
        state["game_points"] = {p: 0 for p in state["players"]}
        events.append(f"game_won:{winner}")

        w_games, l_games = state["set_games"][winner], state["set_games"][loser]
        if _wins_set(w_games, l_games):
            events += _close_out_set(state, winner)
        elif w_games == TIEBREAK_AT_GAMES and l_games == TIEBREAK_AT_GAMES:
            state["in_tiebreak"] = True
            events.append("tiebreak_started")

    return events


def _is_break_point(state, server):
    p1, p2 = state["players"]
    returner = p2 if server == p1 else p1
    hypothetical = state["game_points"][returner] + 1
    return _wins_game(hypothetical, state["game_points"][server])


def score_match(outcomes_df):
    known_players = set()
    for col in ("server", "winner", "loser"):
        known_players.update(_norm(v) for v in outcomes_df[col].unique())
    known_players -= UNKNOWN_LABELS

    if len(known_players) != 2:
        return pd.DataFrame(), {
            "players": tuple(sorted(known_players)),
            "match_winner": None,
            "error": f"expected exactly 2 known players, found {len(known_players)}: {sorted(known_players)}",
            "ambiguous_points_skipped": None,
            "post_match_rallies_ignored": None,
        }

    players = tuple(sorted(known_players))
    state = _new_match_state(players)

    rows = []
    ambiguous_skipped = 0
    post_match_ignored = 0

    for _, rally in outcomes_df.sort_values("rally_id").iterrows():
        winner = _norm(rally["winner"])
        loser = _norm(rally["loser"])
        server = _norm(rally.get("server"))

        post_match = state["match_winner"] is not None
        scored = (
            not post_match
            and winner not in UNKNOWN_LABELS
            and loser not in UNKNOWN_LABELS
        )

        events = []
        if post_match:
            events = ["post_match_rally_ignored"]
            post_match_ignored += 1
        elif not scored:
            ambiguous_skipped += 1
        else:
            p1, p2 = players
            returner = p2 if server == p1 else p1 if server == p2 else None
            bp = (not state["in_tiebreak"]) and returner is not None and _is_break_point(state, server)

            events = _apply_point(state, winner, loser)

            if bp:
                game_won_event = next((e for e in events if e.startswith("game_won:")), None)
                if game_won_event:
                    game_winner = game_won_event.split(":", 1)[1]
                    outcome = "converted" if game_winner == returner else "faced_not_converted"
                    events.append(f"break_point_{outcome}:{returner}")

        rows.append({
            "rally_id": rally["rally_id"],
            "scored": scored,
            "server": rally.get("server"),
            "point_winner": winner if scored else None,
            "game_points": dict(state["game_points"]),
            "set_games": dict(state["set_games"]),
            "sets_won": dict(state["sets_won"]),
            "in_tiebreak": state["in_tiebreak"],
            "events": events,
            "match_winner": state["match_winner"],
        })

    per_point_df = pd.DataFrame(rows)

    summary = {
        "players": players,
        "match_winner": state["match_winner"],
        "sets_won": dict(state["sets_won"]),
        "completed_sets": state["completed_sets"],
        "ambiguous_points_skipped": ambiguous_skipped,
        "post_match_rallies_ignored": post_match_ignored,
        "total_rallies": len(outcomes_df),
        "rallies_scored": len(outcomes_df) - ambiguous_skipped - post_match_ignored,
    }
    return per_point_df, summary


def _game_swap_parity(games_completed_in_set):
    return (math.ceil(games_completed_in_set / 2)) % 2 == 1


def _tiebreak_swap_parity(points_played_in_tiebreak):
    return (points_played_in_tiebreak // 6) % 2 == 1


def _current_swap_parity(state):
    if state["in_tiebreak"]:
        base = _game_swap_parity(2 * TIEBREAK_AT_GAMES)
        tb_points = sum(state["game_points"].values())
        return base != _tiebreak_swap_parity(tb_points)
    games_completed = sum(state["set_games"].values())
    return _game_swap_parity(games_completed)


def score_match_near_far(outcomes_df, end_swaps=None):
    """end_swaps: optional {rally_id: player_1_is_at_far_end} from
    player_appearance.rally_end_swaps (clothing colour). When given it
    replaces the game-count changeover rule, which breaks when points are
    missed or the players never change ends."""
    POSITIONAL = {"near", "far"}
    players = ("player_1", "player_2")
    state = _new_match_state(players)

    rows = []
    ambiguous_skipped = 0
    identity_unresolved = 0
    post_match_ignored = 0

    for _, rally in outcomes_df.sort_values("rally_id").iterrows():
        raw_winner = _norm(rally["winner"])
        raw_loser = _norm(rally["loser"])
        raw_server = _norm(rally.get("server"))

        post_match = state["match_winner"] is not None

        already_ambiguous = raw_winner in UNKNOWN_LABELS or raw_loser in UNKNOWN_LABELS
        identity_gap = (
            not already_ambiguous
            and (raw_winner not in POSITIONAL or raw_loser not in POSITIONAL)
        )
        resolvable = not already_ambiguous and not identity_gap

        swap = (end_swaps.get(int(rally["rally_id"]), False) if end_swaps is not None
                else _current_swap_parity(state))
        p1, p2 = players
        near_player, far_player = (p2, p1) if swap else (p1, p2)
        side_map = {"near": near_player, "far": far_player}

        winner = side_map.get(raw_winner) if resolvable else None
        loser = side_map.get(raw_loser) if resolvable else None
        server = side_map.get(raw_server, raw_server)

        scored = not post_match and resolvable

        events = []
        if post_match:
            events = ["post_match_rally_ignored"]
            post_match_ignored += 1
        elif not scored:
            if identity_gap:
                identity_unresolved += 1
            else:
                ambiguous_skipped += 1
        else:
            returner = p2 if server == p1 else p1 if server == p2 else None
            bp = (not state["in_tiebreak"]) and returner is not None and _is_break_point(state, server)

            events = _apply_point(state, winner, loser)

            if bp:
                game_won_event = next((e for e in events if e.startswith("game_won:")), None)
                if game_won_event:
                    game_winner = game_won_event.split(":", 1)[1]
                    outcome = "converted" if game_winner == returner else "faced_not_converted"
                    events.append(f"break_point_{outcome}:{returner}")

        rows.append({
            "rally_id": rally["rally_id"],
            "scored": scored,
            "near_player": near_player,
            "far_player": far_player,
            "server": server,
            "point_winner": winner if scored else None,
            "game_points": dict(state["game_points"]),
            "set_games": dict(state["set_games"]),
            "sets_won": dict(state["sets_won"]),
            "in_tiebreak": state["in_tiebreak"],
            "events": events,
            "match_winner": state["match_winner"],
        })

    per_point_df = pd.DataFrame(rows)

    summary = {
        "players": players,
        "match_winner": state["match_winner"],
        "sets_won": dict(state["sets_won"]),
        "completed_sets": state["completed_sets"],
        "ambiguous_points_skipped": ambiguous_skipped,
        "identity_unresolved_rallies": identity_unresolved,
        "post_match_rallies_ignored": post_match_ignored,
        "total_rallies": len(outcomes_df),
        "rallies_scored": (
            len(outcomes_df) - ambiguous_skipped - identity_unresolved - post_match_ignored
        ),
    }
    return per_point_df, summary


if __name__ == "__main__":
    # NOTE: this is a basic smoke test using the raw rally_outcomes.py output
    # (winner/loser as track_id strings), via score_match(). Given the known
    # track-ID churn across the video (700+ distinct player IDs), this WILL
    # report "expected exactly 2 known players" and refuse to score -- that's
    # expected, not a new bug. The real production path is score_match_near_far(),
    # which needs winner/loser already translated to "near"/"far" via
    # player_identity.py's rally-level mapping (see run_scoring_chain.py,
    # built 2026-09-17) -- not available in this reconstructed file, so it's
    # not wired up here. Feed this a genuinely 2-player outcomes_df (e.g. a
    # hand-filtered rally subset, or the near/far-translated output once
    # run_scoring_chain.py is available) to get a real scored result.
    outcomes_csv = str(config.EVENTS_CSV).replace("rally_events.csv", "rally_outcomes.csv")
    outcomes_df = pd.read_csv(outcomes_csv)

    per_point_df, summary = score_match(outcomes_df)
    print("score_match() smoke test (raw track_id winner/loser, no near/far translation):")
    for k, v in summary.items():
        print(f"  {k}: {v}")
