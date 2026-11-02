"""Save frames t-1,t,t+1 (as crops matching the labeled image) for every v4 TRAIN image. Held-out sets untouched."""
import cv2, glob, re, os, json, numpy as np
D = 'Training/Tennis Ball.v4-4.yolov8/train'
OUT = 'Training/tracker_eval/cache/train'
os.makedirs(OUT, exist_ok=True)
meta = []
caps = {'orig': cv2.VideoCapture('Videos/Tennis1.mp4'), 'far': cv2.VideoCapture('Videos/tennis1_clip2.mp4')}
fs = sorted(glob.glob(f'{D}/images/*'))
for k, f in enumerate(fs):
    n = os.path.basename(f)
    if re.match(r'frame_\d{6}_', n): continue  # 69 4K frames from another video (diagonal angle); skipped
    sub = 'far' if n.startswith('tennis1_clip2_f') else 'orig'
    idx = int(re.search(r'(\d+)_jpg', n).group(1)) * (15 if sub == 'orig' else 1)
    im = cv2.imread(f); H, W = im.shape[:2]
    cap = caps[sub]; cap.set(cv2.CAP_PROP_POS_FRAMES, idx - 2)
    frs = [cap.read()[1] for _ in range(5)]
    if any(x is None for x in frs): continue
    ox = oy = 0
    if sub == 'far':
        r = cv2.matchTemplate(cv2.resize(frs[2], None, fx=.25, fy=.25), cv2.resize(im, None, fx=.25, fy=.25), cv2.TM_SQDIFF_NORMED)
        _, _, (ox, oy), _ = cv2.minMaxLoc(r); ox, oy = ox * 4, oy * 4
        frs = [x[oy:oy + H, ox:ox + W] for x in frs]
    diff = np.abs(frs[2].astype(float) - im.astype(float)).mean()
    stem = f'{k:05d}'
    for j, fr in enumerate(frs):
        cv2.imwrite(f'{OUT}/{stem}_{j}.jpg', fr, [cv2.IMWRITE_JPEG_QUALITY, 95])
    lbl = os.path.join(D, 'labels', os.path.splitext(n)[0] + '.txt')
    gt = []
    if os.path.exists(lbl):
        for l in open(lbl):
            p = l.split()
            if len(p) >= 5:
                cx, cy, w, h = map(float, p[1:5]); gt.append([cx * W, cy * H, w * W, h * H])
    g = [cv2.cvtColor(x, cv2.COLOR_BGR2GRAY).astype(float) for x in frs]
    mov = []
    for cx, cy, w, h in gt:
        r = int(max(6, 0.8 * max(w, h)))
        y0, y1, x0, x1 = max(0, int(cy) - r), int(cy) + r, max(0, int(cx) - r), int(cx) + r
        mov.append(bool(min(np.abs(g[2][y0:y1, x0:x1] - g[q][y0:y1, x0:x1]).mean() for q in (0, 4)) > 6))
    meta.append(dict(stem=stem, name=n, sub=sub, idx=idx, W=W, H=H, gt=gt, mov=mov, match_diff=round(diff, 2)))
    if k % 200 == 0: print(k, len(fs), flush=True)
json.dump(meta, open(f'{OUT}/meta.json', 'w'))
print('saved', len(meta), 'bad matches', sum(m['match_diff'] > 6 for m in meta))
