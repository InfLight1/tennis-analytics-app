"""Ball detector comparison on held-out labeled frames (never in YOLO training).
Metrics: recall on moving (in-play) balls, recall on all balls, false detections per frame."""
import cv2, glob, re, os, sys, json, numpy as np, torch
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
B = 'Training/eval_tools_2026-09-29/clean_eval'
CACHE = 'Training/tracker_eval/cache'
os.makedirs(CACHE, exist_ok=True)

def boxes(lbl, W, H):
    out = []
    if os.path.exists(lbl):
        for l in open(lbl):
            p = l.split()
            if len(p) >= 5:
                cx, cy, w, h = map(float, p[1:5]); out.append((cx * W, cy * H, w * W, h * H))
    return out

def build_items():
    """Each item: name, 5 frames (t-2..t+2) as crops matching the labeled image, GT boxes, moving flags."""
    hp = f'{CACHE}/heldout/meta.json'
    if os.path.exists(hp):  # fast path: JPEGs of frames t-1..t+1 (index 1..3; 0 and 4 not kept)
        items = json.load(open(hp))
        for i in items:
            fr = [cv2.imread(f"{CACHE}/heldout/{i['k']:04d}_{j}.jpg") for j in (1, 2, 3)]
            i['frames'] = np.stack([fr[0]] + fr + [fr[2]])
        return items
    p = f'{CACHE}/items.npz'
    if os.path.exists(p):
        d = np.load(p, allow_pickle=True); return list(d['items'])
    items = []
    for sub, video in (('orig', 'Videos/Tennis1.mp4'), ('far', 'Videos/tennis1_clip2.mp4')):
        cap = cv2.VideoCapture(video)
        for f in sorted(glob.glob(f'{B}/{sub}/images/*')):
            n = os.path.basename(f); im = cv2.imread(f); H, W = im.shape[:2]
            idx = int(re.search(r'(\d+)_jpg', n).group(1)) * (15 if sub == 'orig' else 1)
            cap.set(cv2.CAP_PROP_POS_FRAMES, idx - 2)
            frs = [cap.read()[1] for _ in range(5)]
            if any(x is None for x in frs): continue
            ox = oy = 0
            if sub == 'far':
                r = cv2.matchTemplate(cv2.resize(frs[2], None, fx=.25, fy=.25), cv2.resize(im, None, fx=.25, fy=.25), cv2.TM_SQDIFF_NORMED)
                _, _, (ox, oy), _ = cv2.minMaxLoc(r); ox, oy = ox * 4, oy * 4
                frs = [x[oy:oy + H, ox:ox + W] for x in frs]
            gt = boxes(os.path.join(B, sub, 'labels', os.path.splitext(n)[0] + '.txt'), W, H)
            mov = []
            g = [cv2.cvtColor(x, cv2.COLOR_BGR2GRAY).astype(float) for x in frs]
            for cx, cy, w, h in gt:
                r = int(max(6, 0.8 * max(w, h)))
                y0, y1, x0, x1 = max(0, int(cy) - r), int(cy) + r, max(0, int(cx) - r), int(cx) + r
                d = min(np.abs(g[2][y0:y1, x0:x1] - g[k][y0:y1, x0:x1]).mean() for k in (0, 4))
                mov.append(bool(d > 6))
            items.append(dict(name=n, sub=sub, frames=np.stack(frs), gt=gt, mov=mov))
        print(sub, 'items', sum(i['sub'] == sub for i in items), flush=True)
    np.savez(p, items=np.array(items, dtype=object))
    return items

def match(dets, gt, tol_min=6):
    used = set(); tp = []
    for gi, (cx, cy, w, h) in enumerate(gt):
        tol = max(tol_min, 1.0 * max(w, h))
        ok = [k for k, (x, y, s) in enumerate(dets) if k not in used and np.hypot(x - cx, y - cy) <= tol]
        if ok:
            used.add(ok[0]); tp.append(gi)
    return tp, len(dets) - len(used)

def score(items, det_fn, label):
    res = {}
    for sub in ('orig', 'far', 'all'):
        it = [i for i in items if sub == 'all' or i['sub'] == sub]
        mv = mt = av = at = fp = 0
        for i in it:
            dets = det_fn(i)
            tp, f = match(dets, i['gt'])
            at += len(i['gt']); av += len(tp); fp += f
            mt += sum(i['mov']); mv += sum(1 for g in tp if i['mov'][g])
        res[sub] = dict(inplay=f'{mv}/{mt}', inplay_pct=round(100 * mv / max(mt, 1), 1),
                        all_pct=round(100 * av / max(at, 1), 1), fp_per_frame=round(fp / max(len(it), 1), 2), n=len(it))
    print(label, json.dumps(res), flush=True)
    return res

