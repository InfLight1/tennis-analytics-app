"""
load_test.py

Team load test (2026-10-29): N players use Record match at the same moment
against one web server: start a recording, send the court picture, mark the
court, then stream video pieces (3 at a time, like the page) as if filming.
Reports how long each step took, the slowest player, and any errors.

It stops before "finish" on purpose: finishing starts the GPU analysis, which
costs money and can't run on this computer. So this checks the web part
(sign-in-free passcode path, court marking, piece uploads); GPU queueing for many
matches at once is worked out from the plan's limits (see TennisPerfApp.md).

Run against the local dev server (Code/dev_server.py --frame <court jpg>):
    python Code/load_test.py --players 30 --pieces 15 --piece-mb 2
Options: --url (default http://127.0.0.1:8770), --passcode (default test-1234),
--frame (court picture to send; default the dev server's test frame job).
"""

import argparse
import asyncio
import json
import os
import statistics
import time

import httpx

POINTS = {   # the hand-checked test frame (Diagnostics/calib_test_frame_clip2.jpg, 3840x2160)
    "baseline_near_left": [285.6, 1477.9], "baseline_near_right": [3168.1, 1405.3],
    "baseline_far_right": [2347.8, 489.0], "baseline_far_left": [1640.0, 529.8],
    "service_line_near_left": [1021.3, 962.9], "service_line_near_right": [2706.8, 891.0],
    "net_center": [1990.0, 640.0],
}


async def one_player(c, n, frame, pieces, piece, out):
    t = {"player": n, "errors": []}
    t0 = time.time()
    try:
        r = await c.post("/api/record/init", data={"mime": "video/webm"})
        r.raise_for_status()
        job = r.json()["job_id"]
        t["init_s"] = time.time() - t0
        t1 = time.time()
        r = await c.post(f"/api/record/{job}/frame", files={"file": ("court.jpg", frame, "image/jpeg")})
        r.raise_for_status()
        t["frame_s"] = time.time() - t1
        t1 = time.time()
        r = await c.post("/api/calibrate", data={"job_id": job, "points_json": json.dumps(POINTS),
                                                 "player1_name": f"Load {n}", "player2_name": "Opponent",
                                                 "match_type": "singles"})
        if r.status_code != 200:
            t["errors"].append(f"calibrate {r.status_code}: {r.text[:120]}")
        t["mark_s"] = time.time() - t1
        t1 = time.time()
        sem = asyncio.Semaphore(3)
        piece_times = []

        async def send(i):
            async with sem:
                s = time.time()
                rr = await c.put(f"/api/upload/{job}/part/{i}", content=piece)
                piece_times.append(time.time() - s)
                if rr.status_code != 200:
                    t["errors"].append(f"piece {i} {rr.status_code}")
        await asyncio.gather(*(send(i) for i in range(pieces)))
        t["upload_s"] = time.time() - t1
        t["piece_median_s"] = statistics.median(piece_times)
        t["piece_max_s"] = max(piece_times)
    except Exception as e:
        t["errors"].append(f"{type(e).__name__}: {e}")
    t["total_s"] = time.time() - t0
    out.append(t)


async def main(a):
    if a.frame:
        frame = open(a.frame, "rb").read()
    else:
        async with httpx.AsyncClient(base_url=a.url, headers={"x-passcode": a.passcode}, timeout=60) as c:
            frame = (await c.get("/api/frame/abcdef000001")).content
    piece = os.urandom(int(a.piece_mb * 1024 * 1024))
    out = []
    limits = httpx.Limits(max_connections=a.players * 3 + 10)
    async with httpx.AsyncClient(base_url=a.url, headers={"x-passcode": a.passcode}, timeout=300, limits=limits) as c:
        t0 = time.time()
        await asyncio.gather(*(one_player(c, n, frame, a.pieces, piece, out) for n in range(a.players)))
        wall = time.time() - t0
    mb = a.players * a.pieces * a.piece_mb
    errs = [e for t in out for e in t["errors"]]
    col = lambda k: [t[k] for t in out if k in t]
    print(f"{a.players} players at once, {a.pieces} pieces of {a.piece_mb} MB each ({mb:.0f} MB total) in {wall:.1f}s "
          f"({mb / wall:.0f} MB/s through the server)")
    for k, label in (("init_s", "start recording"), ("frame_s", "send court picture"), ("mark_s", "mark the court"),
                     ("piece_median_s", "one piece (median)"), ("piece_max_s", "one piece (slowest)"),
                     ("total_s", "whole player")):
        v = col(k)
        if v:
            print(f"  {label:<22} median {statistics.median(v):5.2f}s   slowest {max(v):5.2f}s")
    print(f"  errors: {len(errs)}" + (f" -> {errs[:5]}" if errs else ""))
    return 0 if not errs else 1


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="http://127.0.0.1:8770")
    ap.add_argument("--passcode", default="test-1234")
    ap.add_argument("--players", type=int, default=30)
    ap.add_argument("--pieces", type=int, default=15)
    ap.add_argument("--piece-mb", type=float, default=2.0)
    ap.add_argument("--frame")
    raise SystemExit(asyncio.run(main(ap.parse_args())))
