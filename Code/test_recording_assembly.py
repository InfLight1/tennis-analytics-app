"""
test_recording_assembly.py

Smoke test for "Record match": the page uploads a recording in small byte
pieces (cut wherever the browser's recorder hands them over), sometimes in
several parts (after "Continue recording"), and modal_app.assemble_recording
must turn them back into one video OpenCV can read with the right frame count.

Makes fragmented-MP4 and WebM test recordings with ffmpeg (the formats iPhone
Safari and Android Chrome record), cuts them into uneven pieces, and checks:
1. One part, fragmented MP4 -> readable video, all frames kept.
2. Two parts (MP4) -> both joined end to end.
3. One part, WebM -> readable video.
4. A broken second part is skipped; the good part still comes through.

Needs ffmpeg on the PATH (skips otherwise). Run directly:
    python Code/test_recording_assembly.py
"""

import os
import shutil
import subprocess
import sys
import tempfile

import cv2

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import modal_app  # noqa: E402

FPS, SECONDS = 30, 4


def make_recording(path, fmt):
    args = ["-f", "lavfi", "-i", f"testsrc=size=640x360:rate={FPS}", "-t", str(SECONDS)]
    if fmt == "mp4":
        out = ["-c:v", "libx264", "-pix_fmt", "yuv420p", "-movflags", "frag_keyframe+empty_moov+default_base_moof", "-f", "mp4"]
    else:
        out = ["-c:v", "libvpx-vp9", "-deadline", "realtime", "-f", "webm"]
    subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", *args, *out, path], check=True)


def cut_into_pieces(path, parts_dir, start_index, sizes=(70_000, 33_000, 120_000)):
    data = open(path, "rb").read()
    i, pos = start_index, 0
    while pos < len(data):
        n = sizes[(i - start_index) % len(sizes)]
        with open(os.path.join(parts_dir, f"{i:06d}.part"), "wb") as f:
            f.write(data[pos:pos + n])
        pos += n
        i += 1
    return i


def frames_of(path):
    cap = cv2.VideoCapture(path)
    n = cap.get(cv2.CAP_PROP_FRAME_COUNT)
    cap.release()
    return n


def run_case(name, recordings, broken_last=False):
    work = tempfile.mkdtemp()
    try:
        parts = os.path.join(work, "parts")
        os.makedirs(parts)
        starts, i = [], 0
        for k, fmt in enumerate(recordings):
            src = os.path.join(work, f"src{k}.{fmt}")
            make_recording(src, fmt)
            if broken_last and k == len(recordings) - 1:
                with open(src, "wb") as f:
                    f.write(os.urandom(50_000))       # garbage part
            starts.append(i)
            i = cut_into_pieces(src, parts, i)
        out = os.path.join(work, "video.mp4")
        frames, fps, used = modal_app.assemble_recording(parts, work, out, i, starts)
        good = len(recordings) - (1 if broken_last else 0)
        ok = frames == good * FPS * SECONDS and used == good and abs(frames_of(out) - frames) < 1
        print(f"{'PASS' if ok else 'FAIL'}  {name}: {frames:.0f} frames at {fps:.0f} fps from {used} part(s)")
        return ok
    finally:
        shutil.rmtree(work, ignore_errors=True)


if __name__ == "__main__":
    if not shutil.which("ffmpeg"):
        print("SKIP: ffmpeg not found")
        sys.exit(0)
    results = [
        run_case("one part, fragmented MP4", ["mp4"]),
        run_case("two parts, MP4", ["mp4", "mp4"]),
        run_case("one part, WebM", ["webm"]),
        run_case("broken second part skipped", ["mp4", "mp4"], broken_last=True),
    ]
    sys.exit(0 if all(results) else 1)
