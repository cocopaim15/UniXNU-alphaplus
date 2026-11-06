"""Cache the framebuffer so marks still work after ExitBootServices.

Boot services disappear once ExitBootServices returns, so Mark()/MarkColor()
must not look the GOP up again; capture it right after ReadBootVideo().
All snippets are single-line strings with escapes so the patch is easy to read.
"""
from pathlib import Path

path = Path("/root/aloha/extras/DarwinBootPkg/DarwinBootPkg/Driver/DarwinBoot.c")
text = path.read_text(encoding="utf-8")
if "mVideoCached" in text:
    print("already patched")
    raise SystemExit(0)

globals_code = ("STATIC UINT64   mVideo[6];\n"
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

anchor = "STATIC\nVOID\nMark ("
if anchor not in text:
    raise SystemExit("Mark anchor missing")
text = text.replace(anchor, globals_code + anchor, 1)

lookup = ("if (EFI_ERROR (gBS->LocateProtocol (&gEfiGraphicsOutputProtocolGuid, NULL, (VOID **)&Gop)) ||\n"
          "      EFI_ERROR (DarwinBootVideoFromGop (Gop, Video))) { return; }")
cached = ("if (mVideoCached) {\n"
          "    CopyMem (Video, mVideo, sizeof (mVideo));\n"
          "  } else if (EFI_ERROR (gBS->LocateProtocol (&gEfiGraphicsOutputProtocolGuid, NULL, (VOID **)&Gop)) ||\n"
          "             EFI_ERROR (DarwinBootVideoFromGop (Gop, Video))) { return; }")

if text.count(lookup) < 2:
    raise SystemExit(f"expected two GOP lookups, found {text.count(lookup)}")
text = text.replace(lookup, cached)

old = "  Status = ReadBootVideo (Video);\n  if (EFI_ERROR (Status)) { goto Fail; }"
new = ("  Status = ReadBootVideo (Video);\n  if (EFI_ERROR (Status)) { goto Fail; }\n"
       "  MarkVideoCapture (Video);")
if old not in text:
    raise SystemExit("ReadBootVideo anchor missing")
text = text.replace(old, new, 1)

path.write_text(text, encoding="utf-8")
print("patched", path)
