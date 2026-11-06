"""Drop DarwinBoot's console prints before ExitBootServices.

The hand-off text goes through the firmware's GOP console, which is the last
thing that runs before boot services end; replace it with framebuffer marks so
the exit sequence starts immediately.
"""
from pathlib import Path

path = Path("/root/aloha/extras/DarwinBootPkg/DarwinBootPkg/Driver/DarwinBoot.c")
lines = path.read_text(encoding="utf-8").splitlines(keepends=True)
if any("quiet hand-off" in line for line in lines):
    print("already patched")
    raise SystemExit(0)

start_marker = '  Print (L"DARWINBOOT: ARM64 va=0x%lx'
end_marker = '  DEBUG ((DEBUG_ERROR, "\\nExiting boot services. A green bar across the top\\nmarks the loader handoff before the kernel branch.\\n"));'

start = next((i for i, line in enumerate(lines) if line.startswith(start_marker)), None)
end = next((i for i, line in enumerate(lines) if line.startswith(end_marker)), None)
if start is None or end is None or end <= start:
    raise SystemExit("print block markers not found")

lines[start:end + 1] = ["  // quiet hand-off: no console output before ExitBootServices\n"]
path.write_text("".join(lines), encoding="utf-8")
print("patched", path)
