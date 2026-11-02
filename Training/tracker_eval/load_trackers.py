"""Load the WASB-SBDT tennis trackers (MIT) without hydra. Weights loaded weights_only."""
import sys, os, torch, yaml
HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, '..', 'ext', 'WASB-SBDT', 'src')
WEIGHTS = os.path.join(HERE, '..', 'ext', 'weights')
sys.path.insert(0, SRC)
from models import build_model  # noqa: E402

class AD(dict):
    def __getattr__(self, k):
        try: return self[k]
        except KeyError: raise AttributeError(k)

def ad(o):
    if isinstance(o, dict): return AD({k: ad(v) for k, v in o.items()})
    if isinstance(o, list): return [ad(v) for v in o]
    return o

FILES = {'wasb': 'wasb_tennis_best.pth.tar', 'tracknetv2': 'tracknetv2_tennis_best.pth.tar'}
CFG = {'wasb': 'wasb.yaml', 'tracknetv2': 'tracknetv2.yaml'}

def load(name, device='cuda'):
    cfg = ad({'model': yaml.safe_load(open(os.path.join(SRC, 'configs', 'model', CFG[name])))})
    model = build_model(cfg) if name != 'wasb' else __import__('models').HRNet(cfg['model'])
    ck = torch.load(os.path.join(WEIGHTS, FILES[name]), map_location='cpu', weights_only=True)
    sd = ck.get('model_state_dict', ck.get('state_dict', ck)) if isinstance(ck, dict) else ck
    sd = {k.replace('module.', '', 1): v for k, v in sd.items()}
    missing, unexpected = model.load_state_dict(sd, strict=False)
    return model.to(device).eval(), cfg['model'], missing, unexpected

if __name__ == '__main__':
    for n in FILES:
        m, c, mi, un = load(n)
        x = torch.zeros(1, 9, 288, 512, device='cuda')
        with torch.no_grad():
            y = m(x)
        y0 = y[0] if isinstance(y, dict) else y
        print(n, 'missing', len(mi), 'unexpected', len(un), 'out', tuple(y0.shape), sum(p.numel() for p in m.parameters()))
