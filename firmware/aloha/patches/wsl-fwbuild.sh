#!/bin/bash
# Build the Aloha SurfaceDuo1 (lg-alpha, NOSB) firmware volume with plain BaseTools.
# stuart is skipped: its ext_dep downloads need GitHub release access, which the
# local proxy resets. BaseTools is built from MU_BASECORE source instead.
set -uo pipefail

W=/root/aloha/mu_aloha_platforms
BT=$W/MU_BASECORE/BaseTools
LOG=/root/aloha/fw-build.log

export WORKSPACE=$W
export EDK_TOOLS_PATH=$BT
export PACKAGES_PATH="$W/Platforms:$W/MU_BASECORE:$W/Common/MU:$W/Common/MU_OEM_SAMPLE:$W/Features/DFCI:$W/Features/CONFIG:$W/Binaries:$W/Silicon/QC/Sm8150:/root/aloha/extras:/root/aloha/extras/DarwinBootPkg"
export PATH="$BT/BinWrappers/PosixLike:$BT/Source/C/bin:$PATH"
export PYTHONPATH="$W/MU_BASECORE/BaseTools/Source/Python"
export SHARED_CRYPTO_PATH=/root/aloha/shared-crypto
export ONE_CRYPTO_PATH="$W/MU_BASECORE/CryptoPkg/Binaries/onecrypto-bin_extdep"

for tool in BrotliCompress LzmaCompress TianoCompress; do
    if [ ! -x "$BT/Source/C/bin/$tool" ]; then
        echo "building $tool"
        make -C "$BT/Source/C/$tool" -j 4 > "/root/aloha/$tool-build.log" 2>&1 || {
            echo "FAILED $tool"; tail -20 "/root/aloha/$tool-build.log"; exit 1; }
    fi
done

mkdir -p "$W/Conf"
for pair in "target.template:target.txt" "tools_def.template:tools_def.txt" "build_rule.template:build_rule.txt"; do
    src=${pair%%:*}; dst=${pair##*:}
    [ -f "$W/Conf/$dst" ] || cp "$BT/Conf/$src" "$W/Conf/$dst"
done

cd "$W" || exit 1
echo "build start $(date +%H:%M:%S)"
build -p Platforms/SurfaceDuo1Pkg/SurfaceDuo1NoSb.dsc -a AARCH64 -t CLANGDWARF \
      -b RELEASE -D TARGET_DEVICE=lg-alpha \
      -D SHARED_CRYPTO_PATH="$SHARED_CRYPTO_PATH" \
      -D CUSTOM_STACK_CHECK_LIB=STATIC \
      -D FDT=alpha.dtb \
      -n 8 > "$LOG" 2>&1
status=$?
echo "build exit=$status at $(date +%H:%M:%S)"
tail -25 "$LOG"
find "$W/Build" -name '*.fd' -printf '%p %s\n' 2>/dev/null
