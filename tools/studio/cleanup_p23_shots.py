#!/usr/bin/env python3
"""Cleanup test debris in runs/shots/ — keep only p25-qa/seed{N}/ and p23-qa/seed{N}/."""
import os
import shutil

base = "C:/Users/dbshe/rogueworks/runs/shots"
keep_prefixes = ("p25-qa", "p23-qa", "p22")  # keep standard per-seed dirs
keep_files = ()  # keep these files
for d in os.listdir(base):
    full = os.path.join(base, d)
    if os.path.isdir(full) and not d.startswith(keep_prefixes):
        shutil.rmtree(full)
        print(f"removed dir: {d}")
    elif os.path.isfile(full) and not d.startswith(keep_files) and d.startswith("frame-"):
        os.remove(full)
        print(f"removed file: {d}")

remaining = os.listdir(base)
print("Remaining:", sorted(remaining))
