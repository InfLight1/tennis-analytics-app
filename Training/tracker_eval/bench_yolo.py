import sys, os, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bench import build_items, yolo_fn, score
if __name__ == '__main__':
    items = build_items()
    for c in (0.15, 0.3):
        d = score(items, yolo_fn(sys.argv[1], c), f'YOLO {sys.argv[2] if len(sys.argv) > 2 else ""} conf{c}')
