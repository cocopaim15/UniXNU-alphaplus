# CI：在 GitHub Actions 上编内核

这里放的是"设备仓库 + 一条 workflow"，用来在 macOS runner 上得到 xnu-8796 内核。
**为什么不在本机 Linux 上编**：Linux 工具链（`/opt/unixnu-linux`）能编到 848 个 `.o`，唯一卡点是
`iig`——它是 DriverKit 的接口生成器，输出格式跟 Xcode 世代绑定，新 iig 生成 `IORPC.kernelContent`，
而 8796 的 `IORPC` 没有这个字段。Xcode 15 的 iig 才是对的（cepheus 的 8796 CI 也钉在 Xcode 15）。

## 文件

| 文件 | 作用 |
| --- | --- |
| `.github/workflows/kernel-8796.yml` | 克隆 UniXNU → 打 `ci/0019-unixnu-8796-ci.patch` → `unixnu build kernel` → 传 artifact |
| `ci/0019-unixnu-8796-ci.patch` | 本设备仓库对 UniXNU 的改动**只保留内核相关部分**：`feeds.toml` 钉 8796、`patches/xnu/*`、`scripts/unixnu/ipsw.py`。**不含** `package/`（固件侧）、**不含** dirty 子模块指针 |

## 推之前的三件事

1. **仓库放 GitHub**。macOS runner 在**公开仓库**上是免费的；私有仓库按 10× 计费，
   免费额度 2000 min/月 → 实际只有 ~200 macOS 分钟，**一次内核构建就可能超**。
   建议：单独建一个**公开的 CI 仓**（只放本目录的 `board.toml`、`configs/`、`scripts/`、`ci/`），
   主工作区继续私有。不要推 IPSW、kernelcache、设备分区镜像（纪律 C-03 / P5）。
2. **确认 UniXNU 提交**：workflow 默认 pin 到 `40d21cc`（2026-10-28 验证过 patch 能干净打上）。
   上游 main 变动时改 `unixnu_sha` 输入即可，不用改代码。
3. **跑一次要多久**：macos-14 标准 runner 是 3 核，`unixnu build kernel` 含一次 bootstrap pass，
   预计 **2–3 小时**（超时上限设 350 分钟）。产物 ~几百 MB。

## 跑完拿什么、怎么用

artifact `kernel-8796` 里有：

```
kernel/mach.development.bcm2837*        ← 内核（4 KiB 页，BCM2837 machine config）
kernel/start.s                          ← 实际编进去的 start.s（含探针），对照用
logs/*.log                              ← out/mh2lm/logs/ 全部日志；xnu-work-diffstat.txt 是补丁实际改动
relink/tree/...                         ← 重新链接的输入：link.filelist 及其全部 .o、.LDFLAGS、
                                          导出表、archive builder 的 .a、fakeroot 的 libfirehose/libcc_kext
```

早期启动探针在 `ci/0019` 新增的 `patches/xnu/zzzz-mh2lm-early-boot-probes.patch`（文件名排最后，
在全部 UniXNU 补丁之后应用）。画法与官方 `scripts/patch-xnu-entry-probe.py` 相同：从 boot_args.Video
取 base/rowBytes/height，第 N 阶段画第 N 个 1/16 色带，排在 DarwinBoot 绿带下面：

| 条 | 颜色 | 位置 |
| --- | --- | --- |
| 1 | 红 | start_first_cpu 入口 |
| 2 | 橙 | DAIFSet 关中断后 |
| 3 | 黄 | 装 LowExceptionVectorBase 后 |
| 4 | 白 | 读完 boot args 后 |
| 5 | 青 | 异常栈、中断栈建好后 |
| 6 | 蓝 | bootstrap 页表建好后 |
| 7 | 品红 | TCR、TTBR0/1、MAIR 配好后 |
| 8 | 灰 | 装最终异常向量后、开 MMU 前 |

开 MMU 之后 framebuffer 没映射，改用**定时重启**当信号：在选中的位置等 `MH2LM_PROBE_RESET_SECONDS`（3 秒）后
PSCI SYSTEM_RESET。看**重启方式**判断：

