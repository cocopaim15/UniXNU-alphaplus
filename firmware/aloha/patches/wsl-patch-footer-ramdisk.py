"""Append the UniXNURamDiskDxe status variable to the UniXNU menu footer."""
from pathlib import Path

path = Path("/root/aloha/extras/UniXNUPkg/Library/UniXNULib/Main.c")
text = path.read_text(encoding="utf-8")
if "UnixnuRamDisk" in text:
    print("footer already patched")
    raise SystemExit(0)

anchor = '''      (UINT32)EfiCount,
      (UINT32)CfgCount
      );
  }
'''

addition = '''      (UINT32)EfiCount,
      (UINT32)CfgCount
      );

    {
      STATIC CONST EFI_GUID  RamDiskStatusGuid = {
        0x6b3f3a11, 0x2f7c, 0x4a55, { 0x9a, 0x11, 0x7d, 0x3c, 0x55, 0x66, 0x77, 0x88 }
      };
      CHAR16  RamStatus[96];
      UINTN   RamSize;

      RamSize = sizeof (RamStatus) - sizeof (CHAR16);
      ZeroMem (RamStatus, sizeof (RamStatus));
      if (!EFI_ERROR (gRT->GetVariable (
                            L"UnixnuRamDisk",
                            (EFI_GUID *)&RamDiskStatusGuid,
                            NULL,
                            &RamSize,
                            RamStatus
                            )))
      {
        RamStatus[RamSize / sizeof (CHAR16)] = L'\\0';
        StrCatS (Ui.Info, ARRAY_SIZE (Ui.Info), L"  ");
        StrCatS (Ui.Info, ARRAY_SIZE (Ui.Info), RamStatus);
      }
    }
  }
'''

if anchor not in text:
    raise SystemExit("footer anchor missing")
text = text.replace(anchor, addition, 1)
path.write_text(text, encoding="utf-8")
print("patched", path)
