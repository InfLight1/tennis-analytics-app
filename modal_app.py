"""
Modal app for the Tennis Performance pipeline.

Images (built + smoke-tested 2026-09-22, unchanged here):
  - gpu_image: detection.py only (torch/ultralytics on CUDA 12.8)
  - cpu_image: every other stage (transform, analysis, shot_type,
    player_identity, rally_outcomes, scoring, match_stats, prioritization,
    report)

This version wires the REAL, validated pipeline -- the chain built by
run_real_report.py / run_scoring_chain.py, NOT main.py's stage sequence.
main.py still calls player_id.py's assign_player_ids() (KMeans identity),
the approach the 2026-09-10 session found architecturally broken (10-18
ID churn, confirmed not fixable by buffer size) and replaced with the
near/far + player_identity.py + scoring.py swap-parity approach. main.py
was never updated after that pivot, so it is NOT used as the basis here.

Real pipeline wired below:
    detection.py (GPU)
      -> transform.py
      -> analysis.py (FRAME_HEIGHT auto-detected per job -- see note below)
      -> shot_type.py            [INCLUDED PER REQUEST -- see flag below]
      -> player_identity.py      (Pass 1: track_id -> near/far per rally)
      -> rally_outcomes.py       (winner/loser/server, derived from player_side)
      -> scoring.py              (Pass 2: near/far -> stable player_1/player_2)
      -> match_stats.py / prioritization.py / report.py

*** shot_type.py FLAG ***
shot_type.py (serve/volley/groundstroke) was built and validated ONLY
against synthetic data in Week 3 -- it was never wired into
run_real_report.py/run_scoring_chain.py, and had never been run against
real footage until this session. Included here per explicit request.

Running it against the real 40-min video's rally_events.csv (2026-09-23)
found a real bug: the original design used hit-event geometry (distance
from net) as the PRIMARY volley/groundstroke label, with a bounce-since-
last-hit check as a secondary cross-check. On real data these disagreed
on 62.2% of non-serve hits -- VOLLEY_ZONE_HALF_WIDTH_CM turned out to
cover nearly the whole forecourt, so most groundstrokes were being
mislabeled as volleys (141 volley vs 52 groundstroke -- implausible for
real baseline rally footage). Fixed by swapping which signal is primary:
bounce-since-last-hit (a volley is BY DEFINITION struck before the ball
bounces -- structural, not a proxy) now drives the label; geometry is
now the secondary cross-check. Re-run on the same real data: 128
groundstroke / 65 volley / 102 serve -- a far more plausible split.

Still, NEITHER signal is ground truth -- there is no manually-verified
shot-type dataset for this project (label_ground_truth.py only logs
bounce/hit/net timing). The disagreement rate (unchanged at 62.2%, since
it's symmetric either way) is now a signal that VOLLEY_ZONE_HALF_WIDTH_CM
itself needs re-deriving, not a signal about which label to trust. The
report's "shot_type_status" field says this plainly -- treat these
counts as a real improvement over the old code, not as validated.

*** FRAME_HEIGHT per-job fix ***
analysis.py's get_bounce_prominence/get_hit_prominence/
get_player_proximity_margin all default frame_height to config.FRAME_HEIGHT
as a FUNCTION-DEFINITION-TIME default -- mutating config.FRAME_HEIGHT after
analysis.py is first imported does NOT change already-bound defaults
(Python evaluates default args once, at def time). This is exactly the
class of bug that caused the 2026-09-19 near-total-data-loss incident
(2160p-fit thresholds silently applied to 1080p footage). Since Modal jobs
will process videos of whatever resolution the user uploads, this file
detects each job's real resolution via cv2 and reloads analysis.py AFTER
setting config.FRAME_HEIGHT, so the defaults rebind correctly per job.

Storage layout on the shared Volume (VOLUME_PATH = "/data"):
  /data/models/<ball_model_name>       -- your trained tennis ball detector
  /data/models/<player_model_name>     -- generic YOLOv8 person detector
  /data/jobs/<job_id>/input/video.mp4
  /data/jobs/<job_id>/perspective_matrix.npy
  /data/jobs/<job_id>/birdeye_check.jpg
  /data/jobs/<job_id>/status.json                  (polled by the demo UI)
  /data/jobs/<job_id>/raw_detection.csv
  /data/jobs/<job_id>/ball_candidates_debug.csv     (NEW -- see below)
  /data/jobs/<job_id>/match_data.csv
  /data/jobs/<job_id>/rally_events.csv
  /data/jobs/<job_id>/rally_events_resolved.csv   (Pass 1 output)
  /data/jobs/<job_id>/rally_events_stable.csv      (Pass 2 output, + shot_type)
  /data/jobs/<job_id>/match_report.json
  /data/jobs/<job_id>/match_report.txt
  /data/jobs/<job_id>/diagnose_<start>_<end>.csv    (NEW -- see
                                                      diagnose_frame_range_remote)

*** DEMO WEB UI, added 2026-09-23 ***
Built the actual upload -> calibrate -> process -> report flow, end to end,
for the demo. This is the piece that was "designed but not built" as of
2026-09-20 -- it's built now, via a FastAPI app served as a Modal web
endpoint (see `web_app` below), plus a single-file HTML page
(calibration_demo.html, delivered alongside this file) that:
  1. Uploads a video (POST /api/upload) -> gets back a job_id and the
     first frame.
  2. Shows that frame and walks the user through clicking the 7 court
     reference points in calibration.py's EXTENDED_POINT_LABELS order,
     using its own CLICK_INSTRUCTIONS text so the two never drift apart.
  3. Submits the clicks (POST /api/calibrate) -> this builds the
     perspective transform AND kicks off detection + the full CPU
     pipeline in the background (run_full_job_remote.spawn()) -- the
     endpoint returns immediately, it does not block on the ~minutes of
     processing.
  4. Polls GET /api/status/{job_id} every few seconds -- status.json
     tracks stage: uploaded -> calibrated -> detecting -> analyzing ->
     done | error. On "done" the response includes the full report JSON
     (report + shot_type_summary + shot_type_status, same shape as
     run_cpu_pipeline_remote's own output).

Deploy with `modal deploy modal_app.py`, copy the printed web_app URL
into calibration_demo.html's BACKEND_URL constant (top of the <script>
block), then open that HTML file directly in a browser -- no separate
frontend hosting needed for a demo.

Known limitations, worth stating before a live demo rather than
discovering mid-recording:
  - No auth on these endpoints -- fine for a demo on a private URL,
    NOT fine to leave deployed long-term.
  - Ball/player model names are hardcoded defaults
    (tennis_ball_best.pt / yolov8n.pt) in both the HTML and
    run_full_job_remote's signature -- upload your models under those
    exact names (see the CLI commands at the bottom of this docstring),
    or pass different names via the (optional) model-name fields in the
    HTML form.
  - The click UI trusts the user to click points in order and does not
    re-verify them against the video (e.g. no zoom/pan, no "redo last
    point" beyond a full reset) -- fine for a controlled demo recording,
    not yet a polished end-user tool.
  - A cold GPU container (first request after idle) adds real startup
    time before detection actually starts -- worth a test run before
    recording so the demo's pacing isn't a surprise.

NOT included in this pass (explicitly out of scope, flagged not silently
skipped):
  - court_coverage(): still explicitly skipped (player_csv=None), same as
    run_real_report.py -- it groups by raw track_id with no rally-id
    context and needs its own rally-aware rewrite (open item, ??9).

*** SETUP, before the first demo run ***
1. Upload your trained models to the volume (one-time, from your machine):
     modal volume put tennis-perf-storage path/to/best.pt models/tennis_ball_best.pt
     modal volume put tennis-perf-storage Code/yolov8n.pt models/yolov8n.pt
   (Match these filenames to the "Ball model filename"/"Player model
   filename" fields in calibration_demo.html, or change either side to
   match.)
2. Deploy:
     modal deploy modal_app.py
   Copy the printed web_app URL (ends in .modal.run).
3. Open calibration_demo.html in a browser, paste that URL into the
   "Backend URL" field, upload a video, click the 7 points, submit, watch
   it process, read the report.

*** UPLOAD FIX, 2026-09-24 ***
/api/upload previously did `f.write(await file.read())` (read the whole
body into memory, THEN write it) followed by a synchronous `volume.commit()`
-- for a ~1.4GB video this created a multi-minute window where the HTTP
connection sat completely idle (no bytes flowing either direction) while
the server wrote the file and synced the volume. A real browser upload
(via the demo HTML) consistently showed the client finishing the send
(100% progress) and then getting a bare network-error/connection-drop
before any response came back -- consistent with something on the network
path (router NAT, VPN, ISP) killing an idle connection during that
post-upload window. curl succeeded because (in the sessions tested) the
commit happened to be fast enough not to trip whatever idle timeout was
in play, not because the underlying issue wasn't real.

Fixed two ways:
  1. Stream the incoming file to disk in chunks (`await file.read(chunk_size)`
     in a loop) instead of reading the whole body into memory first --
     avoids an extra, slow, memory-heavy read-then-write pass after all
     bytes have already arrived.
  2. Run `volume.commit()` in a background thread and stream small
     keep-alive bytes back to the client while it runs, via a
     StreamingResponse. This keeps the connection demonstrably active
     (bytes flowing) for the whole commit duration, rather than sitting
     fully idle -- which is what a NAT/VPN/proxy is most likely to kill.
No client-side change is needed: calibration_demo.html's XHR-based upload
already just JSON.parses the response body once the request completes,
and a leading run of keep-alive bytes/whitespace before the JSON payload
parses fine.

*** UPLOAD FIX PART 2, 2026-09-25 ***
A subsequent real upload attempt stalled mid-transfer (77%) with the
Modal logs showing only OPTIONS preflight requests -- each with several
seconds of wall-clock duration but ~100ms of actual execution -- and no
POST /api/upload entry at all, meaning the real request either never
started cleanly or hit a cold container spin-up gap. Two changes:
  1. web_app now sets min_containers=1, keeping a container warm so
     /api/upload doesn't have to cold-start on the request that matters
     -- removes the multi-second acquisition gap seen in the logs before
     the real POST is even accepted.
  2. The upload loop now logs progress roughly every 100 MB written, so
     if a transfer stalls or dies again, Modal's logs show exactly how
     far it got instead of nothing at all.

*** DEPTH-ADAPTIVE BALL-TRACK FILTER, added this session ***
detection.py's ball-track displacement filter (accept/reject a candidate
point as "real ball motion" vs "near-static") is now depth-adaptive
(BALL_TRACK_MIN_DISPLACEMENT_NEAR_PX/FAR_PX in config.py), same pattern
as analysis.py's existing bounce/hit-prominence and player-proximity-
margin thresholds. See config.py/detection.py for the full rationale.
run_detection_remote below now also always writes a
ball_candidates_debug.csv per job (post-stitch candidate points, with
each point's depth-adjusted threshold and accept/reject decision) so this
can be tuned/audited offline without a GPU rerun per attempt -- pull it
with `modal volume get`.

*** LOW-CONFIDENCE FRAME-RANGE DIAGNOSTIC, added this session ***
Ground-truth comparison on job 76a383379d90 found the depth-adaptive
filter fix (above) had ZERO effect on the specific frame ranges where
real events were missing (e.g. 298-386, 954-2207 -- raw detection counts
in both ranges were byte-for-byte identical before/after the fix). That
rules out the displacement filter as the cause for THIS clip's problem
and points upstream, to whether the ball model is generating ANY
candidates there at all, independent of the production confidence
threshold. diagnose_frame_range_remote (new, below) reruns just the ball
model over a given frame range at a much lower confidence (default 0.02)
and dumps every raw box it finds, with no tracking/filtering applied at
all -- same purpose as the project's own diagnose_ball_candidates.py from
the 2026-09-09 session, just runnable on Modal against a job already on
the volume. Reads the video SEQUENTIALLY from frame 0 (not cap.set()
seeking) per the project's own 2026-09-09 finding that per-frame seeking
produces different frame content than production on fast motion --
inference is only actually run once start_frame is reached, so this
costs a bit of extra decode time but not extra GPU inference time.
"""

import json
import os

import modal

app = modal.App("tennis-perf-app")