# ---- detectors
def yolo_fn(weights, conf):
    from ultralytics import YOLO
    m = YOLO(weights)
    def f(i):
        r = m(i['frames'][2], conf=conf, imgsz=1280, verbose=False, half=True)[0]
        return [((a + c) / 2, (b + d) / 2, s) for (a, b, c, d), s in zip(r.boxes.xyxy.tolist(), r.boxes.conf.tolist())]
    return f

MEAN = np.array([0.485, 0.456, 0.406]); STD = np.array([0.229, 0.224, 0.225])
def tracker_fn(name, scale, thr=0.5, rgb=True, model=None, rel4k=False):
    from load_trackers import load
    m = model or load(name)[0]
    def f(i):
        frs = i['frames'][1:4]
        H, W = frs[0].shape[:2]
        sc = scale * (2 if (rel4k and i['sub'] == 'orig') else 1)
        h, w = int(round(H * sc / 32) * 32), int(round(W * sc / 32) * 32)
        xs = []
        for fr in frs:
            x = cv2.resize(fr, (w, h), interpolation=cv2.INTER_AREA)
            if rgb: x = x[:, :, ::-1]
            xs.append(((x / 255.0 - MEAN) / STD).transpose(2, 0, 1))
        t = torch.from_numpy(np.concatenate(xs)).float()[None].cuda()
        with torch.no_grad(), torch.autocast('cuda', dtype=torch.float16):
            hm = m(t)[0][0, 1].float().sigmoid().cpu().numpy()
        if hm.max() <= thr: return []
        _, lab = cv2.threshold(hm, thr, 1, cv2.THRESH_BINARY)
        n, labels = cv2.connectedComponents(lab.astype(np.uint8))
        out = []
        for k in range(1, n):
            ys, xs_ = np.where(labels == k); ws = hm[ys, xs_]
            out.append((float((xs_ * ws).sum() / ws.sum()) * W / w, float((ys * ws).sum() / ws.sum()) * H / h, float(ws.sum())))
        return out
    return f

if __name__ == '__main__':
    items = build_items()
    mv = sum(sum(i['mov']) for i in items); tot = sum(len(i['gt']) for i in items)
    print('frames', len(items), 'balls', tot, 'moving', mv, flush=True)
    which = sys.argv[1] if len(sys.argv) > 1 else 'all'
    if which in ('all', 'yolo'):
        for w in ('Training/runs/detect/tennis_ball_v1-5/weights/best.pt', 'Training/runs/detect/tennis_ball_v2/weights/best.pt'):
            for c in (0.15, 0.3):
                score(items, yolo_fn(w, c), f'YOLO {w.split("/")[3]} conf{c}')
    if which in ('all', 'trk'):
        from load_trackers import load
        for name in ('wasb', 'tracknetv2'):
            m = load(name)[0]
            for sc in (0.267, 0.5, 0.75, 1.0):
                score(items, tracker_fn(name, sc, model=m), f'{name} scale{sc}')

def run_ft(ckpt, scales=(0.5,), thrs=(0.3, 0.5)):
    """Heatmap computed once per frame, then scored at each threshold."""
    from load_trackers import load
    items = build_items()
    m = load('wasb')[0]; m.load_state_dict(torch.load(ckpt, map_location='cuda', weights_only=True)); m.eval()
    res = {}
    for sc in scales:
        hms = {}
        for i in items:
            frs = i['frames'][1:4]; H, W = frs[0].shape[:2]
            s2 = sc * (2 if i['sub'] == 'orig' else 1)
            h, w = int(round(H * s2 / 32) * 32), int(round(W * s2 / 32) * 32)
            xs = [((cv2.resize(fr, (w, h), interpolation=cv2.INTER_AREA)[:, :, ::-1] / 255.0 - MEAN) / STD).transpose(2, 0, 1) for fr in frs]
            with torch.no_grad(), torch.autocast('cuda', dtype=torch.float16):
                hms[i['name']] = (m(torch.from_numpy(np.concatenate(xs)).float()[None].cuda())[0][0, 1].float().sigmoid().cpu().numpy(), W / w, H / h)
        def fn_for(t):
            def f(i):
                hm, kx, ky = hms[i['name']]
                if hm.max() <= t: return []
                n, lab = cv2.connectedComponents((hm > t).astype(np.uint8)); out = []
                for k in range(1, n):
                    ys, xs_ = np.where(lab == k); ws = hm[ys, xs_]
                    out.append((float((xs_ * ws).sum() / ws.sum()) * kx, float((ys * ws).sum() / ws.sum()) * ky, float(ws.max())))
                return out
            return f
        for t in thrs:
            res[(sc, t)] = score(items, fn_for(t), f'FT {os.path.basename(ckpt)} scale{sc} thr{t}')
    return res
