"""Report ExitBootServices and failure codes as on-screen marks."""
from pathlib import Path

path = Path("/root/aloha/extras/DarwinBootPkg/DarwinBootPkg/Driver/DarwinBoot.c")
text = path.read_text(encoding="utf-8")
if "EBS %r" in text:
    print("already patched")
    raise SystemExit(0)

old = "    Status = gBS->ExitBootServices (mImage, Key);\n"
new = ("    Status = gBS->ExitBootServices (mImage, Key);\n"
       "    Mark (7, L\"EBS %r\", (UINT64)Status);\n")
if old not in text:
    raise SystemExit("ExitBootServices anchor missing")
text = text.replace(old, new, 1)

old_fail = '  Print (L"DARWINBOOT: boot refused: %r; firmware retained\\n", Status);'
new_fail = ('  Mark (7, L"FAIL %r", (UINT64)Status);\n'
            '  Print (L"DARWINBOOT: boot refused: %r; firmware retained\\n", Status);')
if old_fail not in text:
    raise SystemExit("Fail anchor missing")
text = text.replace(old_fail, new_fail, 1)

path.write_text(text, encoding="utf-8")
print("patched", path)
