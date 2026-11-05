# UniXNU-mh2lm（P2 起草）

LG G8X ThinQ（`mh2lm`，SM8150）的 UniXNU 设备仓库。结构照 `ref/UniXNU-guacamole` 抄，
数值凡未在真机上核对过的都标了 `TODO(verify)`。

## 现状（2026-10-27）

- `board.toml` 已能被 UniXNU 解析：`python3 unixnu status -D ../UniXNU-mh2lm` 正常列出 device/drivers/kits/patches。
- `scripts/`：`adt.py`、`mkadt.py`、`devices.py` 从 guacamole 拷来，**已加 `mh2lm` device profile**
  （GIC/timer/UFS 与 android-mh2lm.dtb 核对过；fb/内存布局标了 TODO(verify)）。
- **ADT 已经能离线生成**：`python3 scripts/mkadt.py out.adt --device mh2lm --dram-size 0xc0000000`
  → 9904 B。目前缺 `base-d22ap.adt`（Apple 的 /product 身份节点，要从 iOS 16 IPSW 里抽），
  生成时会警告 "no /product node"。
- 内核（`kernel.macho`）还没有：需要 iOS 16 的 kernelcache 与预链接工具链。
- `configs/`（defconfig）还没写。

## 待办

| # | 事项 | 依赖 | 备注 |
| --- | --- | --- | --- |
| 1 | `scripts/devices.py` 加 `mh2lm` profile | 无（离线可做） | 从 `android-mh2lm.dtb` 里读 GIC/timer/fb/UFS/USB/I2C 等节点；与 guacamole 同 SoC，多数地址可直接对 |
| 2 | `scripts/make-mh2lm-adt.py` | #1 | 照 `make-guacamole-adt.py` 改 `--device mh2lm` |
| 3 | `configs/` defconfig | #1 | `unixnu defconfig` 选配置用 |
| 4 | 内核 Mach-O（`kernel.macho`） | **需要工具链 + IPSW** | 见下 |
| 5 | payload FAT 卷 | #4（或 stub） | `unixnu payload --kernel FILE` |

## 关键数值（来自本工作区已核对的数据）

| 项 | 值 | 来源 |
| --- | --- | --- |
| UEFI FD | `0xC3C00000`，`0x300000` | `SurfaceDuo1.fdf` / `PlatformMemoryMapLib` |
| 显示 framebuffer | `0x9D200000`（"Display Reserved" 18 MiB） | mh2lm 内存映射 |
| 面板 | 1080×2340，32bpp | `PcdsFixedAtBuild.dsc.inc` |
| boot.img | v0 / 4096 / kernel@0x8000 / tags@0x100 | 实测可启动 |
| ABL "Kernel" RAM 区 | `0x80000000` + **仅 6 MiB** | mh2lm 内存映射 ⚠️ |

⚠️ **6 MiB 的 Kernel 区装不下 64 MiB payload ramdisk**。P2 必须先决定：
(a) 改 `PlatformMemoryMapLib` 把 Kernel 区扩到（至少）96 MiB，且不能和别的 carve-out 冲突；
(b) 或换加载方式（payload 放别的已映射区）。

## 内核步骤需要什么

`unixnu kernel` 在 Linux 上用 `scripts/linux/setup-toolchain.py` 准备工具链；
`--skip-setup` / `seed-data-grow` 之类才需要 macOS 的 `hdiutil`。
所以云端准备一台**能联网的 Linux**（16–32 GiB 内存比较稳）+ iOS 16 IPSW 即可，未必要 macOS。

## 先到 M2 的捷径（不依赖内核）

M2 的验收只是 `DARWINBOOT: inputs validated; exiting boot services`。
可以用一个**手搓的最小 ARM64 Mach-O**（clang 直接可生成）当 `--kernel`，
把 DarwinBoot 的校验、窗口分配、ExitBootServices 全跑通；真内核等工具链就绪再换。


## 2026-10-27 晚：A1（本地 stub 冲 M2）的调研结论

### 载荷链路（读源码得到，和之前的假设不同）

