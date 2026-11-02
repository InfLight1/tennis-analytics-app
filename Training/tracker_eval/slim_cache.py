"""Convert the 10 GB items.npz into JPEGs (frames t-1..t+1) + json, so the test loads fast."""
import numpy as np, cv2, json, os
C = 'Training/tracker_eval/cache'; O = f'{C}/heldout'; os.makedirs(O, exist_ok=True)
items = list(np.load(f'{C}/items.npz', allow_pickle=True)['items'])
meta = []
for k, i in enumerate(items):
    for j in (1, 2, 3):
        cv2.imwrite(f'{O}/{k:04d}_{j}.jpg', i['frames'][j], [cv2.IMWRITE_JPEG_QUALITY, 95])
    meta.append(dict(k=k, name=i['name'], sub=i['sub'], gt=[list(map(float, g)) for g in i['gt']], mov=list(map(bool, i['mov']))))
json.dump(meta, open(f'{O}/meta.json', 'w')); print(len(meta))
