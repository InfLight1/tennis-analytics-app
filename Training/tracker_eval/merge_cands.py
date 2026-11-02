"""Make candidate CSVs for scoring: tracker alone (conf remapped) or YOLO + tracker union.
Usage: merge_cands.py <yolo.csv|-> <tracker.csv> <out.csv> [k=3] [max_frame=N]"""
import sys, csv, collections
yolo, trk, out = sys.argv[1:4]
kw = dict(a.split('=') for a in sys.argv[4:]); k = float(kw.get('k', 3)); gap_only = kw.get('gap') == '1'; mf = int(kw.get('max_frame', 10**9))
rows = collections.defaultdict(list)
if yolo != '-':
    for r in csv.DictReader(open(yolo)):
        if int(r['frame']) <= mf: rows[int(r['frame'])].append([float(r[c]) for c in ('pixel_x', 'pixel_y', 'x1', 'y1', 'x2', 'y2', 'confidence')])
for r in csv.DictReader(open(trk)):
    f = int(r['frame'])
    if f > mf: continue
    x, y = float(r['pixel_x']), float(r['pixel_y']); c = min(1.0, float(r['confidence']) * k)
    if gap_only and any(d[6] >= 0.15 for d in rows[f]): continue  # only fill frames where YOLO has no usable ball
    dup = [d for d in rows[f] if abs(d[0] - x) < 15 and abs(d[1] - y) < 15]
    if dup:
        dup[0][6] = max(dup[0][6], c)
    else:
        rows[f].append([x, y, x - 8, y - 8, x + 8, y + 8, c])
with open(out, 'w', newline='') as fo:
    w = csv.writer(fo); w.writerow(['frame', 'pixel_x', 'pixel_y', 'x1', 'y1', 'x2', 'y2', 'confidence'])
    for f in sorted(rows):
        for d in rows[f]: w.writerow([f] + d)
