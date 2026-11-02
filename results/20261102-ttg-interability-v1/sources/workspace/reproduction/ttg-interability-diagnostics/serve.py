"""Run the unchanged accepted observer/server from the diagnostic cache namespace."""
from pathlib import Path
import runpy
import sys
PRIMARY = Path(__file__).resolve().parents[1] / 'ttg-interability-performance'
sys.path.insert(0, str(PRIMARY))
runpy.run_path(str(PRIMARY / 'serve.py'), run_name='__main__')
