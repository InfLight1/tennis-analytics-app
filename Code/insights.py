"""
insights.py -- the LLM suggestion layer (Week 2 #8, 2026-09-30).

Turns each player's ranked patterns (player_profile.build_profiles) into
actionable practice drills and match tactics with ONE Claude call per job,
cached by the caller (modal_app writes insights.json).

Decision D2 holds structurally: the model only sees diagnosed-pattern JSON
(titles, point counts, sample sizes, the playstyle line) -- never raw stats,
positions or video -- and is told not to prescribe stroke technique, which
the pipeline can't observe.

Model: Claude Haiku 4.5 -- the user asked for a budget model ($5 of credit).
Short structured output; ~2-3k input + ~1.5k output tokens per job, i.e.
well under a cent at $1 / $5 per million tokens.

Failure is non-fatal: any error returns None and the report page shows the
patterns without suggestions (plan fallback).

Usage (from Code/, needs ANTHROPIC_API_KEY):
  python insights.py <profile.json> [--out insights.json]
"""

import argparse
import json

MODEL = "claude-haiku-4-5"
MAX_TOKENS = 4000
MAX_WEAKNESSES = 4     # top headline + context weaknesses sent per player
MAX_STRENGTHS = 3

VERSION = 4   # bump to regenerate cached insights.json after a prompt change

SYSTEM = """You are a friendly tennis coach writing the "how to improve" section of a match report for club and school players.

You get, for each player, patterns diagnosed from tracked match video: a title, a detail line, how many points it cost or won, and how often it happened out of how many chances. Turn each pattern into advice the player can act on next time they play or practise.

For every pattern give:
0. headline: what happened and what it cost, at most 10 words (e.g. "Net errors cost you 4 points").
   try_this: the single most useful change for next time, at most 12 words, starting with a verb (e.g. "Aim higher over the net on every baseline shot").
Then the details behind a "show more" tap:
1. match_strategy: a change in what they choose to do during points (targets, shot choice, where to stand, when to attack or stay patient).
2. habit: a change in routine, mindset or body language they can apply right away (between-point routine, breathing before a second serve, committing to a target before swinging, resetting after an error).
3. practice_drill: one drill with a clear count or goal they can track (e.g. "hit 20 second serves; aim for 16 in the box").

Write so a 12-year-old understands it:
- Describe heights, distances and speeds with things they can picture on court, never bare numbers or percentages of effort. Say "aim so the ball would pass over the net by about a racket's length", "a target about as high as the top of the net post", "land the ball between the service line and the baseline", "a smooth swing you could repeat ten times in a row" - not "1 m clearance" or "75% pace".
- Short sentences, no jargon (if a tennis term is needed, explain it in a few words). Speak to the player as "you".
- match_strategy, habit and practice_drill: one short sentence each, at most 25 words. Players read this on a phone; every extra word gets skipped.
- Plain punctuation: no em dashes.

Rules:
- Ground every suggestion in the pattern's numbers and say why it matters ("this cost you 4 points"). Don't invent facts not in the data.
- Tactics, habits and practice only. Do not prescribe stroke mechanics (grip, swing path, footwork technique, body position): the video can't see technique, so that belongs to a coach.
- Weaknesses: what to change. Strengths: how to use it more on purpose.
- Use words like "early sign" only for patterns that happened fewer than 3 times.
- The game_summary is ONE sentence, at most 25 words: overall style, the biggest thing to fix, the best thing to keep."""

SCHEMA = {
    "type": "object",
    "properties": {
        "players": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "player_id": {"type": "string"},
                    "game_summary": {"type": "string"},
                    "insights": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "pattern_id": {"type": "string"},
                                "headline": {"type": "string"},
                                "try_this": {"type": "string"},
                                "match_strategy": {"type": "string"},
                                "habit": {"type": "string"},
                                "practice_drill": {"type": "string"},
                            },
                            "required": ["pattern_id", "headline", "try_this", "match_strategy", "habit", "practice_drill"],
                            "additionalProperties": False,
                        },
                    },
                },
                "required": ["player_id", "game_summary", "insights"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["players"],
    "additionalProperties": False,
}


def build_llm_input(profile):
    """Only diagnosed patterns + the playstyle line -- no raw stats/positions."""
    def pick(patterns, n):
        ranked = [p for p in patterns if not p.get("low_sample")]
        return [{k: p[k] for k in ("id", "kind", "title", "detail", "points", "occurrences", "chances")}
                for p in ranked[:n]]
    players = []
    for pid, pl in profile["players"].items():
        players.append({
            "player_id": pid,
            "playstyle": pl["playstyle"]["summary"],
            "points_won": pl["stats"]["points_won"], "points_lost": pl["stats"]["points_lost"],
            "weaknesses": pick(pl["weaknesses"], MAX_WEAKNESSES),
            "strengths": pick(pl["strengths"], MAX_STRENGTHS),
        })
    return {"players": players, "data_note": profile["coverage"]["notes"][0]}


def input_hash(profile):
    import hashlib
    return hashlib.sha256(json.dumps(build_llm_input(profile), sort_keys=True).encode()).hexdigest()[:16]


def generate_insights(profile, client=None):
    """Returns {"model":..., "players": {player_id: {...}}} or None on any failure."""
    try:
        import os
        import anthropic
        # Keys not tied to a workspace need the workspace named on each
        # request; optional ANTHROPIC_WORKSPACE_ID in the same Modal secret.
        ws = os.environ.get("ANTHROPIC_WORKSPACE_ID", "").strip()
        client = client or anthropic.Anthropic(
            default_headers={"anthropic-workspace-id": ws} if ws else None)
        payload = build_llm_input(profile)
        if not any(p["weaknesses"] or p["strengths"] for p in payload["players"]):
            return None
        response = client.messages.create(
            model=MODEL,
            max_tokens=MAX_TOKENS,
            system=SYSTEM,
            messages=[{"role": "user", "content":
                       "Write the insights for these players. Cover every pattern listed.\n\n"
                       + json.dumps(payload, indent=1)}],
            output_config={"format": {"type": "json_schema", "schema": SCHEMA}},
        )
        if response.stop_reason != "end_turn":
            print(f"[insights] stopped early: {response.stop_reason}")
            return None
        text = next(b.text for b in response.content if b.type == "text")
        data = json.loads(text)
        known = {p["player_id"]: {x["id"] for x in p["weaknesses"] + p["strengths"]}
                 for p in payload["players"]}
        out = {}
        for pl in data["players"]:
            pid = pl["player_id"]
            if pid not in known:
                continue
            out[pid] = {"game_summary": pl["game_summary"],
                        "insights": [i for i in pl["insights"] if i["pattern_id"] in known[pid]]}
        return {"model": MODEL, "version": VERSION, "input_hash": input_hash(profile), "players": out,
                "usage": {"input_tokens": response.usage.input_tokens,
                          "output_tokens": response.usage.output_tokens}}
    except Exception as e:                            # suggestions are optional -- never fail the job
        print(f"[insights] failed, report will show patterns without suggestions: {type(e).__name__}: {e}")
        return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("profile")
    ap.add_argument("--out")
    a = ap.parse_args()
    result = generate_insights(json.load(open(a.profile, encoding="utf-8")))
    text = json.dumps(result, indent=2)
    if a.out and result:
        open(a.out, "w", encoding="utf-8").write(text)
    print(text)


if __name__ == "__main__":
    main()
