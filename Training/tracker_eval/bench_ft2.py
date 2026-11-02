import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bench import run_ft
if __name__ == '__main__':
    run_ft(sys.argv[1], tuple(float(x) for x in sys.argv[2].split(',')), tuple(float(x) for x in sys.argv[3].split(',')))
