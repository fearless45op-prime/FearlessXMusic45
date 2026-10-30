import runpy
import os
import sys

# Make sure the awkward filename works
script = "music.py"
if not os.path.exists(script):
    print(f"ERROR: {script} not found")
    sys.exit(1)

runpy.run_path(script, run_name="__main__")