# --- CPU image: no GPU needed, lighter build, faster cold starts ---
cpu_image = (
    modal.Image.debian_slim(python_version="3.12")
    .apt_install("libgl1", "libglib2.0-0",  # opencv runtime deps even without GPU use
                 "ffmpeg")                   # turns in-app recordings into a normal video file
    .pip_install(
        "numpy==2.4.6",
        "pandas==3.0.4",
        "opencv-python==5.0.0.93",
        "scipy==1.18.0",
        "matplotlib==3.11.0",
        "scikit-learn==1.9.0",
        "python-dateutil==2.9.0.post0",
        "six==1.17.0",
        "tzdata==2026.2",
        "fastapi==0.115.6",
        "python-multipart==0.0.20",
        "anthropic==1.11.0",   # insights.py (Week 2 #8): one Claude Haiku 4.5 call per job
        "boto3>=1.35",         # direct-to-storage uploads (Cloudflare R2, S3-compatible), off until the r2 secret exists
    )
    # Added LAST so editing pipeline code doesn't invalidate the pip layers above.
    .add_local_dir(
        "Code",
        remote_path="/root/Code",
        ignore=["__pycache__", "*.pyc", "*.csv", "*.json", "*.txt", "*.jpg",
                "*.png", "*.npy", "*.pt", "*.md", "legacy"],
    )
    # The web pages, served by web_app so a phone can just open a link.
    .add_local_file("report.html", "/root/web/report.html")
    .add_local_file("calibration_demo.html", "/root/web/calibration_demo.html")
    .add_local_file("camera_test.html", "/root/web/camera_test.html")
    # passcode.js, manifest + icons (install-on-phone). Served at the site root.
    .add_local_dir("web_assets", remote_path="/root/web/assets")
)

# Week 3 guardrails. The passcode lives in the Modal secret "app-passcode"
# (key APP_PASSCODE); every /api/ route needs it in an X-Passcode header.
MAX_VIDEO_MINUTES = 60

# --- GPU image: adds ultralytics + torch (CUDA build) on top of a CUDA base ---
gpu_image = (
    modal.Image.from_registry(
        "nvidia/cuda:12.8.0-cudnn-runtime-ubuntu22.04", add_python="3.12"
    )
    .apt_install("libgl1", "libglib2.0-0")
    .pip_install(
        "numpy==2.4.6",
        "pandas==3.0.4",
        "opencv-python==5.0.0.93",
        "scipy==1.18.0",
        "supervision==0.29.1",
        "ultralytics==8.4.87",
        "python-dateutil==2.9.0.post0",
        "six==1.17.0",
        "tzdata==2026.2",
    )
    # torch/torchvision pulled from PyTorch's own CUDA 12.8 index, not PyPI defaults
    .pip_install(
        "torch",
        "torchvision",
        index_url="https://download.pytorch.org/whl/cu128",
    )
    .add_local_dir(
        "Code",
        remote_path="/root/Code",
        ignore=["__pycache__", "*.pyc", "*.csv", "*.json", "*.txt", "*.jpg",
                "*.png", "*.npy", "*.pt", "*.md", "legacy"],
    )
)

# Shared storage for models, videos, and per-job intermediate/output files
volume = modal.Volume.from_name("tennis-perf-storage", create_if_missing=True)
VOLUME_PATH = "/data"
EXAMPLE_JOB_ID = "76a383379d90"   # showcase match; its report is public (no passcode)
JOBS_DIR = f"{VOLUME_PATH}/jobs"
MODELS_DIR = f"{VOLUME_PATH}/models"


def _job_paths(job_id: str) -> dict:
    d = f"{JOBS_DIR}/{job_id}"
    return {
        "job_dir": d,
        "video_path": f"{d}/input/video.mp4",
        "matrix_path": f"{d}/perspective_matrix.npy",
        "birdeye_check_path": f"{d}/birdeye_check.jpg",
        "raw_csv_path": f"{d}/raw_detection.csv",
        # NEW -- post-stitch ball candidate dump (every point considered,
        # with its depth-adjusted threshold and accept/reject decision),
        # written every run so the depth-adaptive filter can be
        # tuned/audited offline without a GPU rerun per attempt.
        "ball_candidates_debug_path": f"{d}/ball_candidates_debug.csv",
        "match_csv_path": f"{d}/match_data.csv",
        "events_csv_path": f"{d}/rally_events.csv",
        "resolved_events_csv_path": f"{d}/rally_events_resolved.csv",
        "stable_events_csv_path": f"{d}/rally_events_stable.csv",
        "report_json_path": f"{d}/match_report.json",
        "report_summary_path": f"{d}/match_report.txt",
        # Week 2 (2026-09-30): per-player profile for the report page, the
        # player names entered at calibration, and the cached LLM insights.
        "profile_json_path": f"{d}/profile.json",
        "names_json_path": f"{d}/names.json",
        "insights_json_path": f"{d}/insights.json",
    }


def _import_pipeline():
    """Puts the bundled Code/ dir on sys.path and imports every CPU-safe
    pipeline module. Safe to call repeatedly within one container (import
    caching).

    Deliberately does NOT import detection.py -- it does `import
    supervision` at module level, which only exists in gpu_image.
    cpu_image (used by run_cpu_pipeline_remote, run_calibration_remote,
    and web_app) does not have supervision/ultralytics/torch installed,
    so importing detection here would crash every CPU-image function on
    startup. Caught by a local `.local()` test of web_app before this was
    ever deployed -- see run_detection_remote for the one place detection
    is actually imported, on gpu_image where its deps exist.
    """
    import sys
    if "/root/Code" not in sys.path:
        sys.path.insert(0, "/root/Code")
    import config
    import calibration
    import transform
    import analysis
    import player_identity
    import rally_outcomes
    import scoring
    import shot_type
    import match_stats
    import prioritization
    import report
    import player_profile
    import player_appearance
    return dict(
        config=config, calibration=calibration,
        transform=transform, analysis=analysis, player_identity=player_identity,
        rally_outcomes=rally_outcomes, scoring=scoring, shot_type=shot_type,
        match_stats=match_stats, prioritization=prioritization, report=report,
        player_profile=player_profile, player_appearance=player_appearance,
    )


def _read_json(path, default=None):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


# ---------------------------------------------------------------------------
# Stage 0: calibration (CPU, run once per camera setup / per job if the
# angle changed). Takes already-collected click coordinates -- see the
# module docstring's "DEMO WEB UI" section for how the click UI supplies
# them.
# ---------------------------------------------------------------------------
@app.function(image=cpu_image, volumes={VOLUME_PATH: volume})
def run_calibration_remote(job_id: str, clicked_points_px: dict):
    mods = _import_pipeline()
    p = _job_paths(job_id)
    os.makedirs(os.path.dirname(p["matrix_path"]), exist_ok=True)

    M = mods["calibration"].build_perspective_transform(
        clicked_points_px=clicked_points_px,
        video_path=p["video_path"],
        matrix_path=p["matrix_path"],
        birdeye_check_path=p["birdeye_check_path"],
        display=False,  # headless -- see calibration.py's own docstring for this flag
    )
    volume.commit()
    return {"matrix_path": p["matrix_path"], "matrix_shape": list(M.shape)}


# ---------------------------------------------------------------------------
# Stage 1: detection (GPU). The one stage that needs CUDA.
# ---------------------------------------------------------------------------
@app.function(image=gpu_image, gpu="T4", volumes={VOLUME_PATH: volume}, timeout=10800)  # 3h: 4K footage now runs the ball model at imgsz 2560 (config.ball_inference_imgsz), ~3-4x slower per frame
def run_detection_remote(job_id: str, ball_model_name: str, player_model_name: str,
                          ball_conf: float = None):
    """
    ball_conf : float, optional
        Overrides detection.py's own default (config.BALL_CONF_THRESHOLD,
        0.3) for JUST this call -- doesn't touch config.py, doesn't change
        behavior for any other job or any run that omits this argument.
        Added so that if diagnose_frame_range_remote's low-confidence scan
        shows real candidates sitting below 0.3 in a dead zone, you can
        immediately rerun production detection at a lower value from the
        command line (`--ball-conf 0.15`, say) without waiting on another
        code edit/redeploy cycle. NOT yet validated against real data --
        treat any run using this as an experiment, not a default.
    """
    import sys
    if "/root/Code" not in sys.path:
        sys.path.insert(0, "/root/Code")
    import detection  # only imported here -- needs supervision/torch/ultralytics,
                       # which only exist in gpu_image (see _import_pipeline's docstring)

    p = _job_paths(job_id)

    ball_model_path = f"{MODELS_DIR}/{ball_model_name}"
    player_model_path = f"{MODELS_DIR}/{player_model_name}"
    for path in (ball_model_path, player_model_path, p["video_path"]):
        if not os.path.exists(path):
            raise FileNotFoundError(
                f"{path} not found on the volume -- upload it first "
                f"(see the local_entrypoint's upload step)."
            )

    os.makedirs(p["job_dir"], exist_ok=True)
    kwargs = dict(
        video_path=p["video_path"],
        ball_model_path=ball_model_path,
        player_model_path=player_model_path,
        raw_csv_path=p["raw_csv_path"],
        # NEW -- always dump the post-stitch candidate pool for this job.
        # Cheap (one extra CSV write of data already computed in memory)
        # and turns "why did coverage not improve here" from a guess into
        # something checkable without a second GPU pass.
        debug_dump_path=p["ball_candidates_debug_path"],
    )
    if ball_conf is not None:
        print(f"[job {job_id}] overriding ball_conf to {ball_conf} "
              f"(production default is config.BALL_CONF_THRESHOLD) -- experimental")
        kwargs["ball_conf"] = ball_conf
    detection.run_detection(**kwargs)
    volume.commit()
    return {
        "raw_csv_path": p["raw_csv_path"],
        "ball_candidates_debug_path": p["ball_candidates_debug_path"],
        "ball_conf_used": ball_conf if ball_conf is not None else "config.BALL_CONF_THRESHOLD (default)",
    }


# ---------------------------------------------------------------------------
# NEW this session -- low-confidence, no-tracking, no-filtering diagnostic
# over a specific frame range. Answers "does the ball model see anything
# here AT ALL" independent of the production confidence threshold, the
# displacement filter, or ByteTrack -- separate question from
# run_detection_remote's own dump above, which only shows candidates that
# already cleared ball_conf (0.3 by default) and got tracked. See module
# docstring for why this was needed (the depth-adaptive filter fix showed
# zero effect on the specific frame ranges where events are missing).
#
# Reads the video SEQUENTIALLY from frame 0, per the project's own
# 2026-09-09 finding that cap.set()-based per-frame seeking can return
# different frame content than production's sequential read, especially
# on fast motion -- inference only actually runs once start_frame is
# reached, so this costs extra decode time, not extra GPU time.
#
# Usage:
#   modal run modal_app.py::diagnose_frame_range_remote --job-id <id> \
#       --ball-model-name tennis_ball_best.pt --start-frame 298 --end-frame 386
# ---------------------------------------------------------------------------
@app.function(image=gpu_image, gpu="T4", volumes={VOLUME_PATH: volume}, timeout=1800)
def diagnose_frame_range_remote(
    job_id: str,
    ball_model_name: str,
    start_frame: int,
    end_frame: int,
    low_conf: float = 0.02,
    imgsz: int = 1280,
):
    import cv2
    import pandas as pd
    from ultralytics import YOLO

    p = _job_paths(job_id)
    ball_model_path = f"{MODELS_DIR}/{ball_model_name}"
    if not os.path.exists(ball_model_path):
        raise FileNotFoundError(f"{ball_model_path} not found on the volume.")
    if not os.path.exists(p["video_path"]):
        raise FileNotFoundError(f"{p['video_path']} not found on the volume.")

    model = YOLO(str(ball_model_path))
    cap = cv2.VideoCapture(p["video_path"])

    rows = []
    frame_num = 0
    n_scanned = 0
    print(f"[job {job_id}] scanning frames {start_frame}-{end_frame} at conf={low_conf} "
          f"(sequential read from frame 0, per the project's own per-frame-seek caveat)")
    while cap.isOpened():
        ret, frame = cap.read()
        if not ret or frame_num > end_frame:
            break
        if frame_num >= start_frame:
            n_scanned += 1
            results = model(frame, conf=low_conf, imgsz=imgsz)[0]
            for box in results.boxes:
                x1, y1, x2, y2 = box.xyxy[0].tolist()
                rows.append({
                    "frame": frame_num,
                    "pixel_x": (x1 + x2) / 2, "pixel_y": (y1 + y2) / 2,
                    "x1": x1, "y1": y1, "x2": x2, "y2": y2,
                    "confidence": float(box.conf[0]),
                })
        frame_num += 1
    cap.release()

    out_path = f"{p['job_dir']}/diagnose_{start_frame}_{end_frame}.csv"
    df = pd.DataFrame(rows)
    df.to_csv(out_path, index=False)
    volume.commit()

    n_frames_with_any_candidate = df["frame"].nunique() if len(df) else 0
    print(f"[job {job_id}] {len(rows)} raw box(es) across {n_frames_with_any_candidate}/"
          f"{n_scanned} scanned frames -- saved to {out_path}")
    return {
        "output_path": out_path,
        "n_candidates": len(rows),
        "n_frames_scanned": n_scanned,
        "n_frames_with_any_candidate": n_frames_with_any_candidate,
    }


