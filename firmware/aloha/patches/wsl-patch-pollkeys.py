"""Poll every SimpleTextInput(Ex) device directly from the menu loop.

On this board the console splitter does not forward the phone's buttons, so
the menu waits forever. Polling the protocol instances sidesteps it, and any
key that arrives is treated as a key: volume keys move, anything else confirms.
"""
from pathlib import Path

MENU = Path("/root/aloha/extras/UniXNUPkg/Library/UniXNULib/Menu.c")
text = MENU.read_text(encoding="utf-8")
if "PollAnyKey" in text:
    print("already patched")
    raise SystemExit(0)

poll_fn = '''
STATIC
BOOLEAN
PollAnyKey (
  OUT EFI_INPUT_KEY  *Key
  )
{
  EFI_STATUS  Status;
  EFI_HANDLE  *Handles;
  UINTN       Count;
  UINTN       Index;
  BOOLEAN     Found;

  ZeroMem (Key, sizeof (*Key));
  if ((gST->ConIn != NULL) &&
      !EFI_ERROR (gST->ConIn->ReadKeyStroke (gST->ConIn, Key)) &&
      ((Key->ScanCode != 0) || (Key->UnicodeChar != 0)))
  {
    return TRUE;
  }

  Handles = NULL;
  Count   = 0;
  Found   = FALSE;
  if (EFI_ERROR (gBS->LocateHandleBuffer (ByProtocol, &gEfiSimpleTextInputExProtocolGuid, NULL, &Count, &Handles))) {
    return FALSE;
  }

  for (Index = 0; (Index < Count) && !Found; Index++) {
    EFI_SIMPLE_TEXT_INPUT_EX_PROTOCOL  *Ex;
    EFI_KEY_DATA                       KeyData;

    if (EFI_ERROR (gBS->HandleProtocol (Handles[Index], &gEfiSimpleTextInputExProtocolGuid, (VOID **)&Ex))) {
      continue;
    }

    ZeroMem (&KeyData, sizeof (KeyData));
    if (!EFI_ERROR (Ex->ReadKeyStrokeEx (Ex, &KeyData)) &&
        ((KeyData.Key.ScanCode != 0) || (KeyData.Key.UnicodeChar != 0)))
    {
      *Key  = KeyData.Key;
      Found = TRUE;
    }
  }

  FreePool (Handles);
  return Found;
}

'''

anchor = "UINTN\nUniXNUMenuRun ("
if anchor not in text:
    raise SystemExit("Menu.c: UniXNUMenuRun anchor missing")
text = text.replace(anchor, poll_fn + anchor, 1)

# Poll on every timer tick, before the rotation logic.
tick_anchor = '''      if (!UserActive && (RotateMs > 0) && (Count > 1)) {'''
poll_block = '''      if (PollAnyKey (&Key)) {
        if (!UserActive) {
          UserActive  = TRUE;
          RemainingMs = -1;
          Selected    = Config->DefaultIndex;
        }

        {
          CHAR16  KeyLine[64];
          UnicodeSPrint (KeyLine, sizeof (KeyLine), L"key: scan=0x%02x uni=0x%04x", Key.ScanCode, Key.UnicodeChar);
          UniXNUUiDrawStatus (Ui, 2, KeyLine);
        }

        if ((Key.ScanCode == SCAN_UP) || (Key.UnicodeChar == L'k')) {
          Selected = (Selected + Count - 1) % Count;
        } else if ((Key.ScanCode == SCAN_DOWN) || (Key.UnicodeChar == L'j')) {
          Selected = (Selected + 1) % Count;
        } else if (Key.ScanCode == SCAN_HOME) {
          Selected = 0;
        } else if (Key.ScanCode == SCAN_END) {
          Selected = Count - 1;
        } else {
          Selected = Config->DefaultIndex;
          break;
        }
      }

''' + tick_anchor
if tick_anchor not in text:
    raise SystemExit("Menu.c: tick anchor missing")
text = text.replace(tick_anchor, poll_block, 1)

MENU.write_text(text, encoding="utf-8")
print("patched Menu.c")

# Footer: add input device counts.
MAIN = Path("/root/aloha/extras/UniXNUPkg/Library/UniXNULib/Main.c")
text = MAIN.read_text(encoding="utf-8")
if "tin %u" not in text:
    text = text.replace(
        'L"blk %u part %u fs %u efi %u cfg %u bs4k %u bs512 %u",',
        'L"blk %u part %u fs %u efi %u cfg %u bs4k %u bs512 %u tin %u tinex %u",',
        1,
    )
    text = text.replace(
        '''      (UINT32)Count4k,
      (UINT32)Count512
      );''',
        '''      (UINT32)Count4k,
      (UINT32)Count512,
      (UINT32)TinCount,
      (UINT32)TinExCount
      );''',
        1,
    )
    anchor = '''    UnicodeSPrint (
      Ui.Info,
      sizeof (Ui.Info),'''
    probe = '''    {
      EFI_HANDLE  *InHandles = NULL;
      UINTN       InCount = 0;
      if (!EFI_ERROR (gBS->LocateHandleBuffer (ByProtocol, &gEfiSimpleTextInProtocolGuid, NULL, &InCount, &InHandles))) {
        TinCount = InCount;
        FreePool (InHandles);
        InHandles = NULL;
      }
      if (!EFI_ERROR (gBS->LocateHandleBuffer (ByProtocol, &gEfiSimpleTextInputExProtocolGuid, NULL, &InCount, &InHandles))) {
        TinExCount = InCount;
        FreePool (InHandles);
      }
    }

''' + anchor
    if anchor not in text:
        raise SystemExit("Main.c: footer anchor missing")
    text = text.replace(anchor, probe, 1)
    text = text.replace(
        "    UINTN       Count512 = 0;",
        "    UINTN       Count512 = 0;\n    UINTN       TinCount = 0;\n    UINTN       TinExCount = 0;",
        1,
    )
    for inc in ('#include <Protocol/SimpleTextIn.h>', '#include <Protocol/SimpleTextInEx.h>'):
        if inc not in text:
            text = text.replace('#include "Internal.h"', '#include "Internal.h"\n' + inc, 1)
    MAIN.write_text(text, encoding="utf-8")
    print("patched Main.c")
