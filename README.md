# UniXNU 设备仓库 · LG G8 ThinQ (alphaplus / alphalm, SM8150)

在 LG G8 ThinQ 上通过 UEFI 启动 Darwin / iOS 16 用户态的移植仓库，结构参照
`shenli99/UniXNU-mh2lm`（LG G8X，同 SM8150、同 LG 平台）。

## 当前状态

**P1 — 设备仓库骨架。** 板级参数已建表，构建与真机验证尚未开始。

已在本机真机确认的平台事实（2026-11-05）：

| 项 | 结果 | 依据 |
| --- | --- | --- |
| Bootloader | `DEVICE STATE - unlocked`，`unlocked: yes` | 真机 bootloader 界面 + `fastboot getvar unlocked` |
| `fastboot boot` | **不可用**：`Failed to load/authenticate boot image` | 真机实测；LG abl 对 RAM 启动做鉴权 |
| `fastboot flash` | 可用 | UEFI 镜像刷入 `boot_a` / `boot_b` 成功 |
| `fastboot set_active` | **未实现**：`unknown command` | 真机实测；只能刷当前活动槽 |
| UEFI (Project-Aloha `lg-alphaplus_NOSB.img`) | **可启动**：显示、UFS、分区枚举全部正常 | 屏幕输出 `BLK95`–`BLK115` 与 UEFI Shell 提示 |
| Secure boot | `secure: yes` | `fastboot getvar secure`；解锁不影响芯片级 fuse |

结论：这台机只能走「刷分区 → 重启 → 验证 → 刷回」的循环，不能靠 RAM 启动试错。

## 已确认的板级值

来自 Project-Aloha `mu_aloha_platforms`
`Platforms/SurfaceDuo1Pkg/Device/lg-alpha/Library/PlatformMemoryMapLib/PlatformMemoryMapLib.c`：

| 项 | 值 |
| --- | --- |
| Display Reserved | `0x9D200000` + `0x01200000`（与 mh2lm 相同） |
| Kernel 段 | `0x80000000` + `0x02A00000`（42 MiB，比 mh2lm 的 6 MiB 宽裕） |
| DXE Heap | `0xC0000000` + `0x80000000` |
| 6 GB 内存空洞 | `0xBCC00000` – `0xBFFFFFFF` |
| 面板 | 1440 × 3120 |

SoC 层面已用本机 DTB（`android-alpha.dtb`，用 `scripts/fdt-probe.py` 解析）逐条确认：

| 节点 | DTB 内容 | 仓库取值 |
| --- | --- | --- |
| 根节点 | `compatible = "qcom,sm8150"`，`model = "... SM8150 v2 SoC"` | `board_compat` 已确认 |
| `/soc/interrupt-controller@17a00000` | `0x17a00000 0x10000` + `0x17a60000 0x100000`（`arm,gic-v3`） | `gicd` / `gicr` 已确认 |
| `/soc/ufshc@1d84000` | `0x1d84000 0x2500` + `0x1d90000 0x8000`（ICE） | `ufs` 已确认 |
| `/soc/timer@0x17c20000` | `clock-frequency = 19200000` | `timebase` 已确认 |
| `/reserved-memory/disp_rdump_region` | `0x9c000000 + 0x2400000` | 与 UEFI 的 `Display Reserved 0x9D200000` 并存，取后者 |

## 未确认项（动手前必须补）

`board.toml` 与 `scripts/devices.py` 里所有 `TODO(verify)` 都不是猜着就能用的值：

1. **`serial=`** —— 内核参数里的 UART 编号沿自 guacamole，LG 平台未验证。
2. **`FDT` 名** —— `board.toml` 里写的是 `android-alpha.dtb`，要以 lg-alpha 的 package 为准。
3. **CI 的 early-boot probe 补丁** —— 已从 mh2lm 机械改名为
   `zzzz-alphaplus-early-boot-probes.patch`（`mh2lm_*` → `alphaplus_*`，`MH2LM_*` → `ALPHA_*`）。
   这套 instrumentation 只挂在通用 XNU 初始化点（`bsd_init.c`、`IOPlatformExpert.cpp`、
   `osfmk/arm64/start.s`），不含任何硬件地址，所以改名后应可直接套用；但**尚未在 macOS
   runner 上实跑验证**。改名后 `ci/0019-unixnu-8796-ci.patch` 仍为 1789 行，内层 hunk
   `@@ -0,0 +1,564 @@` 的 564 行全部以 `+` 开头，结构未破。

内存布局已在真机确认。Project-Aloha 的 `android-alpha.dtb` 里 `/memory` 是占位值
（`0x0 0x0 0x0 0x0`），真实值由 bootloader 运行时填入；从手机上读
`/proc/device-tree/memory/reg` 得到三段：

| bank | base | size |
| --- | --- | --- |
| 1 | `0x80000000` | `0x3cc00000` |
| 2 | `0xc0000000` | `0x80000000` |
| 3 | `0x140000000` | `0xc0000000` |

合计约 5.95 GiB。`phys_base + mem_size` = `0xC4000000 + 0x7C000000` 正好止于
`0x140000000`（第三段起点），与 mh2lm 的窗口一致，前 64 MiB 留给 UEFI runtime。

## 与 mh2lm 的关键差异

| | mh2lm (G8X) | alphaplus (G8) |
| --- | --- | --- |
| Kernel 段大小 | 6 MiB（payload ramdisk 放不下） | 42 MiB |
| 面板 | 1080 × 2340 | 1440 × 3120 |
| 内存 | 6 GB | 6 GB |
| ECID | 无 | 无 |
| 现状 | UEFI + DarwinBoot 已在真机跑通，内核入口未打通 | 仅 UEFI 验证通过 |

## 构建流程

内核必须用 macOS 编（Xcode 15），本仓库沿用 GitHub Actions 的 macOS runner：

```sh
# Linux / WSL，设备侧工具
python3 scripts/make-alphaplus-adt.py out.adt --device alphaplus --dram-size 0xc0000000

# macOS（或 Actions），内核
./unixnu defconfig alphaplus_defconfig -D ../UniXNU-alphaplus
./unixnu fetch
./unixnu status --json
```

`scripts/base-d22ap.adt` 是 Apple 的设备树产物，按惯例不入库，需要用 IPSW 现场抽取：

```sh
python3 scripts/adt.py unwrap Firmware/all_flash/DeviceTree.d22ap.im4p scripts/base-d22ap.adt
```

## 不放进仓库的东西

| 内容 | 原因 |
| --- | --- |
| IPSW / kernelcache / DeviceTree 原文件 | Apple 产物，从 Apple 官方下载 |
| `scripts/base-d22ap.adt` | 同上 |
| 设备分区镜像 / 备份 | 体积 + 隐私 |
| `.cache/`、`__pycache__` | 构建缓存 |

## 继承文件

继承自 mh2lm、尚未改写的内容：

| 文件 | 状态 |
| --- | --- |
| `DEVIATIONS.md` | 仍适用：解释为什么 iOS 16 必须走 format 1 |
| `NOTES-mh2lm.md` | G8X 的开发日志，仅作同平台的参考，板级结论不适用于 G8 |
| `ci/README.md` | 描述 CI 补丁的内容，文中仍用 mh2lm 的旧名字，补丁本身已改名为 alphaplus |

`scripts/devices.py` 里的 `mh2lm` / `guacamole` / `sweet` 条目是刻意保留的参照设备，
不是遗留物。