# ---------------------------------------------------------------------------
# Stage 2: everything else (CPU). transform -> analysis -> shot_type ->
# player_identity (pass 1) -> rally_outcomes -> scoring (pass 2) -> report.
# Mirrors run_real_report.py's two-pass identity resolution, with the
# per-job FRAME_HEIGHT fix and shot_type merged in.
# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
# Chunked, parallel detection (added 2026-09-27). Wall-clock time for the
# demo: 4K at imgsz 2560 runs ~13 fps on an RTX 4070 laptop (slower on a
# T4), i.e. ~30-60+ min for a 12-min video in one container. Splitting the
# video into DETECTION_CHUNK_FRAMES pieces and running them in parallel
# containers divides that by the number of chunks. Downscaling instead was
# measured and rejected: 1080p/1440p/4K@1920 all cost 6-10 points of event
# F1 (TennisPerfApp.md §5).
#
# Each chunk writes its RAW ball candidates + player rows to the volume;
# merge_detection_remote then runs the ball linker once over the whole
# video, so chunk boundaries don't cut ball trajectories (validated
# locally: chunked == single-pass ball output, 684/684 frames identical).
#
# DETECTION_GPU: pick with `modal run modal_app.py::benchmark_gpus`.
# ---------------------------------------------------------------------------
# Chosen 2026-09-28 from benchmark_gpus on job 76a383379d90 (detect+decode fps,
# 14-min clip with 10 parallel chunks): L40S 17.7 fps / ~2.1 min / $0.67;
# A10 15.4 / ~2.4 min / $0.43; L4 14.9 / ~2.4 min / $0.33; T4 9.4 / ~3.9 min /
# $0.38. L4: ~20s slower than L40S at half the cost -- 4K decode, not the GPU,
# is the bottleneck. Ordered fallbacks keep jobs running if L4 capacity is short.
DETECTION_GPU = ["L4", "A10", "L40S"]
DETECTION_CHUNK_FRAMES = 1800        # minimum chunk: ~60s of 30fps video per container
DETECTION_MAX_PARALLEL = 10          # Modal Starter plan GPU concurrency limit (Team: 50) --
                                     # longer videos get bigger chunks rather than a 2nd wave
PLAYER_ID_OFFSET_PER_CHUNK = 100_000  # keeps ByteTrack ids unique across chunks


# cpu=4: 4K decode + resize is the local bottleneck (GPU ~30% busy on an RTX 4070),
# and GPU containers otherwise get a small CPU share. ~$0.19/hr extra per container.
@app.function(image=gpu_image, gpu=DETECTION_GPU, cpu=4.0, volumes={VOLUME_PATH: volume}, timeout=3600)
def detect_chunk_remote(job_id: str, ball_model_name: str, player_model_name: str,
                        start_frame: int, end_frame: int, chunk_idx: int,
                        write_output: bool = True) -> dict:
    import sys
    import time
    import pandas as pd
    if "/root/Code" not in sys.path:
        sys.path.insert(0, "/root/Code")
    import detection

    p = _job_paths(job_id)
    t0 = time.time()
    balls, players = detection.detect_chunk(
        p["video_path"], f"{MODELS_DIR}/{ball_model_name}", f"{MODELS_DIR}/{player_model_name}",
        start_frame, end_frame, player_track_id_offset=chunk_idx * PLAYER_ID_OFFSET_PER_CHUNK,
    )
    seconds = time.time() - t0
    if write_output:
        chunk_dir = f"{p['job_dir']}/chunks"
        os.makedirs(chunk_dir, exist_ok=True)
        pd.DataFrame(balls).to_csv(f"{chunk_dir}/ball_{chunk_idx:03d}.csv", index=False)
        pd.DataFrame(players).to_csv(f"{chunk_dir}/players_{chunk_idx:03d}.csv", index=False)
        volume.commit()
    return {"chunk": chunk_idx, "frames": end_frame - start_frame, "seconds": round(seconds, 1),
            "fps": round((end_frame - start_frame) / seconds, 2) if seconds else None}


@app.function(image=cpu_image, volumes={VOLUME_PATH: volume}, timeout=3600)  # 50-60 min videos: linker over the whole video
def merge_detection_remote(job_id: str, n_chunks: int, total_frames: int) -> dict:
    import sys
    import pandas as pd
    if "/root/Code" not in sys.path:
        sys.path.insert(0, "/root/Code")
    import detection_merge

    volume.reload()
    p = _job_paths(job_id)
    chunk_dir = f"{p['job_dir']}/chunks"

    def _records(path):
        try:
            return pd.read_csv(path).to_dict("records")
        except pd.errors.EmptyDataError:   # chunk with no detections at all
            return []

    results = [(_records(f"{chunk_dir}/ball_{i:03d}.csv"), _records(f"{chunk_dir}/players_{i:03d}.csv"))
               for i in range(n_chunks)]
    n_rows = detection_merge.merge_and_link(
        results, total_frames, p["raw_csv_path"], debug_dump_path=p["ball_candidates_debug_path"]
    )
    volume.commit()
    return {"raw_csv_path": p["raw_csv_path"], "rows": n_rows}


def _video_frame_count(video_path: str) -> int:
    import cv2
    cap = cv2.VideoCapture(video_path)
    n = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    cap.release()
    if n <= 0:
        raise RuntimeError(f"Could not read frame count from {video_path}")
    return n


