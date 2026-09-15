with open('tools/validate_data.py') as f:
    lines = f.readlines()

# Find and fix the special block
start = next(i for i,l in enumerate(lines) if 'if schema.get("_special"):' in l and i > 500)
end = next(i for i,l in enumerate(lines) if 'audio.json uses' in l and i > start)

new_lines = [
    '        if schema.get("_special"):\n',
    '            report.files.append({\n',
    '                "file": fname,\n',
    '                "entries": 0,\n',
    '                "errors": len(report.errors) - file_errors_before,\n',
    '            })\n',
    '            continue\n',
    '\n',
]

lines[start:end] = new_lines

with open('tools/validate_data.py', 'w') as f:
    f.writelines(lines)
print(f"Fixed lines {start+1}-{end}")
