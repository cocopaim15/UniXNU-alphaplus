"""Move the cached-video globals above their first use (DiagDraw)."""
from pathlib import Path

path = Path("/root/aloha/extras/DarwinBootPkg/DarwinBootPkg/Driver/DarwinBoot.c")
text = path.read_text(encoding="utf-8")

block = ("STATIC UINT64   mVideo[6];\n"
         "STATIC BOOLEAN  mVideoCached = FALSE;\n"
         "\n"
         "STATIC\n"
         "VOID\n"
         "MarkVideoCapture (\n"
         "  IN CONST UINT64  *Video\n"
         "  )\n"
         "{\n"
         "  CopyMem (mVideo, Video, sizeof (mVideo));\n"
         "  mVideoCached = TRUE;\n"
         "}\n"
         "\n")

if block not in text:
    raise SystemExit("global block missing")

text = text.replace(block, "", 1)

anchor = '#include "DiagFont.h"\n'
if anchor not in text:
    raise SystemExit("DiagFont include missing")

text = text.replace(anchor, anchor + "\n" + block, 1)
path.write_text(text, encoding="utf-8")
print("moved globals above DiagDraw")
