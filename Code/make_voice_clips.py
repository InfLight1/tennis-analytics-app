"""
make_voice_clips.py

Records every line hands-free recording says (2026-10-29) as a small mp3 in the
"mild2" AI voice (Chatterbox, Rudra's local voice tool), so the phone plays a
natural voice instead of its built-in robot voice. The page falls back to the
phone's own voice for any line without a clip.

Writes web_assets/voice-<key>.mp3 and web_assets/voice-clips.json ({text: file}).
Lines: the aiming tips from aim_guide.py (read from the file, no import) plus the
lines in record_match.js below. Edit a line there AND here, then rerun:
    C:\\Users\\rudra\\tools\\chatterbox\\.venv\\Scripts\\python.exe Code/make_voice_clips.py [--only key,key]
"""

import argparse
import ast
import json
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "web_assets"
VOICE = Path("C:/Users/rudra/tools/chatterbox/voices/mild2.wav")
TEMPO = 1.0

PAGE_LINES = {   # key -> exactly the text record_match.js passes to say()
    "intro": "Put the phone up on the fence, sideways, pointing at the court. I'll tell you how to aim it.",
    "no-server": "I can't reach the server. Check the signal.",
    "doubles-seen": "I see four players, so this is doubles. I'll check the alleys are in view too.",
    "marking-singles": "Good spot. Marking the singles court.",
    "marking-doubles": "Good spot. Marking the doubles court.",
    "went-wrong": "Something went wrong. Please take the phone down and check the screen.",
    "check-lines": "Please take the phone down and check the court lines on the screen.",
    "count-10": "Recording starts in 10 seconds.",
    "count-5": "5", "count-3": "3", "count-2": "2", "count-1": "1",
    "recording": "Recording. Good luck!",
}
SPOKEN = {"5": "Five.", "3": "Three.", "2": "Two.", "1": "One."}   # single digits read badly as text


def tips():
    tree = ast.parse((ROOT / "Code" / "aim_guide.py").read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(getattr(t, "id", "") == "TIPS" for t in node.targets):
            return {f"tip-{k.replace('_', '-')}": v for k, v in ast.literal_eval(node.value).items()}
    raise SystemExit("TIPS not found in aim_guide.py")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", default="", help="comma-separated keys to redo")
    ap.add_argument("--seed", type=int, default=7)
    a = ap.parse_args()
    lines = {**tips(), **PAGE_LINES}
    only = {k for k in a.only.split(",") if k}

    import torch
    import torchaudio as ta
    from chatterbox.tts_turbo import ChatterboxTurboTTS
    model = ChatterboxTurboTTS.from_pretrained(device="cuda" if torch.cuda.is_available() else "cpu")
    clips = {}
    for key, text in lines.items():
        out = OUT / f"voice-{key}.mp3"
        clips[text] = out.name
        if (only and key not in only) or (not only and out.exists()):   # --only: just those; else: missing ones
            continue
        torch.manual_seed(a.seed)
        wav = model.generate(SPOKEN.get(text, text), audio_prompt_path=str(VOICE)).cpu()
        with tempfile.TemporaryDirectory() as d:
            raw = Path(d) / "raw.wav"
            ta.save(str(raw), wav, model.sr)
            # trim silence at both ends, even loudness, small mono mp3
            subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", str(raw), "-af",
                            "silenceremove=start_periods=1:start_threshold=-45dB,areverse,"
                            "silenceremove=start_periods=1:start_threshold=-45dB,areverse,"
                            f"atempo={TEMPO},loudnorm=I=-14:TP=-1.5:LRA=11",
                            "-ac", "1", "-ar", "24000", "-b:a", "48k", str(out)], check=True)
        print(f"{key}: {text}")
    (OUT / "voice-clips.json").write_text(json.dumps(clips, indent=1), encoding="utf-8")
    print(f"{len(clips)} lines -> {OUT / 'voice-clips.json'}")


if __name__ == "__main__":
    main()
