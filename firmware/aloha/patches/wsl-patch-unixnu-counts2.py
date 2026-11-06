"""Extend the UniXNU footer probe: also count volumes that have \\EFI and
volumes that actually contain the configured unixnu.toml.

Replaces the first probe block (inserted by wsl-patch-unixnu-counts.py).
"""
from pathlib import Path

path = Path("/root/aloha/extras/UniXNUPkg/Library/UniXNULib/Main.c")
text = path.read_text(encoding="utf-8")

START = "  {\n    EFI_HANDLE  *Probe = NULL;"
END = "\n  Countdown = TRUE;"

if START not in text:
    raise SystemExit("probe block not found")
begin = text.index(START)
finish = text.index(END, begin)

RAW = """
|  {
|    EFI_HANDLE  *Probe = NULL;
|    UINTN       ProbeCount = 0;
|    UINTN       BlkCount = 0;
|    UINTN       PartCount = 0;
|    UINTN       FsCount = 0;
|    UINTN       EfiCount = 0;
|    UINTN       CfgCount = 0;
|    UINTN       ProbeIndex;
|
|    if (!EFI_ERROR (gBS->LocateHandleBuffer (ByProtocol, &gEfiBlockIoProtocolGuid, NULL, &ProbeCount, &Probe))) {
|      BlkCount = ProbeCount;
|      FreePool (Probe);
|      Probe = NULL;
|    }
|    if (!EFI_ERROR (gBS->LocateHandleBuffer (ByProtocol, &gEfiPartitionInfoProtocolGuid, NULL, &ProbeCount, &Probe))) {
|      PartCount = ProbeCount;
|      FreePool (Probe);
|      Probe = NULL;
|    }
|    if (!EFI_ERROR (gBS->LocateHandleBuffer (ByProtocol, &gEfiSimpleFileSystemProtocolGuid, NULL, &ProbeCount, &Probe))) {
|      FsCount = ProbeCount;
|      for (ProbeIndex = 0; ProbeIndex < ProbeCount; ProbeIndex++) {
|        if (UniXNUFileExists (Probe[ProbeIndex], L"\\\\EFI")) {
|          EfiCount++;
|        }
|        if (UniXNUFileExists (Probe[ProbeIndex], (CONST CHAR16 *)PcdGetPtr (PcdUniXNUConfigPath))) {
|          CfgCount++;
|        }
|      }
|      FreePool (Probe);
|      Probe = NULL;
|    }
|
|    UnicodeSPrint (
|      Ui.Info,
|      sizeof (Ui.Info),
|      L"blk %u part %u fs %u efi %u cfg %u",
|      (UINT32)BlkCount,
|      (UINT32)PartCount,
|      (UINT32)FsCount,
|      (UINT32)EfiCount,
|      (UINT32)CfgCount
|      );
|  }
"""

new = "\n".join(line[1:] if line.startswith("|") else line for line in RAW.splitlines()).strip("\n")
text = text[:begin] + new + text[finish:]
path.write_text(text, encoding="utf-8")
print("patched", path)
