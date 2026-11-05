#!/usr/bin/env python3
"""Per-device hardware profiles for the SWEET XNU port.

One entry per phone: everything that changes when the same kernel/shim is
brought up on a different Qualcomm board. The values are the ones the early
boot path reads (see NOTES.md); they come from the live FDT / stock DTB of
the device (reserved-memory, /memory, /soc MMIO nodes) unless noted.

`sweet` values are the ones the port was developed on. `guacamole` is the
OnePlus 7 Pro port: every number must be verified against the phone's own
stock DTB once it is dumped (see GUACAMOLE.md); entries marked
"verify" are from public kernel sources and have not been confirmed on
hardware.

Used by tools/mkadt.py (ADT) and mirrored by shim/boards/*.h (framebuffer,
GIC, probe addresses). Keep the two in sync when changing a value.
"""

DEVICES = {
    'sweet': {
        # Redmi Note 10 Pro (SM7150 / Snapdragon 732G)
        'name': 'Redmi Note 10 Pro (sweet, SM7150)',
        'board_compat': 'xiaomi,sweet',
        'soc_compat': 'qcom,sm7150',
        # Kernel-managed RAM below 4 GiB: above every Qualcomm XPU carve-out
        # (live FDT /memory <0x80000000 2G>, <0x1_00000000 0xfcc00000>; the
        # fixed carve-outs are in the low bank, dynamic pools below 4G).
        'phys_base': 0xb0000000,
        'mem_size': 0x4d000000,
        # --highmem: the whole upper DDR bank (phone default).
        'high_phys_base': 0x100000000,
        'high_mem_size': 0xfcc00000,
        'gicd': 0x17a00000,
        'gicd_size': 0x10000,
        'gicr': 0x17a60000,
        'gicr_size': 0x100000,
        'timebase': 19200000,
        # Qualcomm numbers the architected timer PPIs 1/2/3/0 (sec phys,
        # phys, virt, hyp): CNTV = INTID 16 + 3.
        'vtimer_intid': 19,
        # reserved-memory cont_splash_region that ABL leaves lit.
        'fb': 0x9c000000,
        'fb_size': 0x1700000,
        'fb_w': 1080,
        'fb_h': 2400,
        'fb_stride': 1080 * 4,
        # Internal UFS host (ufshc@1d84000 "ufs_mem"); base is read from the
        # ADT's sweet-ufs node by bsd/dev/sweet_ufs.c.
        'ufs': 0x01d84000,
        'ufs_size': 0x3000,
        # Kryo 470: 6x A55 + 2x A76, one homogeneous SMP cluster. `reg` is
        # the raw MPIDR (Aff1:Aff0), not a logical index.
        'cpu_compat': 'qcom,kryo470',
        'cpus': 8,
        'cpu_regs': [0, 0x100, 0x200, 0x300, 0x400, 0x500, 0x600, 0x700],
        'cpu_clocks': [1804800000] * 6 + [2304000000] * 2,
        'memory_frequency': 1866000000,
        'bus_frequency': 100000000,
    },
    'guacamole': {
        # OnePlus 7 Pro (guacamole, SM8150). Board facts from the LineageOS
        # oneplus_sm8150 DTS (arch/arm64/boot/dts/18821/) and the mainline
        # sm8150-oneplus-guacamole.dts; audited against the GM1910's own live
        # FDT on 2026-10-19 (tools/fdt-audit.py; see GUACAMOLE.md).
        'name': 'OnePlus 7 Pro (guacamole, SM8150)',
        'board_compat': 'oneplus,guacamole',
        'soc_compat': 'qcom,sm8150',
        # SM8150 DDR (audited on the GM1910's live FDT 2026-10-19): three
        # banks - 0x80000000+0x3bb00000, 0xc0000000+0xc0000000 and
        # 0x180000000+0x100000000; the 0x100000000..0x180000000 window (2 GiB)
        # is OnePlus's mem-offline region and 0xbbb00000..0xc0000000 (69 MiB)
        # is a hole, both absent from /memory. The phone path uses the upper
        # bank; `phys_base`/`mem_size` name the 3 GiB mid bank (carve-out
        # free) so QEMU/lowmem runs have a valid window too.
        'phys_base': 0xc0000000,
        'mem_size': 0xc0000000,
        'high_phys_base': 0x180000000,
        'high_mem_size': 0x100000000,
        'gicd': 0x17a00000,          # confirmed on the live FDT
        'gicd_size': 0x10000,
        'gicr': 0x17a60000,          # confirmed
        'gicr_size': 0x100000,
        'timebase': 19200000,        # confirmed (clock-frequency)
        'vtimer_intid': 19,          # confirmed (GIC_PPI 3 numbering)
        # reserved-memory cont_splash_region: 0x9C000000, 0x02400000 (36 MiB);
        # confirmed on the GM1910's live FDT. The mainline port drives the same
        # range as a simple-framebuffer (1440x3120, stride 5760, a8r8g8b8).
        'fb': 0x9c000000,
        'fb_size': 0x2400000,
        'fb_w': 1440,
        'fb_h': 3120,
        'fb_stride': 1440 * 4,
        'ufs': 0x01d84000,           # confirmed (ICE at 0x1d90000 too)
        'ufs_size': 0x3000,
        # Kryo 485: 4x A55 (silver) + 3x A76 (gold) + 1x A76 (prime).
        'cpu_compat': 'qcom,kryo485',
        'cpus': 8,
        'cpu_regs': [0, 0x100, 0x200, 0x300, 0x400, 0x500, 0x600, 0x700],  # confirmed (live FDT)
        'cpu_clocks': [1785600000] * 4 + [2419200000] * 3 + [2841600000],   # verify: opp tables
        'memory_frequency': 2133000000,
        'bus_frequency': 100000000,
    },

    'mh2lm': {
        # LG G8X ThinQ (LM-G850, SM8150). 同 SoC 的 GIC/timer/UFS 直接沿用 guacamole 的
        # 数值（已在 android-mh2lm.dtb 里核对：gic@17a00000、timer@17c20000、ufshc@1d84000）。
        # 显示与内存布局来自 mh2lm 自己的数据，见每项注释。
        'name': 'LG G8X ThinQ (mh2lm, SM8150)',
        'board_compat': 'qcom,sm8150',      # TODO(verify): 根节点只写了 qcom,sm8150
        'soc_compat': 'qcom,sm8150',
        # TODO(verify): 内核可管理 RAM。目前取 mh2lm 内存映射里 0xC4000000 起的那段；
        # 真机 /memory 由 ABL 填，需要在 UEFI 里打印一份再定。
        'phys_base': 0xc4000000,
        'mem_size': 0x7c000000,
        'high_phys_base': 0x140000000,
        'high_mem_size': 0x40000000,
        'gicd': 0x17a00000,
        'gicd_size': 0x10000,
        'gicr': 0x17a60000,
        'gicr_size': 0x100000,
        'timebase': 19200000,
        'vtimer_intid': 19,
        # android-mh2lm.dtb: reserved-memory/splash_region = 0x9C000000 + 0x02400000，
        # 但 ABL 实际扫描输出的是 Mu 内存映射里的 "Display Reserved" = 0x9D200000 + 0x01200000：
        # 证据 1：lg-mh2lm 的 PlatformMemoryMapLib.c:25（Display Reserved 0x9D200000 0x01200000）；
        # 证据 2：SimpleFbDxe 按名字找这块区域，M1/M2 的菜单与日志画在它上面，面板可见。
        # 所以内核 console 必须写 0x9D200000，写 0x9C000000 只会进 splash 区、屏幕无变化。
        'fb': 0x9D200000,
        'fb_size': 0x01200000,
        'fb_w': 1080,
        'fb_h': 2340,
        'fb_stride': 1080 * 4,
        'ufs': 0x01d84000,
        'ufs_size': 0x3000,
        'cpu_compat': 'qcom,kryo485',
        'cpus': 8,
        'cpu_regs': [0, 0x100, 0x200, 0x300, 0x400, 0x500, 0x600, 0x700],
        'cpu_clocks': [1785600000] * 4 + [2419200000] * 3 + [2841600000],   # verify: opp tables
        'memory_frequency': 2133000000,
        'bus_frequency': 100000000,
    },
    'alphaplus': {
        # LG G8 ThinQ (LM-G820, alphalm, SM8150). Same SoC as mh2lm/guacamole, so
        # GIC / timer / UFS are the SM8150 facts and carry over unchanged. Values
        # taken from Project-Aloha mu_aloha_platforms, Device/lg-alpha:
        # Platforms/SurfaceDuo1Pkg/Device/lg-alpha/Library/PlatformMemoryMapLib.
        # Values checked against this phone's live FDT are marked CONFIRMED.
        'name': 'LG G8 ThinQ (alphaplus, SM8150)',
        # CONFIRMED: android-alpha.dtb root compatible = "qcom,sm8150";
        # model = "Qualcomm Technologies, Inc. SM8150 v2 SoC".
        'board_compat': 'qcom,sm8150',
        'soc_compat': 'qcom,sm8150',
        # CONFIRMED against this phone's live FDT (/proc/device-tree/memory/reg):
        #   bank 0x80000000 + 0x3cc00000
        #   bank 0xc0000000 + 0x80000000
        #   bank 0x140000000 + 0xc0000000      (~5.95 GiB total)
        # phys_base + mem_size ends exactly at 0x140000000, the start of the third
        # bank, and leaves the first 64 MiB of bank 2 to UEFI runtime.
        'phys_base': 0xc4000000,
        'mem_size': 0x7c000000,
        'high_phys_base': 0x140000000,
        'high_mem_size': 0x40000000,
        # CONFIRMED: /soc/interrupt-controller@17a00000, reg = 0x17a00000 0x10000
        # 0x17a60000 0x100000 (arm,gic-v3).
        'gicd': 0x17a00000,
        'gicd_size': 0x10000,
        'gicr': 0x17a60000,
        'gicr_size': 0x100000,
        # CONFIRMED: /soc/timer@0x17c20000 clock-frequency = 19200000.
        'timebase': 19200000,
        'vtimer_intid': 19,
        # CONFIRMED: lg-alpha PlatformMemoryMapLib, "Display Reserved" =
        # 0x9D200000 + 0x01200000 (same range mh2lm uses). G8 panel is 1440x3120.
        'fb': 0x9D200000,
        'fb_size': 0x01200000,
        'fb_w': 1440,
        'fb_h': 3120,
        'fb_stride': 1440 * 4,
        # CONFIRMED: /soc/ufshc@1d84000, reg = 0x1d84000 0x2500 0x1d90000 0x8000
        # (the second range is the ICE block).
        'ufs': 0x01d84000,
        'ufs_size': 0x3000,
        'cpu_compat': 'qcom,kryo485',
        'cpus': 8,
        'cpu_regs': [0, 0x100, 0x200, 0x300, 0x400, 0x500, 0x600, 0x700],
        'cpu_clocks': [1785600000] * 4 + [2419200000] * 3 + [2841600000],   # verify: opp tables
        'memory_frequency': 2133000000,
        'bus_frequency': 100000000,
    },
}


def get(name):
    try:
        return DEVICES[name]
    except KeyError:
        raise SystemExit(f'unknown device "{name}"; known: {", ".join(sorted(DEVICES))}')