1. ABL 按 boot.img 头的 `ramdisk_addr/size` 把 ramdisk 装进 RAM，并把区间写进它传给下一级的 **DTB**
   的 `/chosen`：`linux,initrd-start` / `linux,initrd-end`；
2. `BootShim` 保留 x0（DTB 指针）→ Mu PrePi 存进 HOB；
3. `UniXNURamDiskDxe` 读 `/chosen` 的 initrd 区间，**把这段内存当只读块设备发布**；
4. UniXNU 在它上面挂 FAT → 读 `EFI/UniXNU/unixnu.toml`；
5. 选 `xnu` 条目后，DarwinBoot 从**同一个 FAT 卷**读 `kernel.macho` 和 `kernel.macho.adt`，
   用 ADT 里的节点决定 window/ramdisk/video，然后 ExitBootServices 跳内核。

所以 payload 卷 = **initrd ramdisk**（64 MiB FAT 镜像），不是放进 FV。

### DarwinBoot 对内核 Mach-O 的硬要求（ParseKernel）

- magic `0xfeedfacf`、cputype `0x0100000c`、filetype 2
- `LC_SEGMENT_64` 且 `vmsize != 0`；入口必须落在**可执行段**（initprot & 4）且在其 filesize 内
- `LC_UNIXTHREAD`（cmd 5）cmdsize 288、flavor 6、count 68、pc 在 +272
- 段不重叠、base 页对齐、`End-Base ≤ window - 2 MiB`

`ld64.lld` 产出的是 `LC_MAIN`，不被接受；已写 [scripts/make-stub-kernel.py](../../scripts/make-stub-kernel.py)
直接生成满足上述条件的 Mach-O（17 872 B，entry 0x11000），并用同样的规则自检通过。

### 待办（下一轮）

1. `unixnu payload --kernel <stub> --uefi <aloha>` 生成 64 MiB FAT（会调用 make-mh2lm-adt.py）；
2. boot.img 加 ramdisk，**ramdisk 地址要避开 mh2lm 的 `DBI Dump` carve-out（0x82A00000–0x83722000）**：
   `0x81000000 + 64 MiB` 会撞上，候选是 `0xC4000000` 或先缩到 32 MiB 试探；
3. `fastboot boot` 看 `DARWINBOOT: inputs validated; exiting boot services`（M2 验收）。


## 2026-10-27 夜：ramdisk 加载的两次试错（重要结论）

| 现象 | 真正原因 | 处置 |
| --- | --- | --- |
| 加了 ramdisk 后「闪日志→黑屏→重启」 | mh2lm 的库存内存映射里 **0x80600000–0x82A00000 没有描述**，PrePi 没给它建页表；驱动一读就 data abort | 在 `PlatformMemoryMapLib` 里补一段 `RAM Partition 0x80600000 + 0x02400000`（[0013](../../patches/0013-ramdisk-window-mapping.patch)） |
| 读 unmapped 还导致「扫描候选地址」自杀 | 同上 | 驱动里的候选地址全部限在 **4 GiB 以下**（高段 DDR 在这棵树里没映射） |
| 修好映射后仍失败 | ABL 自报 **`lge crash handler: secure watching bite! invalid ram console`** —— LG 的 ABL 对「带大 ramdisk 的 boot.img」有自己的安全检查（ram console / secure watchdog），0x81000000 与 0x82000000 都触发 | 待定，见下 |

### 现在的取舍

- **不再走 ramdisk**：把 payload（stub 只有 ~30 KB）做成 **FFS 文件塞进 FV**，由 FvSimpleFileSystem 提供卷。
  FD 目前用 2.35/3 MiB，余量足够；这样完全不碰 ABL 的 ramdisk 逻辑。
- 或继续逆 ABL 的 ram console / secure watchdog 规则（成本高、收益低）。

驱动侧已经准备好：`UniXNURamDiskDxe` 在拿不到 FDT initrd 时会用构建期 PCD（`PcdUniXNUInitrdBase/Size`）
扫描候选地址里的 FAT 引导扇区（[0014](../../patches/0014-initrd-fallback.patch)），换偏移只要重打 boot.img。


## 2026-10-27 夜（B1）：payload 走 FV，M2 打通

