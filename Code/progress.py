"""
progress.py -- one player's progress across matches, from the per-match
player profiles the report already uses (profile.json -> players[pid]).

Weaknesses are compared as a RATE (points lost to it per 10 points played),
so a long match and a short one compare fairly. A trend needs at least two
matches with enough points; with less, the trend says "not enough yet"
instead of guessing (same honesty rule as the report's low_sample).

build(matches) -> {
  "matches":  [{job_id, date, points_played, points_won, points_lost, points_won_pct,
                result (win/loss/None), result_from (player/app/points), sets,
                first_serve_in_pct, second_serve_in_pct, double_faults, top_fix}],   oldest first
  "weaknesses": [{id, title, rates: [per match, None if absent], trend,
                  change}],                                     worst latest first
  "focus":    {id, title, why} or None   -- "the one thing this week"
  "fixes":    latest report's top 3 fixes with advice and trend
  "strengths": latest report's top strengths [{id, title, detail, points}]
}
Each input match may also carry "slot", "match" (profile["match"]) and the
player's own "result", for the win/loss tag.
"""

MIN_POINTS = 10        # a match with fewer decided points says too little
STEADY_BAND = 0.5      # change in points lost per 10 played that counts as "about the same"


def _rate(pattern, points_played):
    if not points_played:
        return None
    return round(10 * pattern.get("points", 0) / points_played, 1)


def _trend(rates):
    known = [r for r in rates if r is not None]
    if len(known) < 2:
        return "not enough yet", None
    # latest vs. the average of the earlier matches (less jumpy than last-vs-previous)
    earlier = sum(known[:-1]) / len(known[:-1])
    change = round(known[-1] - earlier, 1)
    if change <= -STEADY_BAND:
        return "shrinking", change
    if change >= STEADY_BAND:
        return "growing", change
    return "about the same", change


def build(matches):
    """matches: [{"job_id", "date" (ISO string), "player": profile player dict,
    "advice": optional {pattern_id: AI advice dict} from that report's insights}]."""
    rows = sorted((m for m in matches if m.get("player")), key=lambda m: m.get("date") or "")
    out_matches, rates_by_id, titles = [], {}, {}
    usable = []
    for m in rows:
        pl, st = m["player"], m["player"].get("stats", {})
        sv = st.get("serve", {})
        played = st.get("points_played", 0)
        top = next((w for w in pl.get("weaknesses", []) if w.get("top")), None)
        out_matches.append({
            "job_id": m["job_id"], "date": m.get("date"), "points_played": played,
            "points_won": st.get("points_won"), "points_lost": st.get("points_lost"),
            "points_won_pct": st.get("points_won_pct"),
            **_result(m),
            "first_serve_in_pct": sv.get("first_serve_in_pct"),
            "second_serve_in_pct": sv.get("second_serve_in_pct"),
            "double_faults": sv.get("double_faults"),
            "top_fix": top and {"id": top["id"], "title": top["title"]},
            "enough": played >= MIN_POINTS,
        })
        if played >= MIN_POINTS:
            usable.append((m, played))

    for i, (m, played) in enumerate(usable):
        for w in m["player"].get("weaknesses", []):
            titles[w["id"]] = w["title"]
            rates_by_id.setdefault(w["id"], [None] * len(usable))[i] = _rate(w, played)
    # a weakness missing from a usable match lost 0 points there
    for rates in rates_by_id.values():
        for i, r in enumerate(rates):
            if r is None:
                rates[i] = 0.0

    weaknesses = []
    for wid, rates in rates_by_id.items():
        trend, change = _trend(rates)
        weaknesses.append({"id": wid, "title": titles[wid], "rates": rates, "trend": trend, "change": change})
    weaknesses.sort(key=lambda w: -(w["rates"][-1] if w["rates"] else 0))

    # Focus = the latest full match's "#1 fix" (same as its report says), with its trend.
    focus = None
    latest_top = next((w["id"] for w in usable[-1][0]["player"].get("weaknesses", []) if w.get("top")),
                      None) if usable else None
    pick = next((w for w in weaknesses if w["id"] == latest_top), None) or (weaknesses[0] if weaknesses else None)
    if pick and pick["rates"][-1] > 0:
        w = pick
        why = f"It cost about {w['rates'][-1]} of every 10 points in your latest match"
        if w["trend"] == "shrinking":
            why += ", and it's shrinking: keep at it."
        elif w["trend"] == "growing":
            why += ", and it's growing."
        else:
            why += "."
        focus = {"id": w["id"], "title": w["title"], "why": why}
    return {"matches": out_matches, "weaknesses": weaknesses, "focus": focus,
            "fixes": _fixes(rows, usable, weaknesses), "strengths": _strengths(rows, usable)}


