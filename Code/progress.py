"""
progress.py -- one player's progress across matches, from the per-match
player profiles the report already uses (profile.json -> players[pid]).

Weaknesses are compared as a RATE (points lost to it per 10 points played),
so a long match and a short one compare fairly. A trend needs at least two
matches with enough points; with less, the trend says "not enough yet"
instead of guessing (same honesty rule as the report's low_sample).

build(matches) -> {
  "matches":  [{job_id, date, points_played, points_won_pct, first_serve_in_pct,
                second_serve_in_pct, double_faults, top_fix}],   oldest first
  "weaknesses": [{id, title, rates: [per match, None if absent], trend,
                  change}],                                     worst latest first
  "focus":    {id, title, why} or None   -- "the one thing this week"
}
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
    """matches: [{"job_id", "date" (ISO string), "player": profile player dict}]."""
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
            "points_won_pct": st.get("points_won_pct"),
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

    focus = None
    if weaknesses and weaknesses[0]["rates"][-1] > 0:
        w = weaknesses[0]
        why = f"It cost about {w['rates'][-1]} of every 10 points in your latest match"
        if w["trend"] == "shrinking":
            why += ", and it's shrinking: keep at it."
        elif w["trend"] == "growing":
            why += ", and it's growing."
        else:
            why += "."
        focus = {"id": w["id"], "title": w["title"], "why": why}
    return {"matches": out_matches, "weaknesses": weaknesses, "focus": focus}