- **B1 做法**：`payload.img`（512 KiB FAT12，含 `EFI/UniXNU/unixnu.toml` + `Payloads/kernel.macho[.adt]`）
  作为 `FILE FREEFORM = 7E2B4C1A-...` 的 `SECTION RAW` 塞进 FV（`SurfaceDuo1.fdf`）；
  `UniXNURamDiskDxe` 先用 `GetSectionFromAnyFv()` 取这段，发布成只读块设备。boot.img 保持 6 字节空 ramdisk，完全不碰 ABL 的 ramdisk 逻辑。
  → **菜单出现 `LG G8X - XNU (stub)` 条目**（[0016](../../patches/0016-fv-payload.patch) / [0017](../../patches/0017-initrd-and-fv-source.patch)）
- **Mu 变量策略的 DEBUG 断言**：`MuVarPolicyFoundationDxe` 的 `ASSERT_EFI_ERROR` 在 mh2lm 上必然触发
  （变量服务拒绝阶段指示变量，`EFI_INVALID_PARAMETER`），会让 ReadyToBoot / Restart / Power off 全部卡死。
  已降级为只打日志（[0015](../../patches/0015-varpolicy-assert-debug-only.patch)）。
- **M2 现象**：选中 XNU 条目后屏幕**闪绿光**（DarwinBoot 在 ExitBootServices 前把 framebuffer 顶部 1/16 刷绿），
  随后设备复位回 Android —— stub 内核没有真正的内核代码，复位是预期行为。**即 DarwinBoot 已完成输入校验并退出 boot services**。
- 待办：为了留下"日志证据"，给 DarwinBoot 加一个可选的 handoff 前 stall（几秒），让屏幕上的
  `DARWINBOOT: inputs validated; exiting boot services` 能被拍到；之后 M2 就可以正式勾掉，进入真内核（云端）。

## 2026-10-31：M3 卡点的两个根因（探针二分）

方法：`ci/0019` 里的 `patches/xnu/zzzz-mh2lm-early-boot-probes.patch`（用法见 `ci/README.md`）。
MMU 开之前画色带；之后用"等 3 s → PSCI SYSTEM_RESET"当信号（3 s 正常重启进 Android = 走到了；卡住/watchdog bite = 没走到）。
kernel_bootstrap 之后改成 boot-arg `mh2lm_reset=<步骤名>`，只改 ramdisk 里 unixnu.toml 的 args，不用重跑 CI。
**注意**：步骤名必须先用 `strings kernel | grep -x NAME` 确认存在（`sfi_init`、`load_context` 在本内核里不存在，曾导致两轮误判）。
重启延时必须 < secure watchdog 窗口（10 s 会被看门狗抢先，3 s 安全）。

### 根因 1：固件把 payload 冲成 0xAF（已修，已验证）
- 现象：start.s 全部通过，ret 进 arm_init 就卡住，5–6 s 后 watchdog bite。
- 位图探针读出 arm_init 处内存 = `0xAFAFAFAF`（Mu DEBUG 固件 `PcdDebugClearMemoryValue`，释放内存时的填充）。
- DarwinBoot 诊断：内核文件刚从 ramdisk 读出来就有 ~14 MiB 是 0xAF。
- 原因：Mu `MemoryMapLib` 里我们加的 "DTB Window" 0x82400000–0x85700000（同时包含 ABL 放的 ramdisk 0x835ff800）
  类型写成了 `Conv`，DXE 分配器在 ramdisk 驱动认领之前就把这些页分配/释放过。
- 修复：改成 `BsData`（Mu-Silicium 分支 `mh2lm-dtb-window`，e84e094）。验证：0xAF 计数 0，arm_init 处 = 0xD10343FF。

### 根因 2：源码 corecrypto 注册晚于第一次 SHA1 调用（修复待验证）
- 二分路径：arm_init 全过 → kernel_bootstrap 主线程全过 → bootstrap 线程 `PE_init_iokit()` → `InitIOKit()` 过 →
  `ConfigureIOKit()` → `IOPlatformExpertDevice::configureDefaults()` → createNVRAM 过、serial 过 → **`generatePlatformUUID()` 卡住**。
