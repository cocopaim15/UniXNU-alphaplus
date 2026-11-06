"""Add an "Erase boot_a" action to UniXNU's menu.

Reaching fastboot on this phone currently means going through 9008 and wiping
boot_a by hand; the menu can do the wipe itself and reset into fastboot.
"""
from pathlib import Path

BASE = Path("/root/aloha/extras/UniXNUPkg/Library/UniXNULib")

# ---------------------------------------------------------------- enum
internal = BASE / "Internal.h"
text = internal.read_text(encoding="utf-8")
if "UniXNUActionEraseBoot" not in text:
    text = text.replace(
        "  UniXNUActionExit,",
        "  UniXNUActionExit,\n  UniXNUActionEraseBoot,",
        1,
    )
    internal.write_text(text, encoding="utf-8")
    print("patched Internal.h")

# ---------------------------------------------------------------- parser + built-in entry
config = BASE / "Config.c"
text = config.read_text(encoding="utf-8")
if "erase-boot" not in text:
    old_parse = '''    } else if (AsciiStrCmp (Action, "tools") == 0) {
      Entry->Action = UniXNUActionTools;
    } else {'''
    new_parse = '''    } else if (AsciiStrCmp (Action, "tools") == 0) {
      Entry->Action = UniXNUActionTools;
    } else if (AsciiStrCmp (Action, "erase-boot") == 0) {
      Entry->Action = UniXNUActionEraseBoot;
    } else {'''
    if old_parse not in text:
        raise SystemExit("Config.c: action parser anchor missing")
    text = text.replace(old_parse, new_parse, 1)

    old_entry = '''  "[[entry]]\\n"
  "id = \\"tools\\"\\n"'''
    new_entry = '''  "[[entry]]\\n"
  "id = \\"erase-boot\\"\\n"
  "title = \\"Erase boot_a (fastboot)\\"\\n"
  "type = \\"action\\"\\n"
  "action = \\"erase-boot\\"\\n"
  "[[entry]]\\n"
  "id = \\"tools\\"\\n"'''
    if old_entry not in text:
        raise SystemExit("Config.c: built-in entry anchor missing")
    text = text.replace(old_entry, new_entry, 1)
    config.write_text(text, encoding="utf-8")
    print("patched Config.c")

# ---------------------------------------------------------------- execution
boot = BASE / "Boot.c"
text = boot.read_text(encoding="utf-8")
if "EraseBootPartition" not in text:
    helper = '''
#include <Protocol/PartitionInfo.h>
#include <Protocol/BlockIo.h>

STATIC
EFI_STATUS
EraseBootPartition (
  VOID
  )
{
  EFI_STATUS                   Status;
  EFI_HANDLE                   *Handles;
  UINTN                        Count;
  UINTN                        Index;
  EFI_PARTITION_INFO_PROTOCOL  *Info;
  EFI_BLOCK_IO_PROTOCOL        *Block;
  VOID                         *Zero;
  UINTN                        Size;

  Handles = NULL;
  Count   = 0;
  Status  = gBS->LocateHandleBuffer (ByProtocol, &gEfiPartitionInfoProtocolGuid, NULL, &Count, &Handles);
  if (EFI_ERROR (Status)) {
    return Status;
  }

  Status = EFI_NOT_FOUND;
  for (Index = 0; Index < Count; Index++) {
    if (EFI_ERROR (gBS->HandleProtocol (Handles[Index], &gEfiPartitionInfoProtocolGuid, (VOID **)&Info))) {
      continue;
    }
    if ((Info->Type != PARTITION_TYPE_GPT) || (StrCmp (Info->Info.Gpt.PartitionName, L"boot_a") != 0)) {
      continue;
    }
    if (EFI_ERROR (gBS->HandleProtocol (Handles[Index], &gEfiBlockIoProtocolGuid, (VOID **)&Block))) {
      continue;
    }

    Size = 1024 * 1024;
    Size -= Size % Block->Media->BlockSize;
    Zero  = AllocateZeroPool (Size);
    if (Zero == NULL) {
      Status = EFI_OUT_OF_RESOURCES;
      break;
    }

    Status = Block->WriteBlocks (Block, Block->Media->MediaId, 0, Size, Zero);
    if (!EFI_ERROR (Status)) {
      Block->FlushBlocks (Block);
    }
    FreePool (Zero);
    break;
  }

  FreePool (Handles);
  return Status;
}
'''
    anchor = "STATIC\nEFI_STATUS\nRunAction ("
    if anchor not in text:
        raise SystemExit("Boot.c: RunAction anchor missing")
    text = text.replace(anchor, helper + "\n" + anchor, 1)

    old_case = '''    case UniXNUActionExit:
      UniXNULog ("action: exit");
      return EFI_SUCCESS;'''
    new_case = '''    case UniXNUActionEraseBoot:
      UniXNULog ("action: erase boot_a");
      EraseBootPartition ();
      gRT->ResetSystem (EfiResetCold, EFI_SUCCESS, 0, NULL);
      break;
    case UniXNUActionExit:
      UniXNULog ("action: exit");
      return EFI_SUCCESS;'''
    if old_case not in text:
        raise SystemExit("Boot.c: action case anchor missing")
    text = text.replace(old_case, new_case, 1)
    boot.write_text(text, encoding="utf-8")
    print("patched Boot.c")
