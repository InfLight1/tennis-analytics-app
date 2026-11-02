"""Run a (fine-tuned) WASB tracker over a video; write ball candidates in the same CSV format as
Code/extract_raw_ball_detections.py (4K pixel coords), so offline_eval / score_all can use them.
Usage: python extract_tracker_cands.py <video> <out_csv> [ckpt=...] [scale=0.5] [thr=0.3] [end=N]"""
import sys, os, csv, time, collections, cv2, numpy as np, torch
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from load_trackers import load
MEAN = torch.tensor([0.485, 0.456, 0.406]).view(3, 1, 1).cuda(); STD = torch.tensor([0.229, 0.224, 0.225]).view(3, 1, 1).cuda()

def blobs(hm, thr):
    if hm.max() <= thr: return []
    n, lab = cv2.connectedComponents((hm > thr).astype(np.uint8))
    out = []
    for k in range(1, n):
        ys, xs = np.where(lab == k); ws = hm[ys, xs]
        out.append(((xs * ws).sum() / ws.sum(), (ys * ws).sum() / ws.sum(), float(ws.max())))
    return out

if __name__ == '__main__':
    video, out = sys.argv[1], sys.argv[2]
    kw = dict(a.split('=') for a in sys.argv[3:])
    scale, thr, end = float(kw.get('scale', 0.5)), float(kw.get('thr', 0.3)), int(kw.get('end', 10**9))
    m = load('wasb')[0]
    if kw.get('ckpt'): m.load_state_dict(torch.load(kw['ckpt'], map_location='cuda', weights_only=True))
    m.eval().half()
    cap = cv2.VideoCapture(video)
    W, H = int(cap.get(3)), int(cap.get(4)); k4 = 3840 / W  # output in 4K pixel space
    sc = scale * k4  # scale is relative to 4K
    w, h = int(round(W * sc / 32) * 32), int(round(H * sc / 32) * 32)
    buf = collections.deque(maxlen=3); fn = -1; t0 = time.time()
    def prep(fr):
        x = torch.from_numpy(cv2.resize(fr, (w, h), interpolation=cv2.INTER_AREA)[:, :, ::-1].copy()).cuda()
        return ((x.permute(2, 0, 1).float() / 255 - MEAN) / STD).half()
    with open(out, 'w', newline='') as f:
        wr = csv.writer(f); wr.writerow(['frame', 'pixel_x', 'pixel_y', 'x1', 'y1', 'x2', 'y2', 'confidence'])
        def emit(frame_no, hm):
            for x, y, c in blobs(hm, thr):
                X, Y = x * W / w * k4, y * H / h * k4
                wr.writerow([frame_no, X, Y, X - 8, Y - 8, X + 8, Y + 8, c])
        while fn < end:
            ok, fr = cap.read()
            if not ok: break
            fn += 1; buf.append(prep(fr))
            if len(buf) < 3: continue
            with torch.no_grad():
                hm = m(torch.cat(list(buf))[None])[0][0, 1].float().sigmoid().cpu().numpy()
            emit(fn - 1, hm)
            if fn % 1000 == 0: print(f'{fn} frames {time.time() - t0:.0f}s', flush=True)
    print('done', fn, out)