- 约 3 秒后**正常重启进 Android** = 我们的 PSCI 重启，走到了这个位置；
- **bsp-kernel + secure watchdog bite**（约 10 秒）= 看门狗咬的，没走到。

延时必须比看门狗窗口短：10 秒时被看门狗抢先（2026-10-31），6 秒时没有。
位置由补丁里 `osfmk/arm64/mh2lm_probe.h` 的 `MH2LM_PROBE_RESET_AT` 选（一次只启用一个，0 = 关闭）：

| 值 | 名字 | 位置 | 结果 |
| --- | --- | --- | --- |
| 1 | `MMU_ON` | start.s，`msr SCTLR_EL1` 之后 | 2026-10-31 实机通过（8 条色带后自动重启） |
| 0 | `NONE` | 不重启 | **当前选中**（改用下面的 boot-arg）；修复 ramdisk 后不重启时 8 条色带后卡住 > 1 min |
| 2 | `COMMON_START_RET` | start.s，`ret` 回 arm_init 之前（仅冷启动） | 2026-10-31 实机通过（3 s 正常重启） |
| 3 | `ARM_INIT` | arm_init.c，第一句 | 失败（5–6 s 后 watchdog bite）；根因是固件把 ramdisk 冲成 0xAF，见下 |
| 4 | `REBASED` | arm_init.c，`arm_slide_rebase_and_sign_image()` 之后 | |
| 5 | `PE_INIT` | arm_init.c，`PE_init_platform(FALSE)` 之后 | 2026-10-31 实机通过（3 s 正常重启） |
| 6 | `VM_INIT` | arm_init.c，`arm_vm_init()` 之后 | 2026-10-31 实机通过（3 s 正常重启） |
| 7 | `KVA_CHECK` | start.s，`ret` 之前用 `at s1e1r` 翻译 arm_init 的 KVA，不跳过去 | 2026-10-31：2 s 正常重启 = 翻译成功且 PA 正确 |
| 8 | `SERIAL_INIT` | arm_init.c，`serial_init()` 之后 | |
| 9 | `KPRINTF` | arm_init.c，`kernel_startup_initialize_upto(STARTUP_SUB_KPRINTF)` 之后 | |
| 10 | `PRINTF` | arm_init.c，`PE_init_printf(FALSE)` 之后 | 2026-10-31 实机通过（3 s 正常重启，无文字） |
| 11 | `MACHINE_STARTUP` | arm_init.c，`machine_startup()` 之前 | 2026-10-31 实机通过（3 s 正常重启，无文字） |

`MH2LM_PROBE_DUMP_PA`（当前关闭，= 0）：开 MMU 前在第 9、10 条色带位置各画 32 列位图（左边是最高位，白 = 1，灰 = 0）。
第 9 条 = Mach 头 PA >> 12；第 10 条 = 从 arm_init 的 PA 读出的第一个字。第 10 条没出现 = 那次读内存卡住了。
2026-10-31 读数：Mach 头 PA = 0xA4004000；第 10 条起初是 0xAFAFAFAF（DEBUG 固件的释放填充）。
根因：Mu MemoryMapLib 的 "DTB Window" 写成了 Conv，DXE 把 ABL ramdisk 所在的页分配/释放，冲掉了 payload。
改成 BsData（Mu-Silicium 分支 `mh2lm-dtb-window`，e84e094）后第 10 条 = 0xD10343FF，正确。

**设备仓库不要放 `patches/xnu/` 目录**：format 1 下同名模块设备仓库优先，会整个替换 UniXNU 的 `patches/xnu/`。

拿到本地后：

```sh
unzip kernel-8796.zip -d /tmp/k8796
cd ref/UniXNU-src
# 1) 直接当 payload 的内核用（跳过 prelink）
python3 unixnu payload --kernel /tmp/k8796/mach.development.bcm2837.unstripped \
        -D ../UniXNU-mh2lm
# 2) 但它写的是 FAT32/整数 MiB —— B1 的 512 KiB FAT12 还没脚本，先手工做（见 NOTES.md B1）
```

## 这条 workflow 的边界（别误解）

- 产出的是 **UniXNU 主线风格的 4 KiB 内核**（无内置 HFS/AMFI、无 prelink）：
  - ✅ 可以冲 **M3**（内核入口、打印版本与 boot args、平台专家匹配 ADT）；
  - ❌ 到不了 **M4**（没有 Apple kext，也没有单体内核里的 HFS/AMFI/UFS）。
