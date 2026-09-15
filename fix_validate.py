import subprocess
result = subprocess.run(
    ["bash", "-lc", """cd /c/Users/dbshe/rogueworks && python3 << 'PYEOF'
with open('tools/validate_data.py', 'r') as f:
    lines = f.readlines()

# Find the start of the broken block (line with 'version = data.get("version")')
# and the end (line before 'seen: dict[str, int]')
start = None
end = None
for i, line in enumerate(lines):
    if 'version = data.get("version")' in line and start is None:
        start = i
    if 'seen: dict[str, int]' in line and start is not None:
        end = i
        break

new_block = """        version = data.get("version")
        if version != 1:
            report.error(fname, f"top-level 'version' must be 1, got {version!r}")
        if schema.get("_special"):
            report.files.append({"file": fname, "entries": 0, "errors": len(report.errors) - file_errors_before})
            continue
        entries = data.get("entries")
        if not isinstance(entries, list):
            report.error(fname, f"'entries' must be an array, got {describe(entries)}")
            report.files.append({"file": fname, "entries": 0, "errors": len(report.errors) - file_errors_before})
            continue
"""

lines[start:end] = [new_block]

with open('tools/validate_data.py', 'w') as f:
    f.writelines(lines)
print(f'Fixed lines {start+1}-{end}')
PYEOF
"""],
    capture_output=True, text=True
)
print(result.stdout)
if result.stderr:
    print("STDERR:", result.stderr)