def _result(m):
    """Win/loss: the player's own answer first; else the app's score, when it
    counted the match to the end; else whoever won more points (a tie stays
    blank). Set scores from the player's side."""
    slot, score = m.get("slot"), (m.get("match") or {}).get("score") or {}
    other = "player_2" if slot == "player_1" else "player_1"
    sets = [f"{a}-{b}" if slot == "player_1" else f"{b}-{a}" for a, b in score.get("completed_sets") or []]
    result, source = m.get("result"), "player" if m.get("result") else None
    st = (m.get("player") or {}).get("stats", {})
    won, lost = st.get("points_won"), st.get("points_lost")
    if not result and slot and score.get("match_winner") in (slot, other):
        result, source = ("win" if score["match_winner"] == slot else "loss"), "app"
    elif not result and won is not None and lost is not None and won != lost:
        result, source = ("win" if won > lost else "loss"), "points"
    return {"result": result, "result_from": source, "sets": sets}


def _strengths(rows, usable, limit=3):
    """What went well in the latest report (its top strengths, same order)."""
    src = usable[-1][0] if usable else (rows[-1] if rows else None)
    if not src:
        return []
    good = [s for s in src["player"].get("strengths", []) if s.get("top")] or src["player"].get("strengths", [])
    return [{"id": s["id"], "title": s["title"], "detail": s.get("detail"), "points": s.get("points", 0)}
            for s in good[:limit]]


def team_strengths(players, limit=3):
    """What the team does well: each player's latest strengths pooled by
    pattern, ranked by how many players have it, then points won."""
    pool = {}
    for p in players:
        for s in p.get("strengths") or []:
            e = pool.setdefault(s["id"], {"id": s["id"], "title": s["title"], "players": [], "points": 0})
            e["players"].append(p["name"])
            e["points"] += s.get("points", 0)
    return sorted(pool.values(), key=lambda e: (-len(e["players"]), -e["points"]))[:limit]


def team_focus(players, limit=3):
    """The team's shared weak spots, for the coach: each player's latest top
    fixes pooled by problem, ranked by how many players have it, then points
    lost. Each comes with one practice drill from the players' own reports
    (the one written for whoever lost the most points to it).
    players: [{"name", "fixes": progress fixes list}]."""
    pool = {}
    for p in players:
        for f in p.get("fixes") or []:
            e = pool.setdefault(f["id"], {"id": f["id"], "title": f["title"], "players": [], "points": 0,
                                          "drill": None, "_best": -1})
            e["players"].append(p["name"])
            e["points"] += f.get("points", 0)
            drill = (f.get("advice") or {}).get("practice_drill")
            if drill and f.get("points", 0) > e["_best"]:
                e["drill"], e["_best"] = drill, f.get("points", 0)
    ranked = sorted(pool.values(), key=lambda e: (-len(e["players"]), -e["points"]))
    return [{k: v for k, v in e.items() if k != "_best"} for e in ranked[:limit]]


ADVICE_KEYS = ("headline", "try_this", "match_strategy", "habit", "practice_drill")


def _fixes(rows, usable, weaknesses):
    """The latest report's top fixes (same order as the report) with its AI
    advice (tactic, habit, drill) and each one's trend across matches."""
    src = usable[-1][0] if usable else (rows[-1] if rows else None)
    if not src:
        return []
    advice = src.get("advice") or {}
    trends = {w["id"]: w["trend"] for w in weaknesses}
    tops = sorted((w for w in src["player"].get("weaknesses", []) if w.get("top")),
                  key=lambda w: w.get("rank", 99))
    return [{"id": w["id"], "title": w["title"], "points": w.get("points", 0), "job_id": src["job_id"],
             "trend": trends.get(w["id"], "not enough yet"),
             "advice": {k: advice[w["id"]][k] for k in ADVICE_KEYS if advice.get(w["id"], {}).get(k)}}
            for w in tops[:3]]
