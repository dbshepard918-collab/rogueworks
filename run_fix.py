#!/usr/bin/env python3
import subprocess
result = subprocess.run(
    ["bash", "-lc", "cd /c/Users/dbshe/rogueworks && python3 fix_vd.py"],
    capture_output=True, text=True
)
print(result.stdout)
if result.stderr:
    print("ERR:", result.stderr)
