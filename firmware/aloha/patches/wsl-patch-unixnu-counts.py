"""Show block / partition / file-system counts in the UniXNU menu footer.

Without a serial console the menu is the only output; these three numbers say
whether UFS came up (blk), whether partitions were published (part), and
whether the FAT driver bound anywhere (fs).

The C replacement text is written with a leading "|" per line so this file does
not have to embed bare plus signs; the marker is stripped before use.
"""
from pathlib import Path

path = Path("/root/aloha/extras/UniXNUPkg/Library/UniXNULib/Main.c")
text = path.read_text(encoding="utf-8")
if "blk %u" in text:
    print("already patched")
    raise SystemExit(0)

OLD = """  UnicodeSPrint (
    Ui.Info,
    sizeof (Ui.Info),
    L"drivers %u loaded / %u failed    kits %u    acpi %u",
    (UINT32)Stats.DriversLoaded,
    (UINT32)Stats.DriversFailed,
    (UINT32)Config.KitsLoaded,
    (UINT32)Stats.AcpiInstalled
    );"""

NEW_RAW = """
|  {
|    EFI_HANDLE  *Probe = NULL;
|    UINTN       ProbeCount = 0;
|    UINTN       BlkCount = 0;
|    UINTN       PartCount = 0;
|    UINTN       FsCount = 0;
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
|      FreePool (Probe);
|      Probe = NULL;
|    }
|
|    UnicodeSPrint (
|      Ui.Info,
|      sizeof (Ui.Info),
|      L"drivers %u/%u  kits %u  acpi %u  blk %u part %u fs %u",
|      (UINT32)Stats.DriversLoaded,
|      (UINT32)Stats.DriversFailed,
|      (UINT32)Config.KitsLoaded,
|      (UINT32)Stats.AcpiInstalled,
|      (UINT32)BlkCount,
|      (UINT32)PartCount,
|      (UINT32)FsCount
|      );
|  }
"""

if OLD not in text:
    raise SystemExit("Main.c: UnicodeSPrint block not found")

NEW = "\n".join(
    line[1:] if line.startswith("|") else line
    for line in NEW_RAW.splitlines()
).strip("\n")

text = text.replace(OLD, NEW, 1)

includes = (
    "#include <Protocol/BlockIo.h>\n"
    "#include <Protocol/PartitionInfo.h>\n"
    "#include <Protocol/SimpleFileSystem.h>\n"
)
if "Protocol/PartitionInfo.h" not in text:
    anchor = '#include "Internal.h"\n'
    text = text.replace(anchor, anchor + includes, 1)

path.write_text(text, encoding="utf-8")
print("patched", path)