- `generatePlatformUUID()` 用 `/chosen` 的 `unique-chip-id` + `chip-id` 算 SHA1 → `SHA1Init` 解引用 `g_crypto_funcs`。
- 我们用 `CONFIG_XNU_CRYPTO_BOOTSTRAP="source"`，源码 corecrypto 在 `STARTUP(EARLY_BOOT)` 才注册；
  而 `PE_init_iokit()`（startup.c:717）在 `STARTUP_SUB_EARLY_BOOT`（startup.c:726）之前 → 空指针 → 异常 → 控制台还没出字，看起来是卡住。
- 上游/sheng 用的是 `prelinked`（kernelcache 里的原版 corecrypto），所以没撞上；ios-sweet 没有 corecrypto，
  同类 NULL `g_crypto_funcs` 逐个换成 BearSSL。ios-sweet 也证明 ADT 必须有 unique-chip-id/chip-id（否则无 IOPlatformUUID，datamigrator 无限迁移），不能删。
- 修复（方案 A）：`source-corecrypto14-bootstrap.patch` 改为 `STARTUP(SYSCTL, STARTUP_RANK_LAST, ...)`。
  `corecrypto_kext_start()` 只需要 zalloc、锁和 `sysctl_register_oid()`（动态注册，SYSCTL 阶段后可用），不需要中断/抢占。

- **更正（2026-10-31，CI 产物 k8796q 核对）**：只改 STARTUP 阶段不够——此前所有内核里都**没有** `_source_corecrypto14_bootstrap`。
  原因：xnu-8796 的 `makedefs/MakeInc.def` 的 `CFLAGS` 不含 `$(CFLAGS_EXTRA)`（10063 有），build 脚本经 `CFLAGS_EXTRA` 传的
  `-DXNU_SOURCE_CORECRYPTO14=1`、`-DXNU_NATIVE_PAN=…`、`-DXNU_BOOT_PROGRESS=…` **全部被丢掉**，源码 corecrypto 从未启动，
  `g_crypto_funcs` 一直是 NULL。修复：新增 `patches/xnu/makeinc-cflags-extra.patch`（照 10063 把 `$(CFLAGS_EXTRA)` 加进 `CFLAGS`）。
  副作用：`native-arm-pan.patch` 里 `#if XNU_NATIVE_PAN` 的代码此后才真正编进去（defconfig 开了 NATIVE_PAN）。

- **验证（2026-10-31）**：k8796r（CFLAGS_EXTRA 生效）+ 本地封 HMAC，`mh2lm_reset=pe_uuid_done` 3 s 正常重启 → 根因 2 修复确认。
  CI 的封 HMAC 步骤被跳过（`grep -qa` 在 macOS runner 上对 20 MB 内核误判），改成 python 字节查找；未封则 FIPS POST 失败。

### 根因 3：trust cache runtime 需要 AMFI/Image4 接口（已改 defconfig，待验证）
- 二分：`trust_cache_init` 日志过，`OSKextRemoveKextBootstrap` 日志没到；中间只有 `trust_cache_runtime_init()`、
  `load_static_trust_cache()`、`STARTUP_SUB_LOCKDOWN`（8796 里没有 LOCKDOWN 启动项）。
- `trust_cache_runtime_init()`（bsd/kern/kern_trustcache.c:67）：`img4if == NULL` → `panic("image4 interface not available")`，
  `amfi == NULL` → `panic("amfi interface not available")`。这两个接口由 AppleImage4 / AMFI kext 注册，只有 prelinked kernelcache 才有；
  我们是纯源码内核，两者都是 NULL → panic → 看不到 → 卡住。
- `native-trust-cache-runtime.patch` 让 BCM2837 在 `XNU_NATIVE_TRUST_CACHE=1` 时也跑这段（给 prelinked 的 iPadOS 配置用）。
  修复：`configs/mh2lm_defconfig` 关掉 `CONFIG_XNU_TRUST_CACHE_RUNTIME`（BCM2837 回到原版：不初始化 trust cache runtime）。

### 另一个待解决的问题
内核从头到尾没有画出过任何文字（`-v`、PE_init_printf(TRUE) 都过了），所以 panic 也看不到。修完根因 2 后单独查。
