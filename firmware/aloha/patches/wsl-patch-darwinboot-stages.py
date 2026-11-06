"""Stage marks between the segment copy and ExitBootServices, and skip the
FAT volume close that runs in that window."""
from pathlib import Path

path = Path("/root/aloha/extras/DarwinBootPkg/DarwinBootPkg/Driver/DarwinBoot.c")
text = path.read_text(encoding="utf-8")
if "MARK args" in text:
    print("already patched")
    raise SystemExit(0)

old = "  Args = (DARWIN_BOOT_ARGS *)(UINTN)ArgsAddress;"
new = ('  Mark (7, L"MARK args %lx", ArgsAddress);\n'
       "  Args = (DARWIN_BOOT_ARGS *)(UINTN)ArgsAddress;")
if old not in text:
    raise SystemExit("args anchor missing")
text = text.replace(old, new, 1)

old = "  Status = GetMap (&Map, &Capacity, &MapSize, &Key, &Stride);"
new = ('  Mark (8, L"MARK payloads %lx", Used);\n'
       "  Status = GetMap (&Map, &Capacity, &MapSize, &Key, &Stride);")
if old not in text:
    raise SystemExit("GetMap anchor missing")
text = text.replace(old, new, 1)

old = "  for (Attempt = 0; Attempt < 3; Attempt++) {"
new = ('  Mark (9, L"MARK map %lx", MapSize);\n'
       "  for (Attempt = 0; Attempt < 3; Attempt++) {")
if old not in text:
    raise SystemExit("EBS loop anchor missing")
text = text.replace(old, new, 1)

old = "  Root->Close (Root); Root = NULL;"
new = "  // Root is deliberately left open: closing the FAT volume here touches\n  // UFS again and is the last thing before ExitBootServices.\n  Root = NULL;"
if old not in text:
    raise SystemExit("Root close anchor missing")
text = text.replace(old, new, 1)

path.write_text(text, encoding="utf-8")
print("patched", path)
