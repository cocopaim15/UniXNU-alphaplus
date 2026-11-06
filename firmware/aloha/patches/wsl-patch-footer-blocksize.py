"""Report the block-size mix of the block devices in the menu footer."""
from pathlib import Path

path = Path("/root/aloha/extras/UniXNUPkg/Library/UniXNULib/Main.c")
text = path.read_text(encoding="utf-8")
if "bs4k" in text:
    print("already patched")
    raise SystemExit(0)

anchor = '''      L"blk %u part %u fs %u efi %u cfg %u",'''
replacement = '''      L"blk %u part %u fs %u efi %u cfg %u bs4k %u bs512 %u",'''
if anchor not in text:
    raise SystemExit("format anchor missing")
text = text.replace(anchor, replacement, 1)

anchor = '''      (UINT32)EfiCount,
      (UINT32)CfgCount
      );'''
replacement = '''      (UINT32)EfiCount,
      (UINT32)CfgCount,
      (UINT32)Count4k,
      (UINT32)Count512
      );'''
if anchor not in text:
    raise SystemExit("args anchor missing")
text = text.replace(anchor, replacement, 1)

# Count block sizes over the BlockIo handles right after the counts.
anchor = '''    if (!EFI_ERROR (gBS->LocateHandleBuffer (ByProtocol, &gEfiPartitionInfoProtocolGuid, NULL, &ProbeCount, &Probe))) {'''
insert = '''    if (!EFI_ERROR (gBS->LocateHandleBuffer (ByProtocol, &gEfiBlockIoProtocolGuid, NULL, &ProbeCount, &Probe))) {
      for (ProbeIndex = 0; ProbeIndex < ProbeCount; ProbeIndex++) {
        EFI_BLOCK_IO_PROTOCOL  *Blk;
        if (!EFI_ERROR (gBS->HandleProtocol (Probe[ProbeIndex], &gEfiBlockIoProtocolGuid, (VOID **)&Blk)) &&
            (Blk->Media != NULL)) {
          if (Blk->Media->BlockSize == 4096) {
            Count4k++;
          } else if (Blk->Media->BlockSize == 512) {
            Count512++;
          }
        }
      }
      FreePool (Probe);
      Probe = NULL;
    }

''' + anchor
if anchor not in text:
    raise SystemExit("probe anchor missing")
text = text.replace(anchor, insert, 1)

text = text.replace(
    "    UINTN       ProbeIndex;",
    "    UINTN       ProbeIndex;\n    UINTN       Count4k = 0;\n    UINTN       Count512 = 0;",
    1,
)

if "#include <Protocol/BlockIo.h>" not in text:
    text = text.replace(
        '#include "Internal.h"',
        '#include "Internal.h"\n#include <Protocol/BlockIo.h>',
        1,
    )

path.write_text(text, encoding="utf-8")
print("patched", path)
