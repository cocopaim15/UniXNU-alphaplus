"""Draw stage markers from DarwinBoot straight onto the framebuffer."""
from pathlib import Path

path = Path("/root/aloha/extras/DarwinBootPkg/DarwinBootPkg/Driver/DarwinBoot.c")
text = path.read_text(encoding="utf-8")
if "MARK (" in text:
    print("already patched")
    raise SystemExit(0)

helper = '''
STATIC
VOID
Mark (
  IN UINTN         Row,
  IN CONST CHAR16  *Text,
  IN UINT64        Value
  )
{
  CHAR16  Line[96];

  UnicodeSPrint (Line, sizeof (Line), Text, Value);
  DiagDraw (Line, Row);
}

'''

anchor = "STATIC\nEFI_STATUS\nEFIAPI\nBoot ("
if anchor not in text:
    raise SystemExit("Boot() anchor missing")
text = text.replace(anchor, helper + anchor, 1)

pairs = [
    (
        "  Status = ReadFile (Root, Request->KernelPath, SIZE_128MB, &Image, &ImageSize);\n"
        "  if (EFI_ERROR (Status)) { goto Fail; }",
        "  Mark (4, L\"MARK read kernel %lx\", (UINT64)ImageSize);\n"
        "  Status = ReadFile (Root, Request->KernelPath, SIZE_128MB, &Image, &ImageSize);\n"
        "  if (EFI_ERROR (Status)) { goto Fail; }\n"
        "  Mark (4, L\"MARK kernel %lx\", (UINT64)ImageSize);",
    ),
    (
        "  Status = ParseKernel (Image, ImageSize, &Kernel);\n"
        "  if (EFI_ERROR (Status)) { goto Fail; }",
        "  Status = ParseKernel (Image, ImageSize, &Kernel);\n"
        "  if (EFI_ERROR (Status)) { goto Fail; }\n"
        "  Mark (4, L\"MARK macho entry %lx\", Kernel.Entry);",
    ),
    (
        "  Status = ReadBootVideo (Video);\n"
        "  if (EFI_ERROR (Status)) { goto Fail; }\n"
        "  Status = AllocateWindow (&Kernel, WindowSize, &Address);\n"
        "  if (EFI_ERROR (Status)) { goto Fail; }",
        "  Status = ReadBootVideo (Video);\n"
        "  if (EFI_ERROR (Status)) { goto Fail; }\n"
        "  Mark (5, L\"MARK video %lx\", Video[3]);\n"
        "  Status = AllocateWindow (&Kernel, WindowSize, &Address);\n"
        "  if (EFI_ERROR (Status)) { goto Fail; }\n"
        "  Mark (5, L\"MARK window %lx\", Address);",
    ),
    (
        "  Args = (DARWIN_BOOT_ARGS *)(UINTN)ArgsAddress;",
        "  Mark (6, L\"MARK copied %lx\", Used);\n"
        "  Args = (DARWIN_BOOT_ARGS *)(UINTN)ArgsAddress;",
    ),
    (
        "  Print (L\"DARWINBOOT: inputs validated; exiting boot services\\n\");",
        "  Mark (6, L\"MARK exit boot %lx\", ArgsAddress);\n"
        "  Print (L\"DARWINBOOT: inputs validated; exiting boot services\\n\");",
    ),
    (
        "      DarwinEnter (ArgsAddress, Address + Kernel.Entry - Kernel.Base, Address, WindowSize, Video[0], Video[2] * Video[4]);",
        "      Mark (7, L\"MARK jumping %lx\", Address + Kernel.Entry - Kernel.Base);\n"
        "      DarwinEnter (ArgsAddress, Address + Kernel.Entry - Kernel.Base, Address, WindowSize, Video[0], Video[2] * Video[4]);",
    ),
]

for old, new in pairs:
    if old not in text:
        raise SystemExit(f"anchor missing:\n{old[:100]}")
    text = text.replace(old, new, 1)

path.write_text(text, encoding="utf-8")
print("patched", path)
