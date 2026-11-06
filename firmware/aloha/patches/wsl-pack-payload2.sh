#!/bin/bash
# Rebuild the 4096-byte-sector payload with an "Erase boot_a" escape action and
# pack the boot image carrying the current firmware.
set -euo pipefail

cd /root/aloha/boot

cat > unixnu2.toml <<'EOF'
version = 1

[boot]
timeout = 20
default = "erase"

[kits]
autoload = false

[[entry]]
id = "xnu"
title = "LG G8 - XNU"
type = "xnu"
path = "Payloads/kernel.macho"
args = "debug=0xc serial=3 cpus=8 keepsyms=1 rd=ufsroot0 wdt=-1"

[[entry]]
id = "erase"
title = "Erase boot_a (fastboot)"
type = "action"
action = "erase-boot"
EOF

rm -f part4k2.img
dd if=/dev/zero of=part4k2.img bs=1M count=64 status=none
mkfs.vfat -F 16 -S 4096 -s 1 -n ALPHASP part4k2.img >/dev/null
mmd -i part4k2.img ::/EFI ::/EFI/UniXNU ::/EFI/UniXNU/Payloads
mcopy -i part4k2.img unixnu2.toml ::/EFI/UniXNU/unixnu.toml
mcopy -i part4k2.img /root/aloha/kernel/kernel-stripped.macho ::/EFI/UniXNU/Payloads/kernel.macho
mcopy -i part4k2.img /root/aloha/uplink/out.adt ::/EFI/UniXNU/Payloads/kernel.macho.adt

python3 - <<'PY'
import gzip
from pathlib import Path
shim = Path('/root/aloha/mu_aloha_platforms/BootShim/BootShim.bin').read_bytes()
fd = Path('/root/aloha/mu_aloha_platforms/Build/SurfaceDuo1Pkg/RELEASE_CLANGDWARF/FV/SM8150_EFI.fd').read_bytes()
dtb = Path('/root/aloha/mu_aloha_platforms/Platforms/SurfaceDuo1Pkg/Device/lg-alpha/DeviceTreeBlob/Android/android-alpha.dtb').read_bytes()
Path('/root/aloha/boot/kernel-mark.bin').write_bytes(gzip.compress(shim + fd, 9) + dtb)
print('kernel', Path('/root/aloha/boot/kernel-mark.bin').stat().st_size)
PY

python3 /root/aloha/mu_aloha_platforms/PythonLibs/mkbootimg.py \
    --header_version 0 --pagesize 4096 --base 0x0 \
    --kernel_offset 0x8000 --ramdisk_offset 0x81000000 --tags_offset 0x100 \
    --os_version 11.0.0 --os_patch_level 2023-04-01 \
    --kernel kernel-mark.bin --ramdisk /root/aloha/mu_aloha_platforms/PythonLibs/emptyramdisk \
    -o boot-mark.img

cp boot-mark.img part4k2.img "/mnt/f/ai共享/安卓安装苹果/build-alphaplus/"
ls -l boot-mark.img part4k2.img