- 想要 **iOS 16 用户态**，内核必须走 cepheus 8796 那条**单体内核**线（内置 HFS/AMFI/pthread/UFS、
  iPhone X 身份、16 KiB 页）。那是另一条 workflow（`MACHINE_CONFIG=MH2LM` + 板级件替换），
  目前**还没准备**，因为要先做板级移植；见 `docs/notes/16-ios16-route.md` §16.3。
- prelink 那一步会**故意失败**（board.toml 没有 `[kernel.prelink]`，且 16.7.16 的 kernelcache 是
  `8796.142.1`、与源码 `141.3` 不同修订）。workflow 用 `|| true` 接住，再用 `test -f` 断言内核二进制存在。

### kernel_bootstrap 之后：用 boot-arg 选重启点（不用重编）

`osfmk/kern/startup.c` 的 `kernel_bootstrap_log()` / `kernel_bootstrap_thread_log()` 每次被调用时，
若参数等于 boot-arg `mh2lm_reset` 的值，就在 3 s 后 PSCI 重启。名字就是源码里传给这两个函数的字符串，
例如 `mh2lm_reset=vm_mem_bootstrap`、`mh2lm_reset=sched_init`、`mh2lm_reset=machine_init`，
也可以是 startup 子系统名（`kernel_startup_initialize_upto` 打印的那些）。
改 ramdisk 里 `EFI/UniXNU/unixnu.toml` 的 `args` 即可，不需要再跑 CI。

`PE_init_iokit()`（`pexpert/arm/pe_init.c`）里另有 6 个步骤名，同样用 `mh2lm_reset=` 选：
`iokit_entry` → `PE_init_printf(TRUE)` → `iokit_printf` → `pe_prepare_images()` → `iokit_images` →
`iokit_before_init` → `InitIOKit()` → `iokit_initiokit` → `ConfigureIOKit()` → `iokit_configured`。
2026-10-31 二分结果：卡点在 `PE_init_iokit()` 内部（见开发工作区 evidence/p3-bootstrap-bisect）。
二分到 `ConfigureIOKit()` → `IOPlatformExpertDevice::configureDefaults()`。其中再加了步骤名：
`pe_defaults_entry` → createNVRAM（`nvram_new` → init → `nvram_init` → attach → `nvram_attach` → start → `nvram_start`）
→ `pe_nvram_done` → serial-number → `pe_serial_done` → generatePlatformUUID → `pe_uuid_done`。

2026-10-31：二分到 `generatePlatformUUID()` → `SHA1Init` 时 `g_crypto_funcs` 为空（源码 corecrypto 在 EARLY_BOOT 才注册，晚于 PE_init_iokit）。
修复：`patches/xnu/source-corecrypto14-bootstrap.patch` 改为 `STARTUP(SYSCTL, STARTUP_RANK_LAST, ...)`。验证用 `mh2lm_reset=pe_uuid_done`。
更正：k8796q 里仍无 `_source_corecrypto14_bootstrap`——8796 的 MakeInc.def 不使用 `CFLAGS_EXTRA`，所有 `-DXNU_*` 被丢弃。新增 `patches/xnu/makeinc-cflags-extra.patch`。验证：`llvm-nm kernel | grep _source_corecrypto14_bootstrap` 应有，启动表符号 `___startup_SYSCTL_entry_source_corecrypto14_bootstrap_*`。

`PE_lockdown_iokit()` 之后的步骤名：`iokit_lockdown_entry` → `zalloc_iokit_lockdown()` → `iokit_lockdown_zalloc` → `StartIOKitMatching()`
→ `iokit_matching_started` → … → `bsd_init_entry` → `bsd_init()` → `bsd_init_done`。
`bsd_init()` 里原有的 `bsd_init_kprintf("calling xxx\n")`（35 处）也都是步骤名；boot-arg 里空格写成 `_`、末尾换行忽略，
例如 `mh2lm_reset=calling_vfsinit`、`mh2lm_reset=calling_setconf`、`mh2lm_reset=vfs_mountroot`。
