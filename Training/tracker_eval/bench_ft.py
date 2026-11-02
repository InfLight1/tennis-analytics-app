import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bench import run_ft
if __name__ == '__main__':
    sc = tuple(float(x) for x in (sys.argv[2].split(',') if len(sys.argv) > 2 else ['0.5']))
    run_ft(sys.argv[1], sc, (0.2, 0.3, 0.5))
