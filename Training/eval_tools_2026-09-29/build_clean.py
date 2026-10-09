# Held-out set = new valid+test images whose source frame was never in OLD train (and by construction not in NEW train).
import os, re, shutil, pathlib
T = pathlib.Path(r"C:\Users\rudra\Downloads\Projects\Tennis Performance App\Training")
NEW, OLD = T/"Tennis Ball.v4-4.yolov8", T/"Annotated Ball Pics"
OUT = pathlib.Path(__file__).parent/"clean_eval"
src = lambda n: re.sub(r"_(jpg|png|jpeg)\.rf\..*$", "", n)
old_train = {src(n) for n in os.listdir(OLD/"train"/"images")}
new_train = {src(n) for n in os.listdir(NEW/"train"/"images")}
shutil.rmtree(OUT, ignore_errors=True)
counts = {}
for split in ("valid", "test"):
    for n in os.listdir(NEW/split/"images"):
        s = src(n)
        if s in old_train or s in new_train: continue
        sub = "far" if s.startswith("tennis1_clip2_f") else "orig"
        for d in ("images", "labels"):
            (OUT/sub/d).mkdir(parents=True, exist_ok=True)
        shutil.copy(NEW/split/"images"/n, OUT/sub/"images"/n)
        lbl = os.path.splitext(n)[0] + ".txt"
        if (NEW/split/"labels"/lbl).exists(): shutil.copy(NEW/split/"labels"/lbl, OUT/sub/"labels"/lbl)
        counts[sub] = counts.get(sub, 0) + 1
for sub in counts:
    (OUT/f"{sub}.yaml").write_text(f"path: {(OUT/sub).as_posix()}\ntrain: images\nval: images\nnc: 1\nnames: ['Tennis-Ball']\n")
print(counts, "| old-train overlap w/ new valid+test excluded")
