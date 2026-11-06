"""Make UniXNURamDiskDxe report where initrd discovery stopped.

The driver has no console of its own; it writes a one-line status into a UEFI
variable that the UniXNU menu footer prints.
"""
from pathlib import Path

DRV = Path("/root/aloha/extras/UniXNUPkg/Driver/UniXNURamDiskDxe/UniXNURamDiskDxe.c")
text = DRV.read_text(encoding="utf-8")
if "UnixnuRamDisk" in text:
    print("driver already patched")
    raise SystemExit(0)

helper = '''
// Diagnostic channel: the menu footer reads this variable and prints it.
STATIC CONST EFI_GUID  mStatusGuid = {
  0x6b3f3a11, 0x2f7c, 0x4a55, { 0x9a, 0x11, 0x7d, 0x3c, 0x55, 0x66, 0x77, 0x88 }
};

STATIC
VOID
SetStatus (
  IN CONST CHAR16  *Text
  )
{
  gRT->SetVariable (
         L"UnixnuRamDisk",
         (EFI_GUID *)&mStatusGuid,
         EFI_VARIABLE_BOOT_SERVICE_ACCESS | EFI_VARIABLE_NON_VOLATILE,
         StrSize (Text),
         (VOID *)Text
         );
}

'''

anchor = "STATIC CONST EFI_GUID mEntryArgHobGuid = {"
if anchor not in text:
    raise SystemExit("entry-arg GUID anchor missing")
text = text.replace(anchor, helper + anchor, 1)

if "#include <Library/UefiRuntimeServicesTableLib.h>" not in text:
    text = text.replace(
        "#include <Library/UefiBootServicesTableLib.h>",
        "#include <Library/UefiBootServicesTableLib.h>\n#include <Library/UefiRuntimeServicesTableLib.h>",
        1,
    )

replacements = [
    (
        '''    DEBUG ((DEBUG_ERROR, "UNIXNURAMDISK: no entry argument HOB\\n"));
    return EFI_SUCCESS;''',
        '''    DEBUG ((DEBUG_ERROR, "UNIXNURAMDISK: no entry argument HOB\\n"));
    SetStatus (L"rd: no entry-arg HOB");
    return EFI_SUCCESS;''',
    ),
    (
        '''  if (GET_GUID_HOB_DATA_SIZE (Hob) < sizeof (UINT64)) {
    return EFI_COMPROMISED_DATA;''',
        '''  if (GET_GUID_HOB_DATA_SIZE (Hob) < sizeof (UINT64)) {
    SetStatus (L"rd: HOB too small");
    return EFI_COMPROMISED_DATA;''',
    ),
    (
        '''  Dtb = ReadUnaligned64 ((CONST UINT64 *)GET_GUID_HOB_DATA (Hob));
  if ((Dtb == 0) || ((Dtb & 3) != 0) || (FdtCheckHeader ((VOID *)(UINTN)Dtb) != 0)) {
    DEBUG ((DEBUG_ERROR, "UNIXNURAMDISK: x0 0x%lx is not a device tree\\n", Dtb));
    return EFI_SUCCESS;
  }''',
        '''  Dtb = ReadUnaligned64 ((CONST UINT64 *)GET_GUID_HOB_DATA (Hob));
  if ((Dtb == 0) || ((Dtb & 3) != 0) || (FdtCheckHeader ((VOID *)(UINTN)Dtb) != 0)) {
    CHAR16  Why[64];
    UnicodeSPrint (Why, sizeof (Why), L"rd: x0=0x%lx not a dtb", Dtb);
    SetStatus (Why);
    DEBUG ((DEBUG_ERROR, "UNIXNURAMDISK: x0 0x%lx is not a device tree\\n", Dtb));
    return EFI_SUCCESS;
  }''',
    ),
    (
        '''  Chosen = FdtPathOffset (Fdt, "/chosen");
  if (Chosen < 0) {
    DEBUG ((DEBUG_ERROR, "UNIXNURAMDISK: no /chosen\\n"));
    return;''',
        '''  Chosen = FdtPathOffset (Fdt, "/chosen");
  if (Chosen < 0) {
    SetStatus (L"rd: dtb ok, no /chosen");
    DEBUG ((DEBUG_ERROR, "UNIXNURAMDISK: no /chosen\\n"));
    return;''',
    ),
    (
        '''      ((StartLength != 4) && (StartLength != 8)) || ((EndLength != 4) && (EndLength != 8)))
  {
    DEBUG ((DEBUG_ERROR, "UNIXNURAMDISK: no initrd in /chosen\\n"));
    return;''',
        '''      ((StartLength != 4) && (StartLength != 8)) || ((EndLength != 4) && (EndLength != 8)))
  {
    SetStatus (L"rd: /chosen has no initrd props");
    DEBUG ((DEBUG_ERROR, "UNIXNURAMDISK: no initrd in /chosen\\n"));
    return;''',
    ),
    (
        '''  DEBUG ((DEBUG_ERROR, "UNIXNURAMDISK: initrd block device 0x%lx size 0x%lx %r\\n", Start, End - Start, Status));''',
        '''  {
    CHAR16  Done[72];
    UnicodeSPrint (Done, sizeof (Done), L"rd: 0x%lx+0x%lx %r", Start, End - Start, Status);
    SetStatus (Done);
  }
  DEBUG ((DEBUG_ERROR, "UNIXNURAMDISK: initrd block device 0x%lx size 0x%lx %r\\n", Start, End - Start, Status));''',
    ),
]

for old, new in replacements:
    if old not in text:
        raise SystemExit(f"anchor missing:\n{old[:120]}")
    text = text.replace(old, new, 1)

DRV.write_text(text, encoding="utf-8")
print("patched", DRV)
