#!/bin/bash
# 4096-byte-sector FAT16 payload (matches the UFS logical block size) and a
# boot image carrying it as the ramdisk.
set -euo pipefail

cd /root/aloha/boot

rm -f part4k.img
dd if=/dev/zero of=part4k.img bs=1M count=64 status=none
mkfs.vfat -F 16 -S 4096 -s 1 -n ALPHASP part4k.img >/dev/null
mmd -i part4k.img ::/EFI ::/EFI/UniXNU ::/EFI/UniXNU/Payloads
mcopy -i part4k.img unixnu.toml ::/EFI/UniXNU/unixnu.toml
mcopy -i part4k.img /root/aloha/kernel/kernel-stripped.macho ::/EFI/UniXNU/Payloads/kernel.macho
mcopy -i part4k.img /root/aloha/uplink/out.adt ::/EFI/UniXNU/Payloads/kernel.macho.adt
mdir -i part4k.img ::/EFI/UniXNU/Payloads | tail -4

python3 - <<'PY'
import gzip
from pathlib import Path
shim = Path('/root/aloha/mu_aloha_platforms/BootShim/BootShim.bin').read_bytes()
fd = Path('/root/aloha/mu_aloha_platforms/Build/SurfaceDuo1Pkg/RELEASE_CLANGDWARF/FV/SM8150_EFI.fd').read_bytes()
dtb = Path('/root/aloha/mu_aloha_platforms/Platforms/SurfaceDuo1Pkg/Device/lg-alpha/DeviceTreeBlob/Android/android-alpha.dtb').read_bytes()
Path('/root/aloha/boot/kernel-4k.bin').write_bytes(gzip.compress(shim + fd, 9) + dtb)
print('kernel', Path('/root/aloha/boot/kernel-4k.bin').stat().st_size)
PY

python3 /root/aloha/mu_aloha_platforms/PythonLibs/mkbootimg.py \
    --header_version 0 --pagesize 4096 --base 0x0 \
    --kernel_offset 0x8000 --ramdisk_offset 0x81000000 --tags_offset 0x100 \
    --os_version 11.0.0 --os_patch_level 2023-04-01 \
    --kernel kernel-4k.bin --ramdisk part4k.img \
    -o boot-4k.img

cp part4k.img boot-4k.img "/mnt/f/ai共享/安卓安装苹果/build-alphaplus/"
ls -l boot-4k.img part4k.img
