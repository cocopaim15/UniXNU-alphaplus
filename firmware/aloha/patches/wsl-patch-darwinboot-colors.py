"""Full-screen colour marks around GetMemoryMap and ExitBootServices.

Text marks on a fixed row can be hidden by whatever the menu redraws, so the
last stage is reported by flooding the framebuffer instead: red = entering
GetMemoryMap, green = map returned, blue = ExitBootServices returned,
white = about to branch into the kernel.
"""
from pathlib import Path

path = Path("/root/aloha/extras/DarwinBootPkg/DarwinBootPkg/Driver/DarwinBoot.c")
text = path.read_text(encoding="utf-8")
if "MarkColor" in text:
    print("already patched")
    raise SystemExit(0)

helper = '''
STATIC
VOID
MarkColor (
  IN UINT32  Color
  )
{
  EFI_GRAPHICS_OUTPUT_PROTOCOL  *Gop;
  UINT64                        Video[6];
  UINT32                        *Fb;
  UINTN                         Words;
  UINTN                         Index;

  if (EFI_ERROR (gBS->LocateProtocol (&gEfiGraphicsOutputProtocolGuid, NULL, (VOID **)&Gop)) ||
      EFI_ERROR (DarwinBootVideoFromGop (Gop, Video))) { return; }

  Fb    = (UINT32 *)(UINTN)Video[0];
  Words = (UINTN)(Video[2] / 4) * (UINTN)Video[4];
  for (Index = 0; Index < Words; Index++) { Fb[Index] = Color; }
}

'''

anchor = "STATIC\nEFI_STATUS\nEFIAPI\nBoot ("
if anchor not in text:
    raise SystemExit("Boot anchor missing")
text = text.replace(anchor, helper + anchor, 1)

old = "  for (Attempt = 0; Attempt < 3; Attempt++) {\n    MapSize = Capacity;"
new = ('  for (Attempt = 0; Attempt < 3; Attempt++) {\n'
       '    MarkColor (0xFFFF0000);  // red: calling GetMemoryMap\n'
       '    MapSize = Capacity;')
if old not in text:
    raise SystemExit("loop anchor missing")
text = text.replace(old, new, 1)

old = "    Status = gBS->ExitBootServices (mImage, Key);\n    Mark (7, L\"EBS %r\", (UINT64)Status);"
new = ("    MarkColor (0xFF00FF00);  // green: map returned, calling ExitBootServices\n"
       "    Status = gBS->ExitBootServices (mImage, Key);\n"
       "    MarkColor (0xFF0000FF);  // blue: ExitBootServices returned\n"
       "    Mark (7, L\"EBS %r\", (UINT64)Status);")
if old not in text:
    raise SystemExit("ExitBootServices anchor missing")
text = text.replace(old, new, 1)

old = "      DarwinEnter (ArgsAddress, Address + Kernel.Entry - Kernel.Base, Address, WindowSize, Video[0], Video[2] * Video[4]);"
new = ("      MarkColor (0xFFFFFFFF);  // white: branching into the kernel\n"
       "      DarwinEnter (ArgsAddress, Address + Kernel.Entry - Kernel.Base, Address, WindowSize, Video[0], Video[2] * Video[4]);")
if old not in text:
    raise SystemExit("DarwinEnter anchor missing")
text = text.replace(old, new, 1)

path.write_text(text, encoding="utf-8")
print("patched", path)
