"""Fine-tune a WASB-SBDT tennis tracker on our labels (train split only).
Target = moving (in-play) balls on the middle frame; still balls are negatives. Run as a script (Windows)."""
import cv2, json, os, sys, random, numpy as np, torch, torch.nn.functional as F
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from load_trackers import load
C = 'Training/tracker_eval/cache/train'
MEAN = np.array([0.485, 0.456, 0.406]); STD = np.array([0.229, 0.224, 0.225])

def args():
    a = dict(model='wasb', scale=0.5, epochs=25, crop_w=512, crop_h=288, bs=8, lr=1e-4, sigma=2.5, out='Training/tracker_eval/ft_wasb.pt', seed=0)
    for kv in sys.argv[1:]:
        k, v = kv.split('='); a[k] = type(a[k])(v)
    return a

class DS(torch.utils.data.Dataset):
    def __init__(self, meta, a):
        self.m, self.a = meta, a
    def __len__(self): return len(self.m)
    def __getitem__(self, i):
        m, a = self.m[i], self.a
        s = a['scale'] * (2 if m['sub'] == 'orig' else 1) * random.uniform(0.8, 1.25)  # scale is relative to 4K; orig frames are 1080p
        frs = [cv2.imread(f"{C}/{m['stem']}_{j}.jpg") for j in (1, 2, 3)]
        H, W = frs[0].shape[:2]; h, w = int(H * s), int(W * s)
        frs = [cv2.resize(x, (w, h), interpolation=cv2.INTER_AREA) for x in frs]
        cw, ch = a['crop_w'], a['crop_h']
        if w < cw or h < ch:  # pad small (far-crop) frames up to the crop size
            frs = [cv2.copyMakeBorder(x, 0, max(0, ch - h), 0, max(0, cw - w), cv2.BORDER_CONSTANT) for x in frs]
            h, w = frs[0].shape[:2]
        pts = [(cx * s, cy * s) for (cx, cy, _, _), mv in zip(m['gt'], m['mov']) if mv]
        if pts and random.random() < 0.8:
            px, py = random.choice(pts)
            x0 = int(np.clip(px - random.uniform(0.1, 0.9) * cw, 0, w - cw)); y0 = int(np.clip(py - random.uniform(0.1, 0.9) * ch, 0, h - ch))
        else:
            x0, y0 = random.randint(0, w - cw), random.randint(0, h - ch)
        flip = random.random() < 0.5
        xs = []
        for fr in frs:
            c = fr[y0:y0 + ch, x0:x0 + cw][:, :, ::-1]
            if flip: c = c[:, ::-1]
            xs.append(((c / 255.0 - MEAN) / STD).transpose(2, 0, 1))
        yy, xx = np.mgrid[0:ch, 0:cw]
        hm = np.zeros((ch, cw), np.float32)
        for px, py in pts:
            px, py = px - x0, py - y0
            if flip: px = cw - 1 - px
            hm = np.maximum(hm, np.exp(-((xx - px) ** 2 + (yy - py) ** 2) / (2 * a['sigma'] ** 2)))
        return torch.from_numpy(np.concatenate(xs).copy()).float(), torch.from_numpy(hm)

def focal(logit, t):
    p = logit.sigmoid().clamp(1e-4, 1 - 1e-4)
    pos = t.ge(0.99).float(); neg = 1 - pos
    lp = -torch.log(p) * (1 - p) ** 2 * pos
    ln = -torch.log(1 - p) * p ** 2 * (1 - t) ** 4 * neg
    return (lp.sum() + ln.sum()) / pos.sum().clamp(min=1)

if __name__ == '__main__':
    a = args(); random.seed(a['seed']); torch.manual_seed(a['seed'])
    meta = [m for m in json.load(open(f'{C}/meta.json')) if m['match_diff'] <= 6]
    model, _, _, _ = load(a['model']); model.train()
    dl = torch.utils.data.DataLoader(DS(meta, a), batch_size=a['bs'], shuffle=True, num_workers=0, drop_last=True)
    opt = torch.optim.AdamW(model.parameters(), lr=a['lr'], weight_decay=1e-4)
    sched = torch.optim.lr_scheduler.CosineAnnealingLR(opt, a['epochs'] * len(dl))
    scaler = torch.amp.GradScaler()
    print(a, 'clips', len(meta), flush=True)
    for ep in range(a['epochs']):
        tot = 0
        for x, t in dl:
            x, t = x.cuda(), t.cuda()
            with torch.autocast('cuda', dtype=torch.float16):
                out = model(x)[0][:, 1]
            loss = focal(out.float(), t)
            opt.zero_grad(); scaler.scale(loss).backward(); scaler.step(opt); scaler.update(); sched.step()
            tot += loss.item(); it = getattr(dl, '_n', 0) + 1; dl._n = it
            if it % 100 == 0: print(f'  iter {it} loss {loss.item():.4f}', flush=True)
        print(f'epoch {ep + 1} loss {tot / len(dl):.4f}', flush=True)
        torch.save(model.state_dict(), a['out'])
