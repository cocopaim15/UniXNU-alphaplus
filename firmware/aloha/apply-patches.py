#!/usr/bin/env python3
"""Turn a pristine Project-Aloha mu_aloha_platforms checkout into a tree that
builds the alphaplus firmware volume with plain EDK2 BaseTools, and that carries
UniXNU's boot chain.

Usage:
    python3 apply-patches.py /path/to/mu_aloha_platforms

Every edit prints one line and is idempotent. The patches fall into three groups:

  build plumbing  the checkout normally builds through stuart, which downloads a
                  255 MB crypto bundle from GitHub releases. Here BaseTools is
                  built from source, the crypto driver comes from Aloha's own
                  released FD, and the library classes point at Mu's
                  protocol-based crypto clients.

  toolchain drift clang 18 and the current Mu sources reject a few constructs
                  that Aloha's CI accepted (K&R zlib, duplicate exception
                  handlers, stack cookies in SEC, the objcopy placeholder).

  UniXNU        the four firmware pieces plus the device-tree handoff that
                  lets UniXNURamDiskDxe find the Android initrd payload.
"""
import sys
from pathlib import Path

ROOT = Path(sys.argv[1] if len(sys.argv) > 1 else ".").resolve()


def patch(rel, replacements, marker=None):
    """Apply (old, new) replacements to one file, asserting each anchor exists."""
    path = ROOT / rel
    if not path.is_file():
        raise SystemExit(f"missing {path}")
    text = path.read_text(encoding="utf-8")
    if marker and marker in text:
        print(f"skip    {rel}")
        return
    for old, new in replacements:
        if old not in text:
            raise SystemExit(f"{rel}: anchor not found:\n{old[:120]}")
        text = text.replace(old, new, 1)
    path.write_text(text, encoding="utf-8")
    print(f"patched {rel}")


def append(rel, text, marker):
    path = ROOT / rel
    body = path.read_text(encoding="utf-8")
    if marker in body:
        print(f"skip    {rel}")
        return
    path.write_text(body + text, encoding="utf-8")
    print(f"patched {rel} (append)")


# --------------------------------------------------------------------------
# toolchain drift
# --------------------------------------------------------------------------

patch("Platforms/QcomModulePkg/Library/zlib/zlib.inf", [(
    "[BuildOptions.AARCH64]\n",
    "[BuildOptions.AARCH64]\n"
    "  # zlib still uses K&R definitions; clang 18 promotes the warning to an error\n"
    "  *_*_*_CC_FLAGS = -Wno-deprecated-non-prototype\n",
)], marker="deprecated-non-prototype")

patch("Platforms/AndromedaPkg/Andromeda.dsc.inc", [
    # DxeImageVerificationLib pulls RealTimeClockLib -> UefiRuntimeLib into a
    # DXE_DRIVER, which EDK2 rejects. No Secure Boot in this build.
    ("""  MdeModulePkg/Universal/SecurityStubDxe/SecurityStubDxe.inf {
    <LibraryClasses>
      NULL|SecurityPkg/Library/DxeImageVerificationLib/DxeImageVerificationLib.inf
  }""",
     "  MdeModulePkg/Universal/SecurityStubDxe/SecurityStubDxe.inf"),
    # The NULL exception handler defines the same symbols as ArmPkg's handler.
    ("""  ArmPkg/Drivers/CpuDxe/CpuDxe.inf {
    <LibraryClasses>
    NULL|MsCorePkg/Library/MemoryProtectionExceptionHandlerLib/MemoryProtectionExceptionHandlerLib.inf
  }""",
     "  ArmPkg/Drivers/CpuDxe/CpuDxe.inf"),
], marker="DxeImageVerificationLib")

# NetworkPkg is not in the FV (the FDF comments it out) but TlsDxe is still
# built and is the only module that needs a real crypto library.
text = (ROOT / "Platforms/AndromedaPkg/Andromeda.dsc.inc").read_text(encoding="utf-8")
if "\n  NetworkPkg/TlsDxe/TlsDxe.inf\n" in text:
    lines = text.splitlines(keepends=True)
    text = "".join("#" + line if line.startswith("  NetworkPkg/") else line for line in lines)
    (ROOT / "Platforms/AndromedaPkg/Andromeda.dsc.inc").write_text(text, encoding="utf-8")
    print("patched Platform/AndromedaPkg/Andromeda.dsc.inc (NetworkPkg out)")
else:
    print("skip    Platform/AndromedaPkg/Andromeda.dsc.inc (NetworkPkg)")

# SEC links with LTO, which re-applies -fstack-protector at link time, while
# MdeLibs maps StackCheckLibNull for SEC. Provide the cookie symbols locally.
sec_cookie = ROOT / "Platforms/AndromedaPkg/PrePi/SecStackCheck.c"
if not sec_cookie.is_file():
    sec_cookie.write_text(
        """/** @file
  Stack cookie symbols for the SEC phase (see apply-patches.py).
**/
#include <Uefi.h>

UINT64  __stack_chk_guard = 0x00000AFF00000AFFULL;

VOID
__stack_chk_fail (
  VOID
  )
{
  for ( ; ; ) {
  }
}
""", encoding="utf-8")
    print(f"created {sec_cookie.relative_to(ROOT)}")

patch("Platforms/AndromedaPkg/PrePi/PeiUniCore.inf", [
    ("[Sources]\n", "[Sources]\n  SecStackCheck.c\n"),
], marker="SecStackCheck.c")

