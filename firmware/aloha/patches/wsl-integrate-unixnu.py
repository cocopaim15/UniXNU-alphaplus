"""Add UniXNU's firmware pieces to the Aloha SurfaceDuo1 platform.

* DSC: build UniXNURamDiskDxe, UniXNUDxe, the UniXNU application and DarwinBoot
* FDF: put all four in the DXE firmware volume
* PrePi: hand the incoming device tree pointer to DXE, so the payload ramdisk
  (the Android initrd, patched into the tree by the bootloader) can be found
"""
from pathlib import Path

ROOT = Path("/root/aloha/mu_aloha_platforms")
DSC = ROOT / "Platforms/SurfaceDuo1Pkg/SurfaceDuo1NoSb.dsc"
DXE_INC = ROOT / "Platforms/SurfaceDuo1Pkg/Device/lg-alpha/DXE.inc"
PREPI_C = ROOT / "Platforms/AndromedaPkg/PrePi/PrePi.c"
PREPI_S = ROOT / "Platforms/AndromedaPkg/PrePi/AArch64/ModuleEntryPoint.S"

DSC_ADDITION = """
[Components]
  UniXNUPkg/Driver/UniXNURamDiskDxe/UniXNURamDiskDxe.inf
  UniXNUPkg/Driver/UniXNUDxe/UniXNUDxe.inf
  UniXNUPkg/Application/UniXNU/UniXNU.inf
  DarwinBootPkg/Driver/DarwinBoot.inf

[LibraryClasses.common.UEFI_APPLICATION, LibraryClasses.common.DXE_DRIVER]
  UniXNULib|UniXNUPkg/Library/UniXNULib/UniXNULib.inf

[LibraryClasses.common.DXE_DRIVER]
  HobLib|MdePkg/Library/DxeHobLib/DxeHobLib.inf

[LibraryClasses]
  FdtLib|MdePkg/Library/BaseFdtLib/BaseFdtLib.inf
"""

FDF_ADDITION = """
# UniXNU: payload volume from the Android initrd, boot manager, XNU loader
INF UniXNUPkg/Driver/UniXNURamDiskDxe/UniXNURamDiskDxe.inf
INF UniXNUPkg/Driver/UniXNUDxe/UniXNUDxe.inf
INF UniXNUPkg/Application/UniXNU/UniXNU.inf
INF DarwinBootPkg/Driver/DarwinBoot.inf
"""

HOB_DECL = """STATIC CONST EFI_GUID  mEntryArgHobGuid = {
  0xDAEE82E6, 0x8090, 0x4E72, { 0xBF, 0xB9, 0x78, 0xC1, 0x3C, 0xD4, 0xE3, 0x59 }
};

// Incoming x0 from the bootloader: the device tree the kernel would have used.
UINT64  mBootDtb = 0;

"""

HOB_CODE = """  // Tell DXE where the bootloader's device tree lives (UniXNURamDiskDxe reads it).
  if (mBootDtb != 0) {
    BuildGuidDataHob (&mEntryArgHobGuid, &mBootDtb, sizeof (mBootDtb));
  }

"""


def add_dsc():
    text = DSC.read_text(encoding="utf-8")
    if "UniXNUPkg/Driver/UniXNURamDiskDxe" in text:
        print("DSC already integrated")
        return
    DSC.write_text(text + DSC_ADDITION, encoding="utf-8")
    print("DSC updated")


def add_fdf():
    text = DXE_INC.read_text(encoding="utf-8")
    if "UniXNUPkg/Driver/UniXNURamDiskDxe" in text:
        print("FDF already integrated")
        return
    DXE_INC.write_text(text + FDF_ADDITION, encoding="utf-8")
    print("FDF updated")


def patch_prepi():
    text = PREPI_C.read_text(encoding="utf-8")
    if "mBootDtb" not in text:
        marker = "UINT64  mSystemMemoryEnd = FixedPcdGet64 (PcdSystemMemoryBase) +\n                           FixedPcdGet64 (PcdSystemMemorySize) - 1;\n"
        if marker not in text:
            raise SystemExit("PrePi.c: mSystemMemoryEnd marker not found")
        text = text.replace(marker, marker + "\n" + HOB_DECL, 1)
        anchor = "  BuildCpuHob (ArmGetPhysicalAddressBits (), PcdGet8 (PcdPrePiCpuIoSize));\n"
        if anchor not in text:
            raise SystemExit("PrePi.c: BuildCpuHob anchor not found")
        text = text.replace(anchor, anchor + "\n" + HOB_CODE, 1)
        PREPI_C.write_text(text, encoding="utf-8")
        print("PrePi.c updated")
    else:
        print("PrePi.c already patched")

    asm = PREPI_S.read_text(encoding="utf-8")
    if "mBootDtb" not in asm:
        anchor = "_PrepareArguments:\n  mov   x0, x10\n"
        if anchor not in asm:
            raise SystemExit("ModuleEntryPoint.S: _PrepareArguments anchor not found")
        replacement = (
            "_PrepareArguments:\n"
            "  // Keep the bootloader's device tree pointer for the DXE phase\n"
            "  ldr   x5, =ASM_PFX(mBootDtb)\n"
            "  str   x10, [x5]\n"
            "  mov   x0, x10\n"
        )
        asm = asm.replace(anchor, replacement, 1)
        PREPI_S.write_text(asm, encoding="utf-8")
        print("ModuleEntryPoint.S updated")
    else:
        print("ModuleEntryPoint.S already patched")


add_dsc()
add_fdf()
patch_prepi()