def _run_detection_chunked(job_id: str, ball_model_name: str, player_model_name: str) -> dict:
    """Plan chunks -> run them in parallel GPU containers -> merge + link.
    Must run inside a Modal container that mounts the volume (orchestrator)."""
    import sys
    import time
    if "/root/Code" not in sys.path:
        sys.path.insert(0, "/root/Code")
    import detection_merge

    volume.reload()
    p = _job_paths(job_id)
    total = _video_frame_count(p["video_path"])
    chunk_frames = max(DETECTION_CHUNK_FRAMES, -(-total // DETECTION_MAX_PARALLEL))
    chunks = detection_merge.plan_chunks(total, chunk_frames)
    print(f"[job {job_id}] {total} frames -> {len(chunks)} chunks of {chunk_frames} on {DETECTION_GPU}")
    _write_status(job_id, message=f"Detecting ball/players: {len(chunks)} parallel chunks on {DETECTION_GPU}...")

    t0 = time.time()
    stats = list(detect_chunk_remote.starmap(
        [(job_id, ball_model_name, player_model_name, s, e, i) for i, (s, e) in enumerate(chunks)]
    ))
    t_detect = time.time() - t0
    merged = merge_detection_remote.remote(job_id, len(chunks), total)
    summary = {"frames": total, "chunks": len(chunks), "gpu": DETECTION_GPU,
               "detect_wall_seconds": round(t_detect, 1),
               "slowest_chunk_seconds": max(s["seconds"] for s in stats),
               "mean_chunk_fps": round(sum(s["fps"] or 0 for s in stats) / len(stats), 2),
               "total_wall_seconds": round(time.time() - t0, 1), **merged}
    print(f"[job {job_id}] detection summary: {summary}")
    with open(f"{p['job_dir']}/detection_summary.json", "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, default=str)   # timing per job, readable without the logs
    volume.commit()
    return summary


@app.function(image=cpu_image, volumes={VOLUME_PATH: volume}, timeout=14400)
def run_detection_chunked_remote(job_id: str, ball_model_name: str, player_model_name: str) -> dict:
    return _run_detection_chunked(job_id, ball_model_name, player_model_name)


# ---------------------------------------------------------------------------
# GPU benchmark: same chunk of a real job's video on each GPU type, no
# output written. Prints fps (inference only) and wall time incl. cold start
# and model load, plus the cost of processing a 12-min 4K video's worth of
# frames. Usage (job must already have video.mp4 on the volume):
#   modal run modal_app.py::benchmark_gpus --job-id 76a383379d90
# ---------------------------------------------------------------------------
GPU_PRICE_PER_HR = {"T4": 0.59, "L4": 0.80, "A10": 1.10, "L40S": 1.95, "A100-40GB": 2.10, "H100": 3.95}


@app.local_entrypoint()
def benchmark_gpus(job_id: str, frames: int = 450, start_frame: int = 1200,
                   gpus: str = "T4,L4,A10,L40S",
                   ball_model_name: str = "tennis_ball_best.pt", player_model_name: str = "yolov8n.pt"):
    import time
    full_video_frames = 21_799   # the 14-min job clip, for the cost estimate
    print(f"Benchmarking frames {start_frame}-{start_frame + frames} of job {job_id}\n")
    for i, g in enumerate(gpus.split(",")):
        fn = detect_chunk_remote.with_options(gpu=g)
        t0 = time.time()
        r = fn.remote(job_id, ball_model_name, player_model_name,
                      start_frame, start_frame + frames, 900 + i, False)
        wall = time.time() - t0
        fps = r["fps"] or 0
        gpu_hours = full_video_frames / fps / 3600 if fps else float("nan")
        cost = gpu_hours * GPU_PRICE_PER_HR.get(g, float("nan"))
        n_chunks = min(DETECTION_MAX_PARALLEL, -(-full_video_frames // DETECTION_CHUNK_FRAMES))
        print(f"{g:>10}: {fps:6.2f} fps (detect+decode), wall {wall:5.0f}s incl. cold start | "
              f"full 14-min video: {gpu_hours * 60:5.1f} GPU-min, ~${cost:.2f}, "
              f"~{gpu_hours * 60 / n_chunks:.1f} min detection wall-clock with {n_chunks} parallel chunks "
              f"(+ cold start + frame skipping)")


@app.function(image=cpu_image, volumes={VOLUME_PATH: volume}, timeout=3600,  # 50-60 min videos need more than 30 min headroom
              # ANTHROPIC_API_KEY for insights.py; created with
              # `modal secret create anthropic ANTHROPIC_API_KEY=...`
              secrets=[modal.Secret.from_name("anthropic")])
def run_cpu_pipeline_remote(job_id: str):
    import importlib
    import cv2
    import pandas as pd

    mods = _import_pipeline()
    config = mods["config"]
    transform = mods["transform"]
    analysis = mods["analysis"]
    shot_type = mods["shot_type"]
    player_identity = mods["player_identity"]
    rally_outcomes = mods["rally_outcomes"]
    scoring = mods["scoring"]
    report = mods["report"]

    p = _job_paths(job_id)

    # -- FRAME_HEIGHT: detect THIS job's real resolution, don't trust
    # whatever config.py happened to be set to for a previous video (see
    # module docstring -- this is the exact bug class from 2026-09-19). --
    cap = cv2.VideoCapture(p["video_path"])
    real_height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    cap.release()
    if not real_height:
        raise RuntimeError(f"Could not read frame height from {p['video_path']}")
    config.FRAME_HEIGHT = real_height
    analysis = importlib.reload(analysis)  # rebinds get_*_prominence defaults
    print(f"[job {job_id}] detected FRAME_HEIGHT={real_height}, analysis.py reloaded against it")

    # -- transform: raw pixel detections -> table coordinates --------------
    transform.interpolate_and_transform(
        raw_csv_path=p["raw_csv_path"],
        matrix_path=p["matrix_path"],
        output_csv_path=p["match_csv_path"],
    )

    # -- analysis: rally segmentation + hit/bounce event detection ---------
    analysis.run_analysis(p["match_csv_path"], output_path=p["events_csv_path"])

    # -- shot_type: serve/volley/groundstroke classification ----------------
    # Bounce-primary as of the 2026-09-23 fix -- see module docstring for
    # why. Still no ground-truth validation. Computed on the raw events
    # (rally_id/event_type/frame/table_x, none of which change under the
    # relabel passes below) and merged into the final stable-events CSV.
    events_df = pd.read_csv(p["events_csv_path"])
    classified_df = shot_type.classify_shot_types(events_df)
    shot_type_summary = shot_type.shot_type_summary(classified_df)

    # -- player_identity Pass 1: raw track_id -> near/far per rally ---------
    match_data_df = pd.read_csv(p["match_csv_path"])
    labels, qa_df = player_identity.compute_rally_near_far_labels(match_data_df, classified_df)
    n_total, n_resolved = len(qa_df), len(labels)
    print(f"[job {job_id}] Pass 1: resolved near/far for {n_resolved}/{n_total} rallies")

    resolved_events_df = player_identity.relabel_events_to_near_far(classified_df, labels)
    resolved_events_df.to_csv(p["resolved_events_csv_path"], index=False)

    # -- scoring Pass 2: near/far -> match-stable player_1/player_2 ---------
    outcomes_df = rally_outcomes.rally_outcomes(resolved_events_df)
    # who is at which end, by clothing colour (falls back to game counting)
    try:
        end_swaps = mods["player_appearance"].rally_end_swaps(p["video_path"], match_data_df, resolved_events_df)
    except Exception as e:
        print(f"[job {job_id}] appearance check failed, using game-count end swaps: {e}")
        end_swaps = None
    per_point_df, score_summary = scoring.score_match_near_far(outcomes_df, end_swaps)
    print(f"[job {job_id}] Pass 2 scoring summary: {score_summary}")

    rally_stable_labels = {
        int(row.rally_id): {"near": row.near_player, "far": row.far_player}
        for row in per_point_df.itertuples()
    }
    stable_events_df = resolved_events_df.copy()
    stable_events_df["player_side"] = [
        rally_stable_labels.get(rid, {}).get(val, val)
        for rid, val in zip(stable_events_df["rally_id"], stable_events_df["player_side"])
    ]
    stable_events_df.to_csv(p["stable_events_csv_path"], index=False)

    # -- report: match_stats -> prioritization -> report on STABLE data ----
    # court_coverage still explicitly skipped (player_csv=None) -- see
    # module docstring's "NOT included in this pass" note.
    full_report = report.generate_report(
        p["stable_events_csv_path"],
        player_csv=None,
        json_path=p["report_json_path"],
        summary_path=p["report_summary_path"],
    )

    # Fold shot_type in -- not part of report.generate_report()'s own output,
    # since none of report.py/match_stats.py/prioritization.py/
    # rally_outcomes.py reference shot_type (confirmed by grep).
    full_report["shot_type_summary"] = shot_type_summary
    full_report["shot_type_status"] = (
        "NOT GROUND-TRUTH VALIDATED - bounce-primary label as of the "
        "2026-09-23 fix (see modal_app.py/shot_type.py docstrings); no "
        "manually-verified shot-type dataset exists for this project yet. "
        "geometry_bounce_disagreement flags where the secondary geometry "
        "check disagrees - a high rate here means VOLLEY_ZONE_HALF_WIDTH_CM "
        "needs re-deriving, not that the count is necessarily wrong."
    )
    with open(p["report_json_path"], "w", encoding="utf-8") as f:
        json.dump(report._df_to_records(full_report), f, indent=2, default=str)
    with open(p["report_summary_path"], "a", encoding="utf-8") as f:
        f.write("\n\n--- SHOT TYPE (not ground-truth validated) ---\n")
        f.write(json.dumps(shot_type_summary, indent=2, default=str))
        f.write("\n")

    # -- player profile (Week 2): what the report page shows ---------------
    names = _read_json(p["names_json_path"], {}) or {}
    import cv2
    cap = cv2.VideoCapture(p["video_path"])
    video_fps = cap.get(cv2.CAP_PROP_FPS) or None      # None -> report shows no video times
    cap.release()
    profile = mods["player_profile"].build_profiles(resolved_events_df, match_data_df, names, end_swaps,
                                                    fps=video_fps)
    with open(p["profile_json_path"], "w", encoding="utf-8") as f:
        json.dump(profile, f, indent=2, default=str)

    # -- LLM insights (Week 2 #8): one Claude Haiku 4.5 call, cached per job.
    # A re-run (rerun_cpu_stages) reuses insights.json instead of paying
    # again; delete that file to regenerate. Failure -> no file, and the
    # report page shows the patterns without suggestions.
    import insights as insights_mod
    cached = _read_json(p["insights_json_path"])
    # regenerate when the prompt version OR the stats it's based on change
    if (not cached or cached.get("version") != insights_mod.VERSION
            or cached.get("input_hash") != insights_mod.input_hash(profile)):
        result = insights_mod.generate_insights(profile)
        if result:
            with open(p["insights_json_path"], "w", encoding="utf-8") as f:
                json.dump(result, f, indent=2)
            print(f"[job {job_id}] insights generated: {result['usage']}")

    volume.commit()
    return {
        "report_json_path": p["report_json_path"],
        "report_summary_path": p["report_summary_path"],
        "pass1_resolved": f"{n_resolved}/{n_total}",
        "pass2_scoring_summary": score_summary,
        "shot_type_summary": shot_type_summary,
    }


def _write_status(job_id: str, **fields):
    """Writes /data/jobs/<job_id>/status.json and commits, so the web
    endpoint (a different container) sees it on its next reload/read.
    Merges with whatever's already there rather than overwriting stage
    history."""
    p = _job_paths(job_id)
    status_path = f"{p['job_dir']}/status.json"
    os.makedirs(p["job_dir"], exist_ok=True)
    current = {}
    if os.path.exists(status_path):
        try:
            with open(status_path) as f:
                current = json.load(f)
        except Exception:
            pass
    current.update(fields)
    with open(status_path, "w", encoding="utf-8") as f:
        json.dump(current, f, indent=2, default=str)
    volume.commit()


def _read_status(job_id: str) -> dict:
    volume.reload()
    p = _job_paths(job_id)
    status_path = f"{p['job_dir']}/status.json"
    if not os.path.exists(status_path):
        return {"stage": "unknown", "message": f"No job found for id {job_id}"}
    with open(status_path) as f:
        return json.load(f)


# ---------------------------------------------------------------------------
# Background orchestrator: calibration already done by the time this is
# called. Chains detection (GPU) -> CPU pipeline, updating status.json at
# each stage so the web UI's polling loop has something to show. Invoked
# via .spawn() from the /api/calibrate endpoint so that endpoint returns
# immediately instead of blocking for the full run.
# ---------------------------------------------------------------------------
@app.function(image=cpu_image, volumes={VOLUME_PATH: volume}, timeout=14400)  # must outlast run_detection_remote + the CPU chain
def run_full_job_remote(job_id: str, ball_model_name: str, player_model_name: str):
    try:
        _write_status(job_id, stage="detecting", message="Running ball/player detection (GPU)...")
        _run_detection_chunked(job_id, ball_model_name, player_model_name)

        _write_status(job_id, stage="analyzing",
                       message="Running transform/analysis/identity/scoring/report...")
        result = run_cpu_pipeline_remote.remote(job_id)

        volume.reload()
        p = _job_paths(job_id)
        with open(p["report_json_path"]) as f:
            report_json = json.load(f)
        profile = _read_json(p["profile_json_path"])
        if profile is not None:
            profile["insights"] = _read_json(p["insights_json_path"])

        _write_status(job_id, stage="done", message="Complete.", report=report_json,
                       profile=profile, pipeline_result=result)
    except Exception as e:
        _write_status(job_id, stage="error", message=str(e))
        raise


# ---------------------------------------------------------------------------
# "Record match" (2026-10-14): the page films the match itself and uploads
# ~4 s pieces while play goes on (same PUT /api/upload/{job}/part/{i} as file
# uploads), and the court is marked on a still from the camera at the start.
# When the player presses Stop, finish_recording_remote joins the pieces,
# rewrites the browser's recording (fragmented MP4 on iPhone, WebM on
# Android) into a normal video file so OpenCV gets a real frame count for
# chunked detection, and starts processing straight away if the court is
# already marked. Everything after that is the normal pipeline.
# ---------------------------------------------------------------------------
BALL_MODEL_NAME, PLAYER_MODEL_NAME = "tennis_ball_best.pt", "yolov8n.pt"   # fixed server-side


def _part_names(parts_dir: str) -> list:
    return sorted(n for n in os.listdir(parts_dir) if n.endswith(".part")) if os.path.isdir(parts_dir) else []


def _join_parts(parts_dir: str, out_path: str, names=None) -> int:
    """Joins the numbered pieces in parts_dir (or just `names`) into out_path, in order; returns its size."""
    with open(out_path, "wb") as out:
        for n in (_part_names(parts_dir) if names is None else names):
            with open(f"{parts_dir}/{n}", "rb") as f:
                while True:
                    b = f.read(16 * 1024 * 1024)
                    if not b:
                        break
                    out.write(b)
    return os.path.getsize(out_path)


# ---------------------------------------------------------------------------
# Direct-to-storage uploads (2026-10-14): when the Modal secret "r2" holds real
# Cloudflare R2 keys, the browser PUTs each piece straight to R2 with a
# presigned URL (skipping the ~1-1.5 MB/s per-connection cap of the web app),
# and the server pulls the pieces into the job folder when the upload or
# recording finishes. Until then the secret is a placeholder (R2_ENABLED=0)
# and everything goes through the web app as before. A job can mix both: the
# page falls back to the web app if R2 keeps failing, and the pull merges.
# R2 deletes leftover pieces after a day (bucket lifecycle rule).
# ---------------------------------------------------------------------------
R2_SECRET = modal.Secret.from_name("r2")
R2_KEYS = ("R2_ACCOUNT_ID", "R2_ACCESS_KEY_ID", "R2_SECRET_ACCESS_KEY", "R2_BUCKET")
_r2_cache = {}


WEB_ORIGIN = "https://rudragoel10--tennis-perf-app-web-app.modal.run"   # must match the bucket's CORS rule


def _r2_problem(e: Exception) -> str:
    """A storage error in plain words (never includes the keys)."""
    code = getattr(e, "response", {}).get("Error", {}).get("Code", "") if hasattr(e, "response") else ""
    return {
        "NoSuchBucket": "the bucket name in R2_BUCKET doesn't exist in this account",
        "InvalidAccessKeyId": "R2_ACCESS_KEY_ID isn't a key Cloudflare knows",
        "SignatureDoesNotMatch": "R2_SECRET_ACCESS_KEY doesn't match the access key",
        "AccessDenied": "the API token isn't allowed to use this bucket (needs Object Read & Write on it)",
        "403": "the API token isn't allowed to use this bucket (needs Object Read & Write on it)",
        "404": "the bucket name in R2_BUCKET doesn't exist in this account",
    }.get(code) or (f"can't reach the storage address (check R2_ACCOUNT_ID): {type(e).__name__}"
                    if any(w in type(e).__name__ for w in ("Endpoint", "Connect", "SSL")) else f"{type(e).__name__}: {code or e}")


def _r2_values() -> list:
    """The four R2 settings; the account ID is accepted as the bare ID or as the whole
    endpoint address (https://<id>.r2.cloudflarestorage.com), an easy thing to paste."""
    vals = [os.environ.get(k, "").strip() for k in R2_KEYS]
    vals[0] = vals[0].replace("https://", "").replace("http://", "").split(".r2.cloudflarestorage.com")[0].strip("/ ")
    return vals


def _r2():
    """(client, bucket) when R2 is set up AND answers, else None. Checked once per container: if
    Cloudflare refuses, storage is switched off (pages use the app server) and the reason is logged."""
    vals = _r2_values()
    if not all(vals) or os.environ.get("R2_ENABLED", "1").strip() == "0" or "broken" in _r2_cache:
        return None
    if "c" not in _r2_cache:
        import boto3
        from botocore.config import Config
        acct, key, secret, bucket = vals
        client = boto3.client("s3", endpoint_url=f"https://{acct}.r2.cloudflarestorage.com",
                              aws_access_key_id=key, aws_secret_access_key=secret, region_name="auto",
                              config=Config(signature_version="s3v4", retries={"max_attempts": 2},
                                            connect_timeout=5, read_timeout=15))
        try:
            client.head_bucket(Bucket=bucket)
        except Exception as e:
            _r2_cache["broken"] = _r2_problem(e)
            print(f"[r2] storage switched OFF: {_r2_cache['broken']}")
            return None
        _r2_cache["c"] = (client, bucket)
    return _r2_cache["c"]


def _r2_key(job_id: str, index: int) -> str:
    return f"uploads/{job_id}/{index:06d}.part"


def _r2_part_keys(job_id: str) -> dict:
    """{piece index: object key} for this job's pieces in R2."""
    r2 = _r2()
    if not r2:
        return {}
    client, bucket = r2
    out = {}
    try:
        for page in client.get_paginator("list_objects_v2").paginate(Bucket=bucket, Prefix=f"uploads/{job_id}/"):
            for o in page.get("Contents", []):
                name = o["Key"].rsplit("/", 1)[-1]
                if name.endswith(".part"):
                    out[int(name.split(".")[0])] = o["Key"]
    except Exception as e:          # storage trouble must never stop an upload
        print(f"[job {job_id}] couldn't list R2 pieces: {_r2_problem(e)}")
    return out


def _pull_r2_parts(job_id: str, parts_dir: str) -> int:
    """Copies this job's R2 pieces into parts_dir (pieces already there win), then deletes
    them from R2. Returns how many were copied."""
    r2 = _r2()
    if not r2:
        return 0
    client, bucket = r2
    keys = _r2_part_keys(job_id)
    os.makedirs(parts_dir, exist_ok=True)
    copied = 0
    try:
        for i, key in sorted(keys.items()):
            final = f"{parts_dir}/{i:06d}.part"
            if not os.path.exists(final):
                client.download_file(bucket, key, final + ".tmp")
                os.replace(final + ".tmp", final)
                copied += 1
        if copied:
            volume.commit()            # saved on our side before Cloudflare's copy is deleted
        batch = [{"Key": k} for k in keys.values()]
        for n in range(0, len(batch), 1000):
            client.delete_objects(Bucket=bucket, Delete={"Objects": batch[n:n + 1000], "Quiet": True})
    except Exception as e:          # missing pieces are reported by the join ("resume the upload")
        print(f"[job {job_id}] couldn't pull R2 pieces: {_r2_problem(e)}")
    if copied:
        print(f"[job {job_id}] pulled {copied} piece(s) from R2")
    return copied


# Copying pieces in while the upload is still going (2026-10-14): without this the
# server only started copying from R2 after 100%, so players waited at "Almost
# done". The helper polls R2 every few seconds; at the end the web app (or the
# recording finisher) asks it to stop, waits for it briefly, and copies only the
# last few pieces itself. Markers live in the job's input folder on the volume.
PULLER_POLL_S, PULLER_IDLE_S, PULLER_STOP_WAIT_S = 4, 20 * 60, 60


def _puller_marker(job_id: str, name: str) -> str:
    return f"{_job_paths(job_id)['job_dir']}/input/r2_puller_{name}"


@app.function(image=cpu_image, volumes={VOLUME_PATH: volume}, secrets=[R2_SECRET], timeout=3 * 3600)
def r2_puller_remote(job_id: str):
    import time

    d = f"{_job_paths(job_id)['job_dir']}/input/parts"
    with open(_puller_marker(job_id, "started"), "w") as f:
        f.write("1")
    volume.commit()
    started = last_new = time.time()
    total = 0
    while True:
        volume.reload()
        stopping = os.path.exists(_puller_marker(job_id, "stop"))
        if not os.path.isdir(d):
            # joined already, or the job is gone; just after the start it may not be visible yet
            if stopping or os.path.exists(_job_paths(job_id)["video_path"]) or time.time() - started > 120:
                break
            time.sleep(PULLER_POLL_S)
            continue
        n = _pull_r2_parts(job_id, d)
        if n:
            total += n
            last_new = time.time()
        if stopping or time.time() - last_new > PULLER_IDLE_S:
            break
        time.sleep(PULLER_POLL_S)
    with open(_puller_marker(job_id, "done"), "w") as f:
        f.write(str(total))
    volume.commit()
    print(f"[job {job_id}] R2 helper copied {total} piece(s) during the upload")


def _start_r2_puller(job_id: str):
    if _r2():
        try:
            r2_puller_remote.spawn(job_id)
        except Exception as e:            # the end-of-upload copy still works without it
            print(f"[job {job_id}] couldn't start the R2 helper: {e}")


def _stop_r2_puller(job_id: str):
    """Ask the helper to finish its current copy and stop; wait up to a minute for it."""
    import time
    volume.reload()
    if not os.path.exists(_puller_marker(job_id, "started")) or os.path.exists(_puller_marker(job_id, "done")):
        return
    with open(_puller_marker(job_id, "stop"), "w") as f:
        f.write("1")
    volume.commit()
    t0 = time.time()
    while time.time() - t0 < PULLER_STOP_WAIT_S:
        time.sleep(1)
        volume.reload()
        if os.path.exists(_puller_marker(job_id, "done")):
            return
    print(f"[job {job_id}] R2 helper didn't stop in time; copying the rest here")


@app.function(image=cpu_image, secrets=[R2_SECRET], timeout=120)
def check_r2():
    """Checks the Cloudflare R2 setup step by step, in plain words:
    python -m modal run modal_app.py::check_r2"""
    import urllib.request
    vals = dict(zip(R2_KEYS, _r2_values()))
    missing = [k for k, v in vals.items() if not v]
    if os.environ.get("R2_ENABLED", "1").strip() == "0" or missing:
        print(f"OFF: the r2 secret is still the placeholder or is missing {', '.join(missing) or 'nothing'}.")
        return
    def size_check(name, want):
        n = len(vals[name])
        odd = [c for c in vals[name] if not c.isalnum()]
        verdict = "looks right" if n == want and not odd else f"LOOKS WRONG (should be {want} letters/numbers)"
        print(f"{name}: {n} characters{', has odd characters ' + repr(''.join(sorted(set(odd)))) if odd else ''} -> {verdict}")
    size_check("R2_ACCOUNT_ID", 32)
    size_check("R2_ACCESS_KEY_ID", 32)
    size_check("R2_SECRET_ACCESS_KEY", 64)
    print(f"R2_BUCKET: '{vals['R2_BUCKET']}' (must match the bucket name in Cloudflare exactly)")
    r2 = _r2()
    if not r2:
        # Ask again with a call whose error comes back with Cloudflare's own explanation.
        import boto3
        from botocore.config import Config
        acct, key, secret, bucket = _r2_values()
        detail = ""
        try:
            boto3.client("s3", endpoint_url=f"https://{acct}.r2.cloudflarestorage.com", aws_access_key_id=key,
                         aws_secret_access_key=secret, region_name="auto",
                         config=Config(signature_version="s3v4")).list_objects_v2(Bucket=bucket, MaxKeys=1)
        except Exception as e:
            err = getattr(e, "response", {}).get("Error", {}) if hasattr(e, "response") else {}
            detail = f" | Cloudflare says: {err.get('Code', type(e).__name__)}: {err.get('Message', str(e)[:200])}"
        print(f"FAIL 1/3 connect to the bucket: {_r2_cache.get('broken')}{detail}")
        return
    print(f"OK   1/3 connected to bucket '{vals['R2_BUCKET']}'")
    client, bucket = r2
    try:
        client.put_object(Bucket=bucket, Key="uploads/_check/000000.part", Body=b"check")
        client.delete_object(Bucket=bucket, Key="uploads/_check/000000.part")
        print("OK   2/3 the token can write and delete pieces")
    except Exception as e:
        print(f"FAIL 2/3 write a test piece: {_r2_problem(e)}")
        return
    url = client.generate_presigned_url("put_object", Params={"Bucket": bucket, "Key": "uploads/_check/cors.part"}, ExpiresIn=300)
    req = urllib.request.Request(url, method="OPTIONS", headers={
        "Origin": WEB_ORIGIN, "Access-Control-Request-Method": "PUT", "Access-Control-Request-Headers": "content-type"})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            allow = r.headers.get("Access-Control-Allow-Origin", "")
    except Exception as e:
        allow = getattr(e, "headers", {}).get("Access-Control-Allow-Origin", "") if hasattr(e, "headers") else ""
    if allow in (WEB_ORIGIN, "*"):
        print("OK   3/3 the CORS rule lets the app's pages send pieces")
        print("All good: uploads should now go to Cloudflare.")
    else:
        print(f"FAIL 3/3 CORS: the bucket doesn't allow uploads from {WEB_ORIGIN} "
              "(check AllowedOrigins exactly, no slash at the end; AllowedMethods PUT; AllowedHeaders content-type)")


def _remove_parts(parts_dir: str):
    for n in os.listdir(parts_dir):
        os.remove(f"{parts_dir}/{n}")
    os.rmdir(parts_dir)


def _to_video(src: str, dst: str):
    """Rewrites a browser recording into a normal video file without re-encoding (quick):
    MP4 first, Matroska if the codec doesn't fit in MP4 (OpenCV reads either, whatever
    the name). Returns (frames, fps); (0, 0) if it can't be read."""
    import subprocess
    import cv2
    for fmt in (["-movflags", "+faststart", "-f", "mp4"], ["-f", "matroska"]):
        r = subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-fflags", "+genpts",
                            *_src_args(src), "-map", "0:v:0", "-c", "copy", *fmt, dst],
                           capture_output=True, text=True)
        if r.returncode == 0:
            cap = cv2.VideoCapture(dst)
            frames, fps = cap.get(cv2.CAP_PROP_FRAME_COUNT), cap.get(cv2.CAP_PROP_FPS)
            cap.release()
            if frames > 0 and fps:
                return frames, fps
        print(f"ffmpeg {fmt[-1]} for {os.path.basename(src)} failed: {r.stderr.strip()[-500:]}")
    return 0, 0


def _src_args(src: str) -> list:
    """ffmpeg input arguments: a concat list (several recorded parts) or a single file."""
    return ["-f", "concat", "-safe", "0", "-i", src] if src.endswith(".txt") else ["-i", src]


def assemble_recording(parts_dir: str, work_dir: str, out_path: str, pieces: int, segments) -> tuple:
    """Pieces 0..pieces-1 -> one video at out_path. `segments` = the first piece of each
    recorded part (a new part starts after "Continue recording", whose pieces begin with a
    fresh file header), so each part is joined and converted on its own, then the parts
    are put end to end. A part that can't be read (e.g. cut off mid-piece) is skipped if
    another part works. Returns (frames, fps, parts_used)."""
    names = _part_names(parts_dir)
    starts = sorted({int(x) for x in (segments or []) if 0 <= int(x) < pieces} | {0})
    bounds = list(zip(starts, starts[1:] + [pieces]))
    made = []
    for k, (a, b) in enumerate(bounds):
        raw, seg = f"{work_dir}/part{k}.rec", f"{work_dir}/part{k}.video"
        _join_parts(parts_dir, raw, names[a:b])
        frames, fps = _to_video(raw, seg)
        os.remove(raw)
        if frames:
            made.append((seg, frames, fps))
        else:
            print(f"recorded part {k} (pieces {a}-{b - 1}) could not be read; skipped")
    if not made:
        return 0, 0, 0
    if len(made) == 1:
        seg, frames, fps = made[0]
        os.replace(seg, out_path)
    else:
        lst = f"{work_dir}/parts.txt"
        with open(lst, "w") as f:
            f.writelines(f"file '{m[0]}'\n" for m in made)
        frames, fps = _to_video(lst, out_path)
        for m in made:
            os.remove(m[0])
        os.remove(lst)
    return frames, fps, len(made)


def _video_minutes(path: str):
    import cv2
    cap = cv2.VideoCapture(path)
    frames, fps = cap.get(cv2.CAP_PROP_FRAME_COUNT), cap.get(cv2.CAP_PROP_FPS)
    cap.release()
    return frames / fps / 60 if fps and frames > 0 else None


# File uploads, joined in the background (2026-10-14): /complete used to join the
# pieces itself, so players waited ~1 min after 100% before they could mark the
# court. Now /complete only checks every piece is there and starts this; the page
# sends the video's first picture straight away, so the court is found and marked
# while this runs. Processing starts here if the court is already marked;
# otherwise the page re-sends its marking once the stage is "uploaded".
@app.function(image=cpu_image, volumes={VOLUME_PATH: volume}, timeout=3600, secrets=[R2_SECRET])
def finish_upload_remote(job_id: str):
    p = _job_paths(job_id)
    d = f"{p['job_dir']}/input/parts"
    try:
        volume.reload()
        meta = _read_json(f"{p['job_dir']}/input/upload.json", {}) or {}
        expected = -(-meta.get("size", 0) // max(meta.get("chunk_size", 1), 1))
        if _r2():
            _stop_r2_puller(job_id)
            _pull_r2_parts(job_id, d)
        volume.reload()
        parts = _part_names(d)
        if len(parts) != expected:
            raise RuntimeError(f"only {len(parts)} of {expected} pieces arrived; please upload again")
        size = _join_parts(d, p["video_path"])
        if size != meta.get("size"):
            raise RuntimeError(f"the joined video is {size} bytes, expected {meta.get('size')}")
        _remove_parts(d)
        minutes = _video_minutes(p["video_path"])
        print(f"[job {job_id}] upload joined: {size / (1024 * 1024):.0f} MB in {len(parts)} pieces"
              + (f", {minutes:.1f} min" if minutes else ""))
        if minutes and minutes > MAX_VIDEO_MINUTES:
            os.remove(p["video_path"])
            _write_status(job_id, stage="error", message=f"This video is {minutes:.0f} minutes long. "
                          f"The limit is {MAX_VIDEO_MINUTES} minutes; please trim it and upload again.")
            return
        volume.commit()
        volume.reload()
        if os.path.exists(p["matrix_path"]):          # court already marked on the early picture: go
            _write_status(job_id, stage="queued", message="Video ready. Processing queued...")
            run_full_job_remote.spawn(job_id, BALL_MODEL_NAME, PLAYER_MODEL_NAME)
        else:
            _write_status(job_id, stage="uploaded", message="Video uploaded, ready to calibrate.")
    except Exception as e:
        _write_status(job_id, stage="error", message=f"Couldn't put the video together: {e}")
        raise


@app.function(image=cpu_image, volumes={VOLUME_PATH: volume}, timeout=3600, secrets=[R2_SECRET])
def finish_recording_remote(job_id: str, pieces: int, size: int, segments=None):
    import time

    p = _job_paths(job_id)
    d = f"{p['job_dir']}/input/parts"
    try:
        if _r2():
            _stop_r2_puller(job_id)
        # Pieces may still be saving from other web containers: wait up to 2 min for all of them.
        for _ in range(60):
            volume.reload()
            _pull_r2_parts(job_id, d)
            if len(_part_names(d)) >= pieces:
                break
            time.sleep(2)
        have = len(_part_names(d))
        if have != pieces:
            raise RuntimeError(f"only {have} of {pieces} pieces arrived")
        got = sum(os.path.getsize(f"{d}/{n}") for n in _part_names(d))
        if size and got != size:
            raise RuntimeError(f"recording is {got} bytes, expected {size}")
        frames, fps, used = assemble_recording(d, f"{p['job_dir']}/input", p["video_path"], pieces, segments)
        if not frames:
            raise RuntimeError("the recording could not be read as a video")
        _remove_parts(d)
        minutes = frames / fps / 60
        print(f"[job {job_id}] recording ready: {got / (1024 * 1024):.0f} MB, {pieces} pieces, {used} part(s), "
              f"{frames:.0f} frames at {fps:.1f} fps ({minutes:.1f} min)")
        if minutes > MAX_VIDEO_MINUTES + 1:
            os.remove(p["video_path"])
            _write_status(job_id, stage="error", message=f"This recording is {minutes:.0f} minutes long. "
                          f"The limit is {MAX_VIDEO_MINUTES} minutes.")
            return
        volume.commit()
        if os.path.exists(p["matrix_path"]):          # court marked at the start: go
            _write_status(job_id, stage="queued", message="Recording received. Processing queued...")
            run_full_job_remote.spawn(job_id, BALL_MODEL_NAME, PLAYER_MODEL_NAME)
        else:
            _write_status(job_id, stage="uploaded", message="Video uploaded, ready to calibrate.")
    except Exception as e:
        _write_status(job_id, stage="error", message=f"Couldn't prepare the recording: {e}")
        raise


# ---------------------------------------------------------------------------
# Court found automatically (2026-10-14): Code/court_detect.py fits the court
# lines in the marking picture, and the page pre-places the 7 points for the
# player to check (and drag). Below its confidence bar the page falls back to
# tapping. Runs in its own small CPU function (the web container is tiny).
# ---------------------------------------------------------------------------
@app.function(image=cpu_image, volumes={VOLUME_PATH: volume}, cpu=2.0, timeout=120)
def guess_court_remote(job_id: str) -> dict:
    import sys
    import time
    sys.path.insert(0, "/root/Code")
    import cv2
    import calibration
    import court_detect

    volume.reload()
    p = _job_paths(job_id)
    still = f"{p['job_dir']}/input/calib_frame.jpg"
    if os.path.exists(still):
        frame = cv2.imread(still)
    elif os.path.exists(p["video_path"]):
        frame = calibration.extract_calibration_frame(p["video_path"])
    else:
        return {"ok": False, "error": "no picture yet"}
    t0 = time.time()
    res = court_detect.detect_court(frame)
    out = {"ok": bool(res["ok"]), "score": res["score"], "points": res["points"],
           "seconds": round(time.time() - t0, 1)}
    print(f"[job {job_id}] court guess: ok={out['ok']} score={out['score']} in {out['seconds']}s")
    try:
        with open(f"{p['job_dir']}/court_guess.json", "w", encoding="utf-8") as f:
            json.dump(out, f)
        volume.commit()
    except OSError:
        pass
    return out


# ---------------------------------------------------------------------------
# Demo web UI backend -- FastAPI app served as a Modal web endpoint.
# See the module docstring's "DEMO WEB UI" section for the full flow.
# Deploy with `modal deploy modal_app.py`; the printed URL is BACKEND_URL
# for calibration_demo.html.
# ---------------------------------------------------------------------------
@app.function(image=cpu_image, volumes={VOLUME_PATH: volume}, timeout=600, min_containers=1,
              secrets=[modal.Secret.from_name("app-passcode"), R2_SECRET])
@modal.concurrent(max_inputs=20)   # the page sends several upload pieces at once (2026-10-12)
@modal.asgi_app()
def web_app():
    import asyncio
    import hmac
    import shutil
    import tempfile
    import threading
    import time
    import uuid

    import cv2
    from fastapi import BackgroundTasks, FastAPI, File, Form, Request, UploadFile
    from fastapi.middleware.cors import CORSMiddleware
    from fastapi.responses import FileResponse, JSONResponse, Response

    mods = _import_pipeline()
    calibration = mods["calibration"]

    fastapi_app = FastAPI(title="Tennis Perf App -- calibration + processing demo")

    # Passcode on every /api/ route (protects GPU spend and players' data).
    # Pages and icons stay public: they hold no data and ask for the code.
    # No secret value set -> everything is locked (fail closed).
    passcode = os.environ.get("APP_PASSCODE", "").strip().encode()

    # The example report opens without the passcode, so judges and new
    # visitors can see a full report (read only; renaming still needs it).
    public_api = {f"/api/profile/{EXAMPLE_JOB_ID}"}

    @fastapi_app.middleware("http")
    async def require_passcode(request, call_next):
        is_public = request.method == "GET" and request.url.path in public_api
        if request.url.path.startswith("/api/") and request.method != "OPTIONS" and not is_public:
            given = request.headers.get("x-passcode", "").strip().encode()
            if not passcode or not hmac.compare_digest(given, passcode):
                await asyncio.sleep(0.5)              # slows guessing
                return JSONResponse({"error": "passcode required"}, status_code=401)
        return await call_next(request)

    # Added after the passcode check so CORS wraps it (a 401 still carries
    # CORS headers and reaches the page as a 401, not a network error).
    fastapi_app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],  # demo only -- see module docstring's known limitations
        allow_methods=["*"],
        allow_headers=["*"],
    )

    def _commit_volume_background(job_id: str):
        """Runs after the response is already sent (see BackgroundTasks
        below). Not on the request's critical path -- the file is already
        on this container's local disk by the time upload_video returns,
        and with web_app's min_containers=1 the next request (frame fetch,
        calibrate) almost certainly lands on this same warm container and
        can read it straight off disk. commit() just makes the write
        visible to OTHER containers (detection's GPU container, mainly),
        which has minutes to finish while the user clicks through
        calibration -- no reason to make the upload response wait on it."""
        try:
            volume.commit()
            print(f"[job {job_id}] volume commit complete")
        except Exception as e:
            print(f"[job {job_id}] volume commit FAILED: {e}")

    @fastapi_app.post("/api/upload")
    async def upload_video(file: UploadFile = File(...), background_tasks: BackgroundTasks = None):
        job_id = uuid.uuid4().hex[:12]
        p = _job_paths(job_id)
        os.makedirs(os.path.dirname(p["video_path"]), exist_ok=True)

        # Stream to disk in chunks instead of `f.write(await file.read())`
        # (read the WHOLE body into memory, then write) -- avoids an extra,
        # slow, memory-heavy pass after all bytes have already arrived. See
        # the "UPLOAD FIX, 2026-09-24" note in this file's module docstring.
        chunk_size = 8 * 1024 * 1024  # 8 MB
        bytes_written = 0
        log_every = 100 * 1024 * 1024  # log roughly every 100 MB
        with open(p["video_path"], "wb") as f:
            while True:
                chunk = await file.read(chunk_size)
                if not chunk:
                    break
                f.write(chunk)
                bytes_written += len(chunk)
                if bytes_written % log_every < chunk_size:
                    print(f"[job {job_id}] upload progress: "
                          f"{bytes_written / (1024 * 1024):.0f} MB written")
        print(f"[job {job_id}] upload complete: {bytes_written / (1024 * 1024):.0f} MB total")
        too_long = _reject_if_too_long(job_id, p["video_path"])
        if too_long:
            return too_long

        _write_status(job_id, stage="uploaded", message="Video uploaded, ready to calibrate.")

        # commit() runs AFTER this response is sent -- see
        # _commit_volume_background's docstring for why this is safe.
        background_tasks.add_task(_commit_volume_background, job_id)

        # Point labels + human instructions, sourced from calibration.py
        # directly so the UI can never drift out of sync with what
        # build_perspective_transform() actually expects.
        return JSONResponse({
            "job_id": job_id,
            "point_labels": calibration.EXTENDED_POINT_LABELS,
            "instructions": calibration.CLICK_INSTRUCTIONS,
        })

    # ── Chunked upload (Week 2 #10, 2026-09-30) ──────────────────────────
    # One long POST of a 1+ GB video fails on some network paths (VPN /
    # proxies closing long connections). Instead the browser sends ~16 MB
    # pieces, retrying each; every piece is its own file on the volume (no
    # cross-container write conflicts), so a dropped connection resumes from
    # the pieces already stored. /complete joins them into input/video.mp4.
    def _reject_if_too_long(job_id: str, video_path: str):
        """Videos over MAX_VIDEO_MINUTES are deleted and refused (GPU spend
        cap). Returns the error response, or None if the video is fine."""
        cap = cv2.VideoCapture(video_path)
        frames, fps = cap.get(cv2.CAP_PROP_FRAME_COUNT), cap.get(cv2.CAP_PROP_FPS)
        cap.release()
        if not fps or frames <= 0:
            return None                        # unreadable length: later stages report problems
        minutes = frames / fps / 60
        if minutes <= MAX_VIDEO_MINUTES:
            return None
        os.remove(video_path)
        msg = (f"This video is {minutes:.0f} minutes long. The limit is {MAX_VIDEO_MINUTES} minutes; "
               f"please trim it and upload again.")
        _write_status(job_id, stage="error", message=msg)
        print(f"[job {job_id}] rejected: {minutes:.1f} min > {MAX_VIDEO_MINUTES}")
        return JSONResponse({"error": msg}, status_code=413)

    def _parts_dir(job_id: str) -> str:
        return f"{_job_paths(job_id)['job_dir']}/input/parts"

    @fastapi_app.post("/api/upload/init")
    def upload_init(size: int = Form(...), chunk_size: int = Form(...)):
        job_id = uuid.uuid4().hex[:12]
        os.makedirs(_parts_dir(job_id), exist_ok=True)
        with open(f"{_job_paths(job_id)['job_dir']}/input/upload.json", "w") as f:
            json.dump({"size": size, "chunk_size": chunk_size}, f)
        volume.commit()
        _start_r2_puller(job_id)
        return JSONResponse({"job_id": job_id, "r2": bool(_r2())})

    @fastapi_app.get("/api/upload/{job_id}/parts")
    def upload_parts(job_id: str):
        """Which pieces are already stored -- the browser resumes from here."""
        volume.reload()
        d = _parts_dir(job_id)
        have = {int(n.split(".")[0]) for n in _part_names(d)} | set(_r2_part_keys(job_id))
        return JSONResponse({"job_id": job_id, "parts": sorted(have)})

    @fastapi_app.get("/api/upload/{job_id}/r2-urls")
    def r2_urls(job_id: str, start: int = 0, count: int = 50):
        """Presigned URLs for pieces start..start+count-1: the browser PUTs them straight to R2."""
        r2 = _r2()
        if not r2:
            return JSONResponse({"r2": False, "error": "direct-to-storage is off"}, status_code=404)
        if not os.path.isdir(_parts_dir(job_id)):
            volume.reload()
        if not os.path.isdir(_parts_dir(job_id)):
            return JSONResponse({"error": f"Unknown upload {job_id}"}, status_code=404)
        client, bucket = r2
        urls = {i: client.generate_presigned_url("put_object", Params={"Bucket": bucket, "Key": _r2_key(job_id, i)},
                                                 ExpiresIn=6 * 3600)
                for i in range(max(start, 0), max(start, 0) + max(1, min(count, 200)))}
        return JSONResponse({"r2": True, "urls": urls})

    # Upload speed fix (2026-10-12): uploads ran at ~0.3 MB/s on a fast
    # connection. Each piece used to be parsed as a form and then wait for
    # a full volume.commit() before the browser could send the next one.
    # Now the page sends the raw bytes, several pieces at once, and commits
    # run in one background thread (several pieces per commit). /complete
    # waits for that thread before joining the pieces.
    commit_lock = threading.Lock()
    commit_state = {"running": False, "again": False}

    def _commit_soon():
        with commit_lock:
            if commit_state["running"]:
                commit_state["again"] = True
                return
            commit_state["running"] = True

        def run():
            while True:
                t0 = time.time()
                try:
                    volume.commit()
                    print(f"[upload] volume commit took {time.time() - t0:.1f}s")
                except Exception as e:
                    print(f"[upload] volume commit FAILED: {e}")
                with commit_lock:
                    if not commit_state["again"]:
                        commit_state["running"] = False
                        return
                    commit_state["again"] = False

        threading.Thread(target=run, daemon=True).start()

    async def _wait_for_commits(limit_s: float = 300):
        start = time.time()
        while commit_state["running"] and time.time() - start < limit_s:
            await asyncio.sleep(0.2)

    @fastapi_app.put("/api/upload/{job_id}/part/{index}")
    async def upload_part(job_id: str, index: int, request: Request):
        d = _parts_dir(job_id)
        if not os.path.isdir(d):
            volume.reload()
        if not os.path.isdir(d):
            return JSONResponse({"error": f"Unknown upload {job_id}"}, status_code=404)
        t0 = time.time()
        # Receive into local disk first, so no volume file sits open for the
        # whole transfer; then copy in and rename (a half-written piece
        # never counts as stored).
        with tempfile.NamedTemporaryFile(delete=False) as f:
            local = f.name
            async for chunk in request.stream():
                f.write(chunk)
        received_s = time.time() - t0
        tmp, final = f"{d}/{index:06d}.tmp", f"{d}/{index:06d}.part"
        await asyncio.to_thread(shutil.copyfile, local, tmp)
        os.remove(local)
        os.replace(tmp, final)
        size = os.path.getsize(final)
        print(f"[job {job_id}] piece {index}: {size / (1024 * 1024):.0f} MB received in {received_s:.1f}s, "
              f"stored in {time.time() - t0 - received_s:.1f}s")
        _commit_soon()
        return JSONResponse({"index": index, "bytes": size})

    @fastapi_app.post("/api/upload/{job_id}/complete")
    async def upload_complete(job_id: str):
        await _wait_for_commits()
        return await asyncio.to_thread(_check_and_finish_upload, job_id)

    def _check_and_finish_upload(job_id: str):
        """Every piece is on our side or in R2? Then join in the background (finish_upload_remote)."""
        p = _job_paths(job_id)
        d = _parts_dir(job_id)
        volume.reload()
        meta = _read_json(f"{p['job_dir']}/input/upload.json", {}) or {}
        expected = -(-meta.get("size", 0) // max(meta.get("chunk_size", 1), 1))
        have = {int(n.split(".")[0]) for n in _part_names(d)} | set(_r2_part_keys(job_id))
        if len(have) != expected:
            return JSONResponse({"error": f"Have {len(have)} of {expected} pieces -- resume the upload."},
                                status_code=409)
        _write_status(job_id, stage="preparing", message="Putting the video together...")
        finish_upload_remote.spawn(job_id)
        return JSONResponse({
            "job_id": job_id,
            "preparing": True,
            "point_labels": calibration.EXTENDED_POINT_LABELS,
            "instructions": calibration.CLICK_INSTRUCTIONS,
        })

    # ── Record match (2026-10-14): see finish_recording_remote ──────────────
    @fastapi_app.post("/api/record/init")
    def record_init(mime: str = Form("")):
        job_id = uuid.uuid4().hex[:12]
        os.makedirs(_parts_dir(job_id), exist_ok=True)
        with open(f"{_job_paths(job_id)['job_dir']}/input/upload.json", "w") as f:
            json.dump({"mode": "record", "mime": mime[:80]}, f)
        _write_status(job_id, stage="recording", message="Recording...")   # commits
        _start_r2_puller(job_id)
        return JSONResponse({"job_id": job_id, "r2": bool(_r2())})

    def _calib_frame_path(job_id: str) -> str:
        return f"{_job_paths(job_id)['job_dir']}/input/calib_frame.jpg"

    @fastapi_app.post("/api/record/{job_id}/frame")
    @fastapi_app.post("/api/upload/{job_id}/frame")
    async def record_frame(job_id: str, file: UploadFile = File(...)):
        """The marking picture sent by the page before the video is ready: a camera still at the
        start of a recording, or the first picture of an uploaded video (taken on the device)."""
        if not os.path.isdir(_parts_dir(job_id)):
            volume.reload()
        if not os.path.isdir(_parts_dir(job_id)):
            return JSONResponse({"error": f"Unknown recording {job_id}"}, status_code=404)
        data = await file.read()
        if len(data) > 20 * 1024 * 1024:
            return JSONResponse({"error": "Picture too large"}, status_code=413)
        with open(_calib_frame_path(job_id), "wb") as f:
            f.write(data)
        volume.commit()
        return JSONResponse({
            "job_id": job_id,
            "point_labels": calibration.EXTENDED_POINT_LABELS,
            "instructions": calibration.CLICK_INSTRUCTIONS,
        })

    @fastapi_app.post("/api/record/{job_id}/finish")
    async def record_finish(job_id: str, pieces: int = Form(...), size: int = Form(...), segments: str = Form("[0]")):
        """Stop pressed and every piece sent: join, convert and (if the court is marked) start."""
        await _wait_for_commits()
        if not os.path.isdir(_parts_dir(job_id)):
            volume.reload()
        if not os.path.isdir(_parts_dir(job_id)):
            return JSONResponse({"error": f"Unknown recording {job_id}"}, status_code=404)
        _write_status(job_id, stage="preparing", message="Putting the recording together...")
        try:
            starts = [int(x) for x in json.loads(segments)][:500]
        except (ValueError, TypeError):
            starts = [0]
        finish_recording_remote.spawn(job_id, pieces, size, starts)
        return JSONResponse({"job_id": job_id, "status": "preparing"})

    @fastapi_app.get("/api/court-guess/{job_id}")
    async def court_guess(job_id: str):
        """The 7 points found automatically in the marking picture, if the fit is confident."""
        try:
            return JSONResponse(await guess_court_remote.remote.aio(job_id))
        except Exception as e:
            print(f"[job {job_id}] court guess failed: {e}")
            return JSONResponse({"ok": False, "error": "court finding failed"})

    # ── Delete a report (2026-10-14): the player removes a match for good ────
    # Removes the job folder (report, stats, the uploaded video and every working
    # file) and any pieces still in R2. Not the example, and not while the match is
    # still being analysed (the running job would fail half-way).
    @fastapi_app.delete("/api/job/{job_id}")
    def delete_job(job_id: str):
        import re
        if not re.fullmatch(r"[0-9a-f]{12}", job_id):
            return JSONResponse({"error": "Not a job code"}, status_code=400)
        if job_id == EXAMPLE_JOB_ID:
            return JSONResponse({"error": "The example report can't be deleted."}, status_code=403)
        volume.reload()
        d = _job_paths(job_id)["job_dir"]
        if not os.path.isdir(d):
            return JSONResponse({"deleted": False, "error": "Not found"}, status_code=404)
        stage = (_read_json(f"{d}/status.json", {}) or {}).get("stage")
        if stage in ("calibrating", "queued", "detecting", "analyzing", "preparing"):
            return JSONResponse({"error": "This match is still being analysed. You can delete it once its report is ready."},
                                status_code=409)
        shutil.rmtree(d, ignore_errors=True)
        volume.commit()
        r2 = _r2()
        if r2:
            try:
                keys = list(_r2_part_keys(job_id).values())
                for n in range(0, len(keys), 1000):
                    r2[0].delete_objects(Bucket=r2[1], Delete={"Objects": [{"Key": k} for k in keys[n:n + 1000]], "Quiet": True})
            except Exception as e:
                print(f"[job {job_id}] couldn't clear R2 pieces: {_r2_problem(e)}")
        print(f"[job {job_id}] deleted by the player (stage was {stage})")
        return JSONResponse({"deleted": True})

    @fastapi_app.get("/api/point-labels")
    def point_labels():
        """Lets the frontend fetch the calibration point schema without an
        upload -- used by the 'resume with existing job ID' path, where
        there's no fresh /api/upload response to pull it from."""
        return JSONResponse({
            "point_labels": calibration.EXTENDED_POINT_LABELS,
            "instructions": calibration.CLICK_INSTRUCTIONS,
        })

    @fastapi_app.get("/api/frame/{job_id}")
    def get_calibration_frame(job_id: str):
        volume.reload()
        p = _job_paths(job_id)
        if os.path.exists(_calib_frame_path(job_id)):        # recorded in the app: the still from the start
            return FileResponse(_calib_frame_path(job_id), media_type="image/jpeg")
        frame = calibration.extract_calibration_frame(p["video_path"])
        ok, buf = cv2.imencode(".jpg", frame)
        if not ok:
            return JSONResponse({"error": "Could not encode frame"}, status_code=500)
        return Response(content=buf.tobytes(), media_type="image/jpeg")

    @fastapi_app.post("/api/calibrate")
    async def calibrate(
        job_id: str = Form(...),
        points_json: str = Form(...),  # {"label": [x, y], ...}
        # player_1 = the player at the NEAR end (closest to the camera) when
        # the video starts; player_2 = far end (scoring's end-swap logic
        # keeps them straight after changeovers)
        player1_name: str = Form(""),
        player2_name: str = Form(""),
    ):
        ball_model_name, player_model_name = BALL_MODEL_NAME, PLAYER_MODEL_NAME
        volume.reload()
        p = _job_paths(job_id)
        os.makedirs(p["job_dir"], exist_ok=True)
        with open(p["names_json_path"], "w", encoding="utf-8") as f:
            json.dump({k: v.strip()[:40] for k, v in
                       (("player_1", player1_name), ("player_2", player2_name)) if v.strip()}, f)
        points = json.loads(points_json)
        clicked_points_px = {label: tuple(xy) for label, xy in points.items()}

        missing = [l for l in calibration.EXTENDED_POINT_LABELS if l not in clicked_points_px]
        if missing:
            return JSONResponse(
                {"error": f"Missing points: {missing}"}, status_code=400
            )

        for path in (
            f"{MODELS_DIR}/{ball_model_name}",
            f"{MODELS_DIR}/{player_model_name}",
        ):
            if not os.path.exists(path):
                return JSONResponse(
                    {"error": f"{path} not found on the volume -- upload your "
                               f"model first (see module docstring for the CLI "
                               f"command)."},
                    status_code=400,
                )

        # Still recording (marked on the camera still, no video yet): the matrix only
        # needs the 7 points; the still stands in for the video's first frame.
        early = not os.path.exists(p["video_path"]) and os.path.exists(_calib_frame_path(job_id))
        recording = early and (_read_json(f"{p['job_dir']}/input/upload.json", {}) or {}).get("mode") == "record"
        if not early:
            _write_status(job_id, stage="calibrating", message="Building perspective transform...")
        calibration.build_perspective_transform(
            clicked_points_px=clicked_points_px,
            video_path=_calib_frame_path(job_id) if early else p["video_path"],
            matrix_path=p["matrix_path"],
            birdeye_check_path=p["birdeye_check_path"],
            display=False,
        )
        volume.commit()
        if recording:
            _write_status(job_id, stage="recording", message="Court marked. Recording...")
            return JSONResponse({"job_id": job_id, "status": "recording"})
        if early:     # upload still being joined: finish_upload_remote starts the job when it's ready
            return JSONResponse({"job_id": job_id, "status": "waiting_for_video"})

        _write_status(job_id, stage="queued", message="Calibrated. Processing queued...")
        run_full_job_remote.spawn(job_id, ball_model_name, player_model_name)

        return JSONResponse({"job_id": job_id, "status": "processing_started"})

    @fastapi_app.get("/api/status/{job_id}")
    def status(job_id: str):
        st = _read_status(job_id)
        # Re-run jobs keep their first run's status note; the report file is
        # the truth for "is there a report to open".
        st["report_ready"] = os.path.exists(_job_paths(job_id)["profile_json_path"])
        return JSONResponse(st)

    from fastapi.responses import FileResponse

    @fastapi_app.get("/")
    @fastapi_app.get("/calibration_demo.html")
    def home_page():
        return FileResponse("/root/web/calibration_demo.html", media_type="text/html",
                            headers={"Cache-Control": "no-store"})

    @fastapi_app.get("/report")
    @fastapi_app.get("/report.html")
    def report_page():
        return FileResponse("/root/web/report.html", media_type="text/html",
                            headers={"Cache-Control": "no-store"})

    @fastapi_app.get("/camera-test")
    def camera_test_page():
        """What this phone can record in the browser (resolution, format, MB per minute)."""
        return FileResponse("/root/web/camera_test.html", media_type="text/html",
                            headers={"Cache-Control": "no-store"})

    _assets = {"passcode.js": "text/javascript", "site.js": "text/javascript", "site.css": "text/css",
               "recorder.js": "text/javascript", "record_match.js": "text/javascript",
               "manifest.webmanifest": "application/manifest+json",
               "icon.svg": "image/svg+xml", "icon-192.png": "image/png", "icon-512.png": "image/png",
               **{f"{n}-{w}.webp": "image/webp" for n in ("hero-court", "band-phone", "band-ball") for w in (800, 1600)}}

    @fastapi_app.get("/{name}")
    def web_asset(name: str):
        """passcode.js, the install manifest, app icons and page photos, at the site root."""
        if name not in _assets:
            return JSONResponse({"error": "not found"}, status_code=404)
        return FileResponse(f"/root/web/assets/{name}", media_type=_assets[name],
                            headers={"Cache-Control": "no-cache"})

    @fastapi_app.get("/api/debug/{job_id}/{name}")
    def debug_file(job_id: str, name: str):
        """Pipeline intermediates for offline checking (ball/player positions
        and events only -- no video). Needs the passcode like every /api/ route:
        curl -H "X-Passcode: <code>" <url>/api/debug/<job>/<name>"""
        allowed = {"rally_events_resolved.csv": "resolved_events_csv_path",
                   "raw_detection.csv": "raw_csv_path", "match_data.csv": "match_csv_path"}
        if name not in allowed:
            return JSONResponse({"error": "not available"}, status_code=404)
        volume.reload()
        path = _job_paths(job_id)[allowed[name]]
        if not os.path.exists(path):
            return JSONResponse({"error": "not found"}, status_code=404)
        return FileResponse(path, media_type="text/csv")

    @fastapi_app.get("/api/profile/{job_id}")
    def get_profile(job_id: str):
        """The report page's data: per-player profile (+ cached insights)."""
        volume.reload()
        p = _job_paths(job_id)
        profile = _read_json(p["profile_json_path"])
        if profile is None:
            return JSONResponse({"error": f"No profile for job {job_id} yet"}, status_code=404)
        insights = _read_json(p["insights_json_path"])
        if insights:
            profile["insights"] = insights
        return JSONResponse(profile)

    @fastapi_app.post("/api/names/{job_id}")
    def set_names(job_id: str, player1_name: str = Form(""), player2_name: str = Form("")):
        """Rename players after processing (fix a typo without a re-run)."""
        volume.reload()
        p = _job_paths(job_id)
        names = {k: v.strip()[:40] for k, v in
                 (("player_1", player1_name), ("player_2", player2_name)) if v.strip()}
        with open(p["names_json_path"], "w", encoding="utf-8") as f:
            json.dump(names, f)
        profile = _read_json(p["profile_json_path"])
        if profile:
            for pid, pl in profile["players"].items():
                pl["name"] = names.get(pid) or ("Player 1" if pid == "player_1" else "Player 2")
            with open(p["profile_json_path"], "w", encoding="utf-8") as f:
                json.dump(profile, f, indent=2, default=str)
        volume.commit()
        return JSONResponse({"job_id": job_id, "names": names})

    return fastapi_app


# ---------------------------------------------------------------------------
# Local entrypoint: alternative to the web UI -- uploads a video +
# (optionally) a matrix from the CLI, then runs the full job directly.
# Useful for testing the pipeline without the browser flow. If matrix_path
# is omitted, call run_calibration_remote separately first (or reuse a
# prior job's matrix by passing it here).
# ---------------------------------------------------------------------------
@app.local_entrypoint()
def run_job(
    job_id: str,
    video_path: str,
    ball_model_name: str = "tennis_ball_best.pt",
    player_model_name: str = "yolov8n.pt",
    matrix_path: str = None,
):
    p = _job_paths(job_id)

    print(f"Uploading video to jobs/{job_id}/input/video.mp4 ...")
    with volume.batch_upload() as batch:
        batch.put_file(video_path, p["video_path"])
        if matrix_path:
            batch.put_file(matrix_path, p["matrix_path"])

    if not matrix_path:
        print(
            "No matrix_path given -- assuming perspective_matrix.npy already "
            f"exists at jobs/{job_id}/perspective_matrix.npy from a prior "
            "run_calibration_remote() call. If not, this job will fail at "
            "the transform stage."
        )

    print("Running detection (GPU, chunked in parallel)...")
    det_result = run_detection_chunked_remote.remote(job_id, ball_model_name, player_model_name)
    print("Detection done:", det_result)

    print("Running CPU stages (transform -> analysis -> shot_type -> "
          "identity -> scoring -> report)...")
    result = run_cpu_pipeline_remote.remote(job_id)
    print("\n=== Job complete ===")
    print(json.dumps(result, indent=2, default=str))


# ---------------------------------------------------------------------------
# Re-run just the CPU stages for a job whose raw_detection.csv is already on
# the volume (detection already succeeded) -- skips the ~15-min GPU
# detection pass entirely. Useful after fixing a bug in transform.py/
# analysis.py/etc. without needing to redo detection. Usage:
#   modal run modal_app.py::rerun_cpu_stages --job-id <id>
# ---------------------------------------------------------------------------
@app.local_entrypoint()
def rerun_job(job_id: str, ball_model_name: str = "tennis_ball_best.pt",
              player_model_name: str = "yolov8n.pt"):
    """Full rerun (chunked GPU detection + CPU chain) of a job whose video and
    perspective_matrix.npy are already on the volume -- no re-upload.
      modal run modal_app.py::rerun_job --job-id 76a383379d90"""
    det = run_detection_chunked_remote.remote(job_id, ball_model_name, player_model_name)
    print("Detection:", json.dumps(det, indent=2, default=str))
    result = run_cpu_pipeline_remote.remote(job_id)
    print("\n=== Job complete ===")
    print(json.dumps(result, indent=2, default=str))


@app.local_entrypoint()
def rerun_cpu_stages(job_id: str):
    result = run_cpu_pipeline_remote.remote(job_id)
    print("\n=== CPU stages complete ===")
    print(json.dumps(result, indent=2, default=str))


# ---------------------------------------------------------------------------
# Model-identity check, added this session -- confirms which local weights
# file is ACTUALLY deployed on the volume as tennis_ball_best.pt, instead
# of inferring it from filenames/paths/dates (which turned out to be
# ambiguous -- see TennisPerfApp.md, still-open since 2026-09-25: verify
# tennis_ball_best.pt on the volume is really the model that achieved the
# 93%+ 2160p benchmark, not a stale/wrong upload). A SHA256 hash is
# decisive where "same folder name"/"same modified date" is not.
#
# Usage:
#   modal run modal_app.py::hash_model --model-name tennis_ball_best.pt
# Then compare the printed hash against a LOCAL hash of the candidate
# weights file (e.g. tennis_ball_v1-5/weights/best.pt) -- see the
# PowerShell command in this function's own printed output.
# ---------------------------------------------------------------------------
@app.function(image=cpu_image, volumes={VOLUME_PATH: volume})
def hash_volume_file_remote(model_name: str) -> dict:
    import hashlib

    path = f"{MODELS_DIR}/{model_name}"
    if not os.path.exists(path):
        raise FileNotFoundError(f"{path} not found on the volume.")

    h = hashlib.sha256()
    size = 0
    with open(path, "rb") as f:
        while True:
            chunk = f.read(8 * 1024 * 1024)
            if not chunk:
                break
            h.update(chunk)
            size += len(chunk)

    return {"path": path, "sha256": h.hexdigest(), "size_bytes": size}


@app.local_entrypoint()
def hash_model(model_name: str = "tennis_ball_best.pt"):
    result = hash_volume_file_remote.remote(model_name)
    print(f"\nVolume file: {result['path']}")
    print(f"Size:   {result['size_bytes']:,} bytes")
    print(f"SHA256: {result['sha256']}")
    print(
        "\nCompare against a local candidate with:\n"
        '  Get-FileHash "C:\\Users\\rudra\\Downloads\\Projects\\Tennis '
        'Performance App\\Training\\runs\\detect\\tennis_ball_v1-5\\'
        'weights\\best.pt" -Algorithm SHA256\n'
        "A match on the hash (not just size) confirms it's byte-identical, "
        "not just similarly-sized."
    )


# ---------------------------------------------------------------------------
# Smoke tests (unchanged from the 2026-09-22 validated build)
# ---------------------------------------------------------------------------
@app.function(image=cpu_image)
def smoke_test_cpu():
    import numpy, pandas, cv2, scipy, sklearn, matplotlib
    return {
        "numpy": numpy.__version__,
        "pandas": pandas.__version__,
        "opencv": cv2.__version__,
        "scipy": scipy.__version__,
        "sklearn": sklearn.__version__,
        "matplotlib": matplotlib.__version__,
    }


@app.function(image=gpu_image, gpu="T4")
def smoke_test_gpu():
    import torch, cv2, supervision, ultralytics
    return {
        "torch": torch.__version__,
        "cuda_available": torch.cuda.is_available(),
        "opencv": cv2.__version__,
        "supervision": supervision.__version__,
        "ultralytics": ultralytics.__version__,
    }


@app.function(image=cpu_image, volumes={VOLUME_PATH: volume}, timeout=1800)
def relink_job_remote(job_id: str) -> dict:
    """Re-run ball linking from the stored per-chunk detections (no GPU),
    e.g. after a ball_linker change (2026-10-07)."""
    import cv2
    volume.reload()
    p = _job_paths(job_id)
    chunk_dir = f"{p['job_dir']}/chunks"
    n_chunks = len([n for n in os.listdir(chunk_dir) if n.startswith("ball_") and n.endswith(".csv")])
    cap = cv2.VideoCapture(p["video_path"])
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    cap.release()
    return merge_detection_remote.local(job_id, n_chunks, total)


@app.local_entrypoint()
def relink_job(job_id: str):
    """Redo ball linking + the whole analysis for a job, without the GPU:
    python -m modal run modal_app.py::relink_job --job-id <id>"""
    print(relink_job_remote.remote(job_id))
    rerun_cpu_stages(job_id)
