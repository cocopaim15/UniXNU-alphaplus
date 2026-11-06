"""Show the last key the menu received, and count input devices.

The phone's buttons come from Qcom's ButtonsDxe; knowing the scan codes it
emits is the only way to map them onto the menu actions.
"""
from pathlib import Path

BASE = Path("/root/aloha/extras/UniXNUPkg/Library/UniXNULib")

# ---------------------------------------------------------------- Menu.c: last key
menu = BASE / "Menu.c"
text = menu.read_text(encoding="utf-8")
if "key: scan=" not in text:
    anchor = '''      if (!UserActive) {
        //
        // The first key takes over: no more countdown or rotation, and the
        // highlight returns to the default before the key applies.
        //'''
    insert = '''      {
        CHAR16  KeyLine[64];
        UnicodeSPrint (
          KeyLine,
          sizeof (KeyLine),
          L"key: scan=0x%02x uni=0x%04x",
          Key.ScanCode,
          Key.UnicodeChar
          );
        UniXNUUiDrawStatus (Ui, 2, KeyLine);
      }

''' + anchor
    if anchor not in text:
        raise SystemExit("Menu.c: key anchor missing")
    text = text.replace(anchor, insert, 1)
    menu.write_text(text, encoding="utf-8")
    print("patched Menu.c")

# ---------------------------------------------------------------- Main.c: input counts
main = BASE / "Main.c"
text = main.read_text(encoding="utf-8")
if "tinex" not in text:
    text = text.replace(
        'L"blk %u part %u fs %u efi %u cfg %u",',
        'L"blk %u part %u fs %u efi %u cfg %u tin %u tinex %u",',
        1,
    )
    text = text.replace(
        '''      (UINT32)EfiCount,
      (UINT32)CfgCount
      );''',
        '''      (UINT32)EfiCount,
      (UINT32)CfgCount,
      (UINT32)TinCount,
      (UINT32)TinExCount
      );''',
        1,
    )
    anchor = '''    UnicodeSPrint (
      Ui.Info,
      sizeof (Ui.Info),'''
    insert = '''    {
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
    text = text.replace(anchor, insert, 1)
    text = text.replace(
        "    UINTN       ProbeIndex;",
        "    UINTN       ProbeIndex;\n    UINTN       TinCount = 0;\n    UINTN       TinExCount = 0;",
        1,
    )
    if "Protocol/SimpleTextIn.h" not in text:
        text = text.replace(
            "#include <Protocol/BlockIo.h>",
            "#include <Protocol/BlockIo.h>\n#include <Protocol/SimpleTextIn.h>\n#include <Protocol/SimpleTextInEx.h>",
            1,
        )
    main.write_text(text, encoding="utf-8")
    print("patched Main.c")
