"""
label_ground_truth.py

Frame-stepping viewer for building a manual ground-truth event set against
real footage. Uses the same cv2.VideoCapture frame-counting detection.py
does, so the frame number you log here lines up exactly with rally_events.csv
-- no timestamp-to-frame conversion, no rounding risk.

Controls (window must be focused):
    d / RIGHT   -> next frame
    a / LEFT    -> previous frame
    D           -> jump forward JUMP_FRAMES
    A           -> jump backward JUMP_FRAMES
    b           -> log a BOUNCE at the current frame
    h           -> log a HIT at the current frame
    n           -> log a NET (ball contacts net) at the current frame
    o           -> log an OTHER/uncertain event at the current frame
    u           -> undo the last logged event
    q / ESC     -> quit and save

Every keypress re-renders the current frame with the frame number,
timestamp, and total frame count burned into the top-left corner, plus a
running list of the last few logged events at the bottom so you can see
what you've already marked without checking the CSV.

Output: one row per logged event -- frame, timestamp_sec, event_type,
written to OUTPUT_CSV as you go (saved on every log + on quit, so nothing
is lost if you close the window unexpectedly).

Run directly (editable-variable style, same convention as everything else
in this project -- no CLI args):
    python label_ground_truth.py
"""

import csv
from pathlib import Path

import cv2

# ── Editable top-of-file variables ─────────────────────────────────────────
VIDEO_PATH = r"C:\Users\rudra\Downloads\Projects\Tennis Performance App\Videos\tennis1_clip2.mp4"   # the ~15s test clip
OUTPUT_CSV = "ground_truth_events.csv"
JUMP_FRAMES = 10          # how many frames the capital-letter keys skip
DISPLAY_MAX_WIDTH = 1280  # downscale only for display; logged frame numbers are unaffected

EVENT_KEYS = {
    ord("b"): "bounce",
    ord("h"): "hit",
    ord("n"): "net",
    ord("o"): "other",
}


def _draw_overlay(frame, frame_num, total_frames, fps, recent_events):
    h, w = frame.shape[:2]
    timestamp = frame_num / fps if fps else 0.0

    overlay_lines = [
        f"Frame {frame_num} / {total_frames - 1}   t={timestamp:.3f}s   fps={fps:.1f}",
        "d/RIGHT=next  a/LEFT=prev  D/A=jump10  b=bounce  h=hit  n=net  o=other  u=undo  q=quit",
    ]
    y = 30
    for line in overlay_lines:
        cv2.putText(frame, line, (10, y), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 0), 4, cv2.LINE_AA)
        cv2.putText(frame, line, (10, y), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 1, cv2.LINE_AA)
        y += 26

    if recent_events:
        y = h - 10 - 20 * len(recent_events)
        for ev in recent_events:
            text = f"logged: frame {ev['frame']}  ({ev['event_type']})"
            cv2.putText(frame, text, (10, y), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 0, 0), 3, cv2.LINE_AA)
            cv2.putText(frame, text, (10, y), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 220, 255), 1, cv2.LINE_AA)
            y += 20

    return frame


def _write_events(events, path):
    with open(path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["frame", "timestamp_sec", "event_type"])
        writer.writeheader()
        for e in events:
            writer.writerow(e)


def main():
    cap = cv2.VideoCapture(str(VIDEO_PATH))
    if not cap.isOpened():
        raise RuntimeError(f"Could not open video: {VIDEO_PATH}")

    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    fps = cap.get(cv2.CAP_PROP_FPS)
    print(f"Opened {VIDEO_PATH}: {total_frames} frames @ {fps:.2f} fps "
          f"(~{total_frames / fps:.1f}s)" if fps else f"Opened {VIDEO_PATH}: {total_frames} frames")

    events = []
    frame_num = 0
    window = "Ground Truth Labeler"
    cv2.namedWindow(window, cv2.WINDOW_NORMAL)

    def read_frame(n):
        n = max(0, min(n, total_frames - 1))
        cap.set(cv2.CAP_PROP_POS_FRAMES, n)
        ok, frame = cap.read()
        return n, frame if ok else None

    frame_num, frame = read_frame(frame_num)

    while True:
        if frame is None:
            print(f"WARNING: could not read frame {frame_num}, stopping.")
            break

        display = frame.copy()
        h, w = display.shape[:2]
        if w > DISPLAY_MAX_WIDTH:
            scale = DISPLAY_MAX_WIDTH / w
            display = cv2.resize(display, (int(w * scale), int(h * scale)))

        display = _draw_overlay(display, frame_num, total_frames, fps, events[-5:])
        cv2.imshow(window, display)

        key = cv2.waitKey(0) & 0xFF

        if key in (ord("q"), 27):  # q or ESC
            break
        elif key in (ord("d"), 83):  # d or RIGHT arrow (platform-dependent code)
            frame_num, frame = read_frame(frame_num + 1)
        elif key in (ord("a"), 81):  # a or LEFT arrow
            frame_num, frame = read_frame(frame_num - 1)
        elif key == ord("D"):
            frame_num, frame = read_frame(frame_num + JUMP_FRAMES)
        elif key == ord("A"):
            frame_num, frame = read_frame(frame_num - JUMP_FRAMES)
        elif key == ord("u"):
            if events:
                removed = events.pop()
                print(f"Undid: frame {removed['frame']} ({removed['event_type']})")
                _write_events(events, OUTPUT_CSV)
            else:
                print("Nothing to undo.")
        elif key in EVENT_KEYS:
            event_type = EVENT_KEYS[key]
            events.append({
                "frame": frame_num,
                "timestamp_sec": round(frame_num / fps, 4) if fps else None,
                "event_type": event_type,
            })
            print(f"Logged {event_type} at frame {frame_num} (t={frame_num / fps:.3f}s)")
            _write_events(events, OUTPUT_CSV)
        # any other key: just redraw current frame, no-op

    cap.release()
    cv2.destroyAllWindows()
    _write_events(events, OUTPUT_CSV)
    print(f"\nSaved {len(events)} events to {OUTPUT_CSV}")


if __name__ == "__main__":
    main()
