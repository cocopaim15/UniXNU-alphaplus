#!/bin/bash
# Build payloads whose kernel resets right after a call to SYMBOL inside _arm_init.
set -eu

PATCHER="/mnt/f/ai共享/安卓安装苹果/build-alphaplus/patch-xnu-probe.py"
PACKER="/mnt/f/ai共享/安卓安装苹果/unixnu-alphaplus/firmware/aloha/patches/wsl-pack-probe.py"
BASE=/root/aloha/kernel/kernel-stripped.macho
WORK=/root/probe-work
OUT=/mnt/f/ai共享/安卓安装苹果/build-alphaplus

cd "$WORK"
for spec in "$@"; do
    # SPEC = [FUNC:]SYMBOL[:OCCURRENCE]; FUNC defaults to _arm_init
    rest=${spec#*:}
    case "$spec" in
        _*:*) func=${spec%%:*}; [ "${func#_}" = "${func}" ] && func=_arm_init ;;
        *)    func=_arm_init; rest=$spec ;;
    esac
    sym=${rest%%:*}
    occ=1
    case "$rest" in
        *:*) occ=${rest##*:} ;;
    esac
    short=${sym#_}
    [ "$occ" != 1 ] && short="$short$occ"
    [ "$func" != "_arm_init" ] && short="${func#_}-$short"
    cp "$BASE" "k-$short.macho"
    python3 "$PATCHER" "k-$short.macho" --no-bars --reset-delay 3 \
        --reset-after "$sym" --occurrence "$occ" --in "$func" | tail -1
    cp "k-$short.macho" "/root/aloha/kernel/kernel-stop-$short.macho"
    python3 "$PACKER" none --kernel "/root/aloha/kernel/kernel-stop-$short.macho" \
        --out "part4k-$short.img" | grep -E '^image '
done