append("Platforms/AndromedaPkg/PrePi/PeiUniCore.inf", """
[BuildOptions.AARCH64]
  *_*_*_CC_FLAGS = -fno-stack-protector
  *_*_*_DLINK_FLAGS = -fno-stack-protector
""", marker="-fno-stack-protector")

# Mu sets OBJCOPY_FLAGS to a human readable placeholder ("objcopy not needed
# for"); the SEC/PEIM rule still runs objcopy, so drop that line locally.
rule = ROOT / "Conf/build_rule.txt"
if rule.is_file():
    lines = rule.read_text(encoding="utf-8").splitlines(keepends=True)
    kept, dropped, inside = [], 0, False
    for line in lines:
        if line.strip().startswith("["):
            inside = line.strip().startswith("[Static-Library-File.SEC")
        if inside and "OBJCOPY_FLAGS" in line:
            dropped += 1
            continue
        kept.append(line)
    if dropped:
        rule.write_text("".join(kept), encoding="utf-8")
        print(f"patched Conf/build_rule.txt ({dropped} objcopy line)")
    else:
        print("skip    Conf/build_rule.txt")

# --------------------------------------------------------------------------
# build plumbing: crypto library classes point at the protocol clients
# --------------------------------------------------------------------------

append("Platforms/SurfaceDuo1Pkg/SurfaceDuo1NoSb.dsc", """
[BuildOptions]
  *:*_*_AARCH64_CC_FLAGS = -Wno-deprecated-non-prototype

[LibraryClasses.common.DXE_DRIVER, LibraryClasses.common.UEFI_DRIVER, LibraryClasses.common.UEFI_APPLICATION, LibraryClasses.common.DXE_CORE]
  BaseCryptLib|CryptoPkg/Library/BaseCryptLibOnProtocolPpi/DxeCryptLib.inf
  TlsLib|CryptoPkg/Library/BaseCryptLibOnProtocolPpi/DxeCryptLib.inf

[LibraryClasses.common.DXE_RUNTIME_DRIVER]
  BaseCryptLib|CryptoPkg/Library/BaseCryptLibOnProtocolPpi/RuntimeDxeCryptLib.inf
  TlsLib|CryptoPkg/Library/BaseCryptLibOnProtocolPpi/RuntimeDxeCryptLib.inf

[LibraryClasses.common.UEFI_APPLICATION]
  StackCheckLib|MdePkg/Library/StackCheckLib/StackCheckLib.inf

[LibraryClasses.common.SEC]
  StackCheckLib|MdePkg/Library/StackCheckLib/StackCheckLib.inf
""", marker="BaseCryptLibOnProtocolPpi")

# --------------------------------------------------------------------------
# UniXNU: components, FDF entries and the device-tree handoff
# --------------------------------------------------------------------------

append("Platforms/SurfaceDuo1Pkg/SurfaceDuo1NoSb.dsc", """
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
""", marker="UniXNUPkg/Driver/UniXNURamDiskDxe")

append("Platforms/SurfaceDuo1Pkg/Device/lg-alpha/DXE.inc", """
# UniXNU: payload volume from the Android initrd, boot manager, XNU loader
INF UniXNUPkg/Driver/UniXNURamDiskDxe/UniXNURamDiskDxe.inf
INF UniXNUPkg/Driver/UniXNUDxe/UniXNUDxe.inf
INF UniXNUPkg/Application/UniXNU/UniXNU.inf
INF DarwinBootPkg/Driver/DarwinBoot.inf
""", marker="UniXNUPkg/Driver/UniXNURamDiskDxe")

patch("Platforms/AndromedaPkg/PrePi/PrePi.c", [
    ("""UINT64  mSystemMemoryEnd = FixedPcdGet64 (PcdSystemMemoryBase) +
                           FixedPcdGet64 (PcdSystemMemorySize) - 1;
""",
     """UINT64  mSystemMemoryEnd = FixedPcdGet64 (PcdSystemMemoryBase) +
                           FixedPcdGet64 (PcdSystemMemorySize) - 1;

// The bootloader hands the firmware a device tree in x0. Mu-Silicium's SEC
// publishes it as a HOB; this platform does the same so DXE can find the
// initrd the bootloader patched into the tree.
STATIC CONST EFI_GUID  mEntryArgHobGuid = {
  0xDAEE82E6, 0x8090, 0x4E72, { 0xBF, 0xB9, 0x78, 0xC1, 0x3C, 0xD4, 0xE3, 0x59 }
};

UINT64  mBootDtb = 0;
"""),
    ("  BuildCpuHob (ArmGetPhysicalAddressBits (), PcdGet8 (PcdPrePiCpuIoSize));\n",
     "  BuildCpuHob (ArmGetPhysicalAddressBits (), PcdGet8 (PcdPrePiCpuIoSize));\n"
     "\n"
     "  if (mBootDtb != 0) {\n"
     "    BuildGuidDataHob (&mEntryArgHobGuid, &mBootDtb, sizeof (mBootDtb));\n"
     "  }\n"),
], marker="mBootDtb")

patch("Platforms/AndromedaPkg/PrePi/AArch64/ModuleEntryPoint.S", [
    ("_PrepareArguments:\n  mov   x0, x10\n",
     "_PrepareArguments:\n"
     "  // Keep the bootloader's device tree pointer (x0) for the DXE phase\n"
     "  ldr   x5, =ASM_PFX(mBootDtb)\n"
     "  str   x10, [x5]\n"
     "  mov   x0, x10\n"),
], marker="mBootDtb")

print("done")
