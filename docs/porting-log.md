# 移植日志 · LG G8 ThinQ（alphaplus / alphalm, SM8150）

按时间顺序记录每一次尝试、结果和踩到的坑。**只把亲眼看到的结果写成结论**；
推断的地方标明「推断」。2026-11-05 一日内的连续作业。

---

## 0. 结论摘要

| 环节 | 状态 | 证据 |
| --- | --- | --- |
| Bootloader 解锁 | 可用 | bootloader 界面 `DEVICE STATE - unlocked`；`fastboot getvar unlocked` = yes |
| `fastboot boot`（RAM 启动） | **不可用** | `Failed to load/authenticate boot image: Load Error` |
| `fastboot flash`（刷分区） | 可用 | 刷入 `boot_a` / `boot_b` 均 OKAY |
| A/B 切槽 | **不可用** | `set_active` 返回 `unknown command` |
| 第三方 UEFI 启动 | **可用** | Project-Aloha `lg-alphaplus_NOSB.img` 刷入后屏幕出 UEFI Shell，枚举 115 个分区 |
| 内核构建（arm64 XNU） | **可用** | CI 8m40s 全绿，产物 arm64 Mach-O |
| ADT 生成 | 可用 | `out.adt` 21,028 B |
| IPSW 输入 | 可用 | DeviceTree / kernelcache 的 sha256 与 pin 值逐位一致 |
| UniXNU 固件（含 DarwinBoot + payload） | **未完成** | uefi-sheng 无 alphaplus 平台包 |

---

## 1. 时间线

### 阶段 A · 资料核对（19:00 前后）

**A1 拉取两个来源**

- 目标：`github.com/oosexgang/hakios-xnu-kernel` 与 `hackios-web.vercel.app/en`
- 坑 1：本机 DNS 把 `github.com` / `*.vercel.app` 解析到 `198.18.0.x`（代理 fake-IP），
  内置抓取器判定「非公网 IP」直接拒绝；必须用 `curl.exe`。
- 坑 2：`git clone` 200 MB 仓库 30 秒只下到 0 MB → 改用 codeload tar 包（8.5 MB / 3.4 s）。
- 结果：`hakios-xnu-kernel/` 649 文件 25.9 MB；官网快照 7 页。

**A2 判定 HakiOS 不是本项目路线**

- HakiOS 真机端口只有 POCO X5 Pro（`redwood`, SM7325），SoC 家族表只有 `sc7280`。
- 新增 SoC 层等于从零写一层 SoC + 全套驱动。
- 附带推翻一个误解：**HakiOS 不要求 macOS**（Linux 用 theos + cctools 即可）；
  需要 macOS/Xcode 的是 UniXNU 的内核步骤。

**A3 找到可行路线**

- Project-Aloha `mu_aloha_platforms` 有 `Platforms/SurfaceDuo1Pkg/Device/lg-alpha`（含 ACPI / DTB / 内存映射）。
- 发布包 `lg-alphaplus_NOSB.img`（4.26 MB，Android boot 镜像，ramdisk 为空）现成可用。
- UniXNU `devices.toml` 的 SM8150 阵营：`cepheus`（小米 9）、`guacamole`（一加 7 Pro，已到
  iOS 16.7.16 用户态）、`raphael`、`nabu`、`flashlm`（LG V50）、`mh2lm`（LG G8X）——**没有 alphaplus**。

### 阶段 B · 设备接入（19:30–20:10）

**B1 设备身份**

```
ro.product.model   LM-G820        ro.product.device  alphalm
ro.build.version   9              ro.boot.hardware   alphalm
serial             LMG820UM40621c27
```

**B2 属性与「已解锁」的冲突**

- 属性显示 `flash.locked=1`、`vbmeta.device_state=locked`、`verifiedbootstate=green`、`warranty_bit=0`
  → 按属性判断是「未解锁」。
- 但 `su -c id` 返回 `uid=0(root)`、上下文 `u:r:magisk:s0`、`/sbin/su -> ./magisk` → Magisk 确实在。
- bootloader 界面随后确认 `DEVICE STATE - unlocked`。
- **结论**：这台机的 `ro.boot.*` 属性不可信（跨刷 `alphalm_lao_com` 固件 + 解锁方式不改这些位）。
  判定解锁状态只认 bootloader 界面和 `fastboot getvar`。

**B3 `adb reboot bootloader` 落到下载模式**

- 实测进入的是 LG Download 模式：`VID_1004&PID_633A`（LGE AndroidNet USB Modem + COM17），不是 fastboot。
- 必须手动：关机 → 按住音量下 → 插 USB。

**B4 fastboot 驱动（Windows 最大的坑）**

- 现象：手机已在 fastboot，但 `fastboot devices` 永远为空；设备管理器里
  `USB\VID_18D1&PID_D00D` 状态 `Error`、Problem `CM_PROB_FAILED_INSTALL`。
- Google USB Driver r13 的 `android_winusb.inf` **没有** `PID_D00D` 条目（只有 4E40/2C10/4EE0/9004/9006/4D00）。
- 解决：自写 INF 绑定 `USB\VID_18D1&PID_D00D` 到 inbox WinUSB，用自签证书签目录文件：
  `New-SelfSignedCertificate` → 导入 Root + TrustedPublisher → `New-FileCatalog` → `Set-AuthenticodeSignature`
  → `pnputil /add-driver /install`（落地为 `oem108.inf`）。
- 坑：第三方 INF 无签名直接被拒（`exit=-536870353`，提示「不包含数字签名信息」）。
- 副作用（需知悉）：本机受信任根里多了 `CN=Android Fastboot Test`；删掉它 fastboot 会重新认不到设备。

### 阶段 C · 启动链验证（20:10–20:40）

**C1 `fastboot boot` 被拒**

```
Sending 'boot.img' (4364 KB)  OKAY
Booting  FAILED (remote: 'Failed to load/authenticate boot image: Load Error')
```

- `unlocked: yes` 但 `secure: yes`：LG 的 abl 对**载入内存**的镜像做鉴权，解锁不解除这一条。
- 结论：HakiOS / UniXNU 默认的「只读 RAM、不写分区」模型在这台机上不成立。

**C2 分区与切槽**

```
current-slot a   slot-count 2   partition-size:boot_a 0x6000000 (96 MB)
fastboot --set-active=b  →  FAILED (remote: 'unknown command')
```

- 备用槽方案作废（abl 没实现 `set_active`），只能写活动槽 `boot_a`。

**C3 刷入 UEFI 并启动成功**

- `fastboot flash boot_a lg-alphaplus_NOSB.img` → OKAY（4364 KB / 0.19 s）
- `fastboot reboot` 回 OKAY 但设备仍停在 fastboot；**需长按电源 15 秒**才真正重启。
- 重启后屏幕出现 UEFI 输出：`BLK95`–`BLK115` 分区枚举 + UEFI Shell
  `ESC in 1 seconds to skip startup.nsh or any other key to continue.`
- **判定**：显示、UFS、GPT 解析、Shell 全部正常。平台层打通。

**C4 无输入设备**

- UEFI 起来后 USB 完全不枚举（无 fastboot / adb / 新串口）——UEFI 固件不带 USB device 模式，属正常。
- 手机无键盘、无 OTG 键盘 → Shell 无法交互，只能看它自动跑。

### 阶段 D · 恢复与资料化（20:40–21:00）

**D1 回到 Android**

- 长按电源 → 进系统；`adb devices` 变空，手机端需重新确认「允许 USB 调试」。
- 备份镜像校验：`magisk_patched-30600_mZhNS.img`，magic `ANDROID!`，64 MB，
  sha256 `46B6452D…29965`。

**D2 用设备自己的设备树钉死板级参数**

- 写 `scripts/fdt-probe.py`（无依赖 FDT 解析器），解析 `android-alpha.dtb`（499,866 B，`D00DFEED`，v17）：

| 节点 | 实际值 | 结论 |
| --- | --- | --- |
| 根 | `compatible = qcom,sm8150` | `board_compat` 确认 |
| `interrupt-controller@17a00000` | `0x17a00000 0x10000` + `0x17a60000 0x100000` | GIC 确认 |
| `ufshc@1d84000` | `0x1d84000 0x2500` + `0x1d90000 0x8000`（ICE） | UFS 确认 |
| `timer@0x17c20000` | `clock-frequency = 19200000` | timebase 确认 |
| `reserved-memory/disp_rdump_region` | `0x9c000000 + 0x2400000` | 与 UEFI 的 `Display Reserved 0x9D200000` 是两块，取后者 |

- 坑：`android-alpha.dtb` 的 `/memory` 是占位值 `0x0 0x0 0x0 0x0`，真实内存布局由 bootloader 运行时填。
- 补救：从真机读 `/proc/device-tree/memory/reg`，得到三段：
  `0x80000000+0x3cc00000`、`0xc0000000+0x80000000`、`0x140000000+0xc0000000`（合计 ≈5.95 GiB）。
  于是 `phys_base+mem_size = 0xC4000000+0x7C000000` 正好止于第三段起点，与 mh2lm 的窗口一致。

**D3 仓库与 CI 补丁**

- 以 `UniXNU-mh2lm` 为模板建 `unixnu-alphaplus`（format 1）。
- CI 补丁 `ci/0019-unixnu-8796-ci.patch` 里 113 处 mh2lm 痕迹**全部是调试仪表**
  （`mh2lm_probe_step`、`MH2LM_PROBE_*`），无硬件地址 → 机械改名 `mh2lm→alphaplus` / `MH2LM→ALPHA`。
- 校验：改后仍 1789 行；内层 hunk `@@ -0,0 +1,564 @@` 的 564 行全以 `+` 开头，结构未破。
- 改写 `AGENTS.md`：原模板写着「只 `fastboot boot`，不写任何分区」，在本机是死规则。

### 阶段 E · 推送到 GitHub（21:00–21:10）

- `gh` 未安装、`winget` 不可用 → 下 `gh_2.103.3_windows_amd64.zip`；
  下载被截断两次（5.1 MB → 8.5 → 11.2 → 14.5 MB），靠 `-C -` 续传凑齐。
- 设备码授权第一次成功；推送被拒：
  `refusing to allow an OAuth App to create or update workflow ... without 'workflow' scope`
  → `gh auth refresh --scopes workflow` 再授权一次。
- 坑：`gh repo create` 报 `Post "https://api.github.com/graphql": unexpected EOF`，
  但**服务端其实已创建**；再建报 422 `name already exists`。API 响应丢失不等于动作失败。
- 仓库：`https://github.com/cocopaim15/UniXNU-alphaplus`（Public，免费 macOS runner）。

### 阶段 F · 内核 CI（21:10–21:45）

- run `42031781958`，**8 分 40 秒**，13 步全绿。
- 关键校验点：`probe sites in start.s: 8 bars, 4 reset` → 改名后的 `ALPHA_PROBE_*` 正确进入 `start.s`。
- 日志里有一次 `LD ... Error 1`（13:04:04）后 13:06:46 重试成功——XNU 构建末段的已知不稳定，
  workflow 按「实际失败点」而非退出码判定，未误判。
- 产物 59.3 MB，下载 **约 43 KB/s**；4 路并发被服务端挂起（4 个 part 全 0 字节），只能单路；
  中途 `-C -` 续传遇到签名 URL 失效会从头开始（文件从 25 MB 归零到 1.7 MB）。
- 产物校验：`CF FA ED FE` + `0x0100000C` = arm64 Mach-O，19.62 MB。

### 阶段 G · IPSW 与 ADT（21:45–22:20）

- Apple CDN 实测 **9.71 MB/s**（与 GitHub 形成鲜明对比）；5.75 GB 约 10 分钟。
- 坑：清理「僵尸 curl」时按启动时间误杀了正在跑的 IPSW 下载（停在 4.11 GB），用 `-C -` 续上。
- 校验：`DeviceTree.d22ap.im4p`（33,719 B）sha256 `480E8B08…A6368`、
  `kernelcache.release.iphone10b`（17.36 MB）sha256 `2D6A13D0…AAEC`，**与 `board.toml` pin 完全一致**。
- 坑：`adt.py` 直接调 `lzfse` 命令行，Windows 没有 → 装 `pip install lzfse`，
  改脚本优先用模块、命令行兜底（提交 `e2d2f46`）。
- 产出：`base-d22ap.adt` 186,084 B；`out.adt` 21,028 B。

### 阶段 H · 固件构建尝试（22:20–23:10）

**H1 WSL 环境**

- 初次 `wsl` 失败：`Wsl/Service/CreateInstance/CreateVm/HCS/HCS_E_SERVICE_NOT_AVAILABLE`
  → 用户开启虚拟化后恢复。
- 无 root：用 `apt-get download mtools` + `dpkg-deb -x` 解到 `~/local/mtools`。

**H2 WSL 无外网**

- Clash Verge 配置 `mixed-port: 7897` / `allow-lan: false`，但本机 7897 **没有监听**（核心以 TUN 方式转发）。
- 试过 `netsh portproxy` + 防火墙放行，Windows 侧自己也连不通 → 判定无 HTTP 代理可借，
  规则已全部删除（`portproxy` 与防火墙规则均清理）。
- 用户开 VPN 后 WSL 直连恢复（`https=200`、`git ls-remote` 正常）。

**H3 git 与 tarball**

- `git clone` 反复 `GnuTLS recv error (-110)`；`--filter=blob:none` 更糟（checkout 时拉 blob 也断）。
- 可行做法：codeload tar 包 + `curl`（`2.4 MB` 完整，`gzip -t` 通过，1148 条目）。
- 注意：**当前 main 已经和 `40d21cc` 分叉**，补丁套不上（`kernel.py`、`build-xnu-4k-baseline.sh` 冲突），
  必须取那个 commit 的 tar 包。

**H4 固件 CI 两轮失败（关键发现）**

- 第一轮：用 Project-Aloha `mu_aloha_platforms` 当 `--uefi` →
  `unixnu: ... /uefi is not a Mu-Silicium checkout`。
- 根因：`unixnu firmware` 读 `uefi/Resources/Configs/<board.firmware.config>.toml`，
  那是 **`UniXNU/uefi-sheng`** 的结构，不是 Aloha 的。
- 第二轮改用 `uefi-sheng`，submodule 名不对：
  `error: pathspec 'MU_BASECORE' did not match any file(s) known to git`
  → uefi-sheng 的实际 submodule 是 `Binaries`、`Common/Mu`、`Common/Mu_OEM_Sample`、
  `Mu_Basecore`、`Silicium-ACPI`、`Silicon/Silicium/OpensslPkg/Library/OpensslLib/openssl`。
- 结构性结论：**uefi-sheng 按机型分包**（`Platforms/LG/mh2Pkg/mh2.dsc` 等），
  `Resources/Configs/` 里也没有 alphaplus → 这台机没有平台包，固件无从构建。

**H5 平台包底稿盘点（结论：零件都在，但分散在两套仓库里）**

`uefi-sheng` 里 LG 目录只有一份：`Platforms/LG/mh2Pkg`。读它的 `mh2.dsc` 可以确认
**它就是 LG G8X ThinQ**：

```
gSiliciumPkgTokenSpaceGuid.PcdSmbiosSystemModel|"G8x ThinQ"
gSiliciumPkgTokenSpaceGuid.PcdSmbiosSystemRetailSku|"LM-G850EMW"
gSiliciumPkgTokenSpaceGuid.PcdSmbiosSystemBoardModel|"mh2lm"
```

它的内存映射里 `Display Reserved` 同样是 `0x9D200000 + 0x01200000`，与 `lg-alpha` 一致；
但三处必须改：

| 项 | mh2（G8X） | alphaplus（G8） | 来源 |
| --- | --- | --- | --- |
| Kernel 段 | `0x80000000 + 0x00600000` | `0x80000000 + 0x02A00000` | lg-alpha MemoryMapLib |
| UEFI FD | `0xA0000000 + 0x00300000` | `0x9FC00000 + 0x00300000` | 同上 |
| 面板 | 1080 × 2340 | 1440 × 3120 | 硬件规格 |

`mh2Pkg` 只有 11 个文件（`dsc` / `fdf` / `dec` / `DeviceBuild.py` / `Include/*.inc` /
两个 Library），体量很小，克隆改造成本可控。

但它引用 `mh2/AcpiTables.inf`，该文件不在 uefi-sheng 里，而在 submodule
`Project-Silicium/Silicium-ACPI` 中：

```
Platforms/LG/mh2/AcpiTables.inf
Platforms/LG/mh2/DSDT.aml
Platforms/LG/mh2/Decompiled/DSDT.dsl
```

该仓库的 LG 目录**只有 mh2**，没有 alpha。也就是说 alphaplus 缺的是 **ACPI 表（DSDT）**，
不是几行配置。

好消息：Project-Aloha 的 `mu_aloha_platforms` 里**存在**
`Platforms/SurfaceDuo1Pkg/Device/lg-alpha/ACPI/DSDT.aml`。所以可用零件是齐的，
只是分布在两套结构不同的仓库里（Aloha 的 `Device/<name>` vs uefi-sheng 的
`Platforms/<Vendor>/<name>Pkg` + `Silicium-ACPI/Platforms/<Vendor>/<name>`）。

---

## 2. 坑位速查

| # | 现象 | 根因 | 处置 |
| --- | --- | --- | --- |
| 1 | 抓取器报「非公网 IP」 | 代理 fake-IP（198.18.x） | 用 `curl.exe` |
| 2 | `git clone` 卡死 / TLS 断 | 链路对长连接不稳 | codeload tar 包 + `curl` 续传 |
| 3 | 大文件下到一半「成功」 | 服务端 `close_notify` 缺失 | 下完必须做完整性校验（gzip/tar/sha256） |
| 4 | `fastboot devices` 永远空 | Windows 无 `18D1:D00D` 驱动 | 自签 INF + 目录签名 + `pnputil` |
| 5 | `adb reboot bootloader` 进下载模式 | LG 原厂 abl 行为 | 关机 → 音量下 → 插线 |
| 6 | `fastboot boot` 失败 | abl 对 RAM 启动鉴权 | 只能 `flash` 分区 |
| 7 | `set_active` unknown command | abl 未实现 | 只写活动槽 |
| 8 | `fastboot reboot` 不生效 | 该 abl 行为 | 长按电源 15 秒 |
| 9 | `adb pull` 得到 0 字节 | 目标路径含中文 | 先拉到 `%TEMP%` 再复制 |
| 10 | 属性说 locked 但有 root | 跨刷固件 + 解锁方式不改属性位 | 以 bootloader 界面 / `getvar` 为准 |
| 11 | CI 步骤显示成功但实际失败 | `cmd \| tee log` 取的是 tee 的退出码 | 去掉 `tee` 或加 `set -o pipefail` |
| 12 | PowerShell 变量后接冒号报错 | `"$store: x"` 被当作用域 | 写 `${store}` |
| 13 | 中文路径 / 特殊字符命令被拒 | 工具层解析问题 | 拆成多条简单命令 |

---

## 3. 下一步（按依赖排序）

1. 新建 `Platforms/LG/alphaplusPkg`：从 `mh2Pkg` 复制 11 个文件，改
   `PLATFORM_NAME` / `PLATFORM_GUID` / `OUTPUT_DIRECTORY` / `FLASH_DEFINITION` /
   SMBIOS 串 / 面板分辨率；`MemoryMapLib.c` 的 Kernel 段与 UEFI FD 段按上表改。
2. 新建 `Silicium-ACPI/Platforms/LG/alphaplus/`：`AcpiTables.inf` 从 `mh2` 抄，
   `DSDT.aml` 取自 Aloha 的 `Device/lg-alpha/ACPI/DSDT.aml`。
3. `Resources/Configs/alphaplus.toml` 已有草稿（本仓库 `firmware/alphaplus.toml`，
   FD base 已按 `0x9FC00000` 填好）。
4. 修正 `board.toml` 的 `[firmware]`：`dsc` 指向 `alphaplusPkg/alphaplus.dsc`，
   `submodules` 换成 uefi-sheng 的实际名称（`Mu_Basecore` / `Common/Mu` / …），
   `fd` 换成 `Build/alphaplusPkg/{target}_CLANGPDB/FV/*.fd`。
5. 固件构建成功后用 `unixnu bootimg` 打包，`fastboot flash boot_a` 验证。
6. 只有到第 5 步才需要手机进 fastboot。

判断：第 1–4 步是**有底稿的移植工作**（不是配置微调），每步都能在免费 CI 上跑通再前进；
第 5 步才回到手机上。

---

## 4. 平台包骨架（2026-11-05 收尾时）

- 已把 `mh2Pkg` 的 11 个文件复制并机械改名为 `firmware/uefi/Platforms/LG/alphaplusPkg/`
  （overlay 目录，CI 构建前覆盖进 uefi-sheng 检出）。
- 已改：`PLATFORM_NAME=alphaplus`、`OUTPUT_DIRECTORY=Build/alphaplusPkg`、
  `FLASH_DEFINITION=alphaplusPkg/alphaplus.fdf`、文件名 `alphaplus.{dsc,fdf,dec}`。
- 未改（见 `firmware/uefi/README.md`）：`MemoryMapLib.c` 的 Kernel / UEFI FD 段、
  SMBIOS 串、以及缺失的 ACPI 表。
- 停在这里的理由：`MemoryMapLib` 的抽象与 Aloha 的不同（`EFI_MEMORY_REGION_DESCRIPTOR`
  vs `ARM_MEMORY_REGION_DESCRIPTOR_EX`），必须逐字段搬运；硬拼会得到能编译但内存映射错误的固件，
  而错误的内存映射在真机上表现为随机死机——比构建失败更难查。

---

## 5. 固件构建打通（2026-11-06 凌晨）

把上面三处补完之后，固件在免费 CI 上一轮一轮往前拱，每次失败只暴露一个具体缺口。
**这一节就是那九轮的真实顺序**，以后复现照这个清单走：

| 轮 | 报错 | 修法 |
| --- | --- | --- |
| 1 | `uefi ... is not a Mu-Silicium checkout` | `--uefi` 要用 `UniXNU/uefi-sheng`，不是 Project-Aloha |
| 2 | `pathspec 'MU_BASECORE' did not match` | submodule 名换成 uefi-sheng 的（`Mu_Basecore` / `Common/Mu` …） |
| 3 | `lld-link not found on PATH` | `apt install lld clang llvm` |
| 4 | `HanaPkg/HanaPkg.dsc.inc` 找不到 | PACKAGES_PATH 加 `{uefi}/Silicon/Qualcomm`、`{uefi}/Silicon/Silicium` |
| 5 | `alphaplusPkg/alphaplus.fdf` 找不到 | 加 `{uefi}/Platforms/LG` |
| 6 | `MsCorePkg/...` 找不到 | 加 `{uefi}/Common/Mu`、`Mu_Basecore`、`Common/Mu_OEM_Sample` |
| 7 | `Binaries/alphaplus/QcomPkg/...` 找不到 | `Device-Binaries` 无 alphaplus，**借 G8X(mh2) 的驱动包**并改名 |
| 8 | `Common/SSDT.aml`、`Hana/*.aml` 找不到 | 加 `{uefi}/Silicium-ACPI` 与 `{uefi}/Silicium-ACPI/Silicon/Qualcomm` |
| 9 | `#if ENABLE_SECUREBOOT == 1` 预处理报错 | `[firmware.defines] ENABLE_SECUREBOOT = "0"` |

修完第 9 轮后：**固件编出来了** —— `Build/alphaplusPkg/DEBUG_CLANGPDB/FV/SILICIUM_UEFI.fd`。

接着补打包链：

| 轮 | 报错 | 修法 |
| --- | --- | --- |
| 10 | `invalid compiled device tree` | Aloha 的 `android-alpha.dtb` 是**四段拼接**（文件 1,974,927 B，首段 totalsize 499,866），切出第一段 |
| 11 | `the payload files take 19 MiB; raise size_mib (now 1)` | `[payload] size_mib = 32`（19 MiB 内核；1 MiB 是给 FV 内嵌场景的） |

最终产物（run `42061796622`，全绿）：

```
boot-alphaplus.img   33.52 MB   magic ANDROID!
  kernel   1,591,726 B @ 0x8000     (3 MiB UEFI FD，gzip)
  ramdisk 33,554,432 B @ 0x800000   (32 MiB payload：kernel.macho + adt + unixnu.toml)
  page 4096   sha256 0244AC60…66DD
```

对照之前成功启动过的 Aloha 镜像：`kernel_addr=0x8000`、`tags_addr=0x100`、`page=4096` 完全同类
（Aloha 的 `ramdisk_addr=0x1000000`，我们 0x800000，同为低地址偏移量级）。

**尚未在真机验证。** 刷写步骤见下一节。

## 6. 待做：真机验证

```sh
# 手机：关机 → 按住音量下 → 插 USB
fastboot devices
fastboot flash boot_a boot-alphaplus.img
# 长按电源 15 秒重启（该 abl 的 fastboot reboot 不生效）
```

回滚（`boot_a` 的备份已校验，magic `ANDROID!`，64 MB）：

```sh
fastboot flash boot_a magisk_patched-30600_mZhNS.img
```

看屏幕：出现 UniXNU 菜单 = 启动链打通；黑屏/循环则按 porting-log 第 2 节的坑位表逐项查
（内存映射、FD 基址、DTB 变体、gzip 内核是否被 abl 解压）。

---

## 7. 真机验证：失败，以及把范围缩到 FV

镜像构建全绿并不等于能启动。刷入后的十几次迭代如下（每次都是
`fastboot flash boot_a` → 长按电源 → 观察，因为该 abl 的 `reboot` 不生效）：

| 变量 | 结果 |
| --- | --- |
| gzip 内核 + 32 MiB payload | 自动回 fastboot |
| 未压缩内核 + payload | 自动回 fastboot |
| 未压缩内核，无 payload | 自动回 fastboot |
| 完整四段 DTB 代替首段 DTB | 自动回 fastboot |
| **对照：Project-Aloha 预编译镜像** | **正常启动，屏幕刷出 UEFI 代码** |
| UEFI 栈从 G8X 的 `0xA0300000` 挪到映射内的 `0x9FFB0000` | 自动回 fastboot |
| 换成 Aloha 的 G8 原生驱动包（弃用借来的 G8X 包） | 自动回 fastboot |
| **混合：Aloha 的 shim + 我们编的 FD** | 自动回 fastboot |

两个关键结论：

1. **手机和刷写通路都是好的** —— 对照组每次都能启动到 UEFI。
2. **问题在 FV 内部，不在 shim、不在 payload、不在 DTB、不在内核编码** ——
   混合镜像（已知能启动的 shim 配我们的 FD）同样失败，把范围彻底钉在 FV 上。

结构性对比（本地解析）：两边 FV 都合法（`_FVH`、3 MiB、header 长度 72），
但**第一个 FFS 模块（type 0x03，SEC/PEI core）的 GUID 不同**：

```
aloha  3e401783-94cc-cd4f-97bc-bd35ac369d2f
ours   9affb503-e643-4141-8b90-17e8588b1d35
```

这意味着两边早期引导模块不是同一个构建产物，而我们没有串口/调试输出能看到它死在哪一步。

**这一轮到此为止**：继续换零件属于盲调，收益低于成本。手机已刷回 Magisk 备份的
`boot_a`，可正常回到 Android。

## 8. 下一步（按性价比排序）

1. **改用 Project-Aloha 自己的构建系统产出 FV**。他们的发布产物在本机实测能启动，
   说明那套 `build_setup.sh` + Dockerfile + 他们的 lg-alpha 设备目录是自洽的；
   `uefi-sheng` 那条路虽然能编出 3 MiB 的 FD，但早期模块组合显然不对。
   拿到能启动的 FV 之后，再把 UniXNU 的 `DarwinBoot` 与 payload 注入进去。
2. **先拿到串口输出再谈调 FV**。Mu 在 AARCH64 上可以在 PEI 早期就把日志写到一个固定的
   RAM 缓冲；没有串口时至少可以用「崩溃后由 abl 保留的内存」或测试点 UART，
   否则任何修复都只是猜。
3. 若 1 顺利，再回来解决 payload 的加载方式（FV 内嵌 512 KiB FAT12 或 disk 模式）。

## 9. 改用 Aloha 的构建系统，并把 UniXNU 放进去（2026-11-06 晚）

按第 8 节第 1 条走完：FV 换成 Project-Aloha 自己那套构建的产物，UniXNU 的四个
模块编进同一个卷。**产物已就绪，尚未上机。**

### 9.1 先补一个结构差异（这次的新证据）

把两边的 FD 解到文件级再对比，差异比第 7 节记的更具体：

| | Aloha `lg-alphaplus_NOSB.img` | 我们的 `boot-alphaplus.img` |
| --- | --- | --- |
| SEC | `3e401783-94cc-4fcd-97bc-bd35ac369d2f`，64,952 B，`ArmPlatformPrePiUniCore` | `9affb503-e643-4141-8b90-17e8588b1d35`，69,560 B，`SiliciumPkg/Sec` |
| `uefiplat.cfg` | 有（11,153 B，FFS 类型 0x02） | **没有** |
| DXE 卷（LZMA） | 16,228,352 B 解压后，2.4 MB 压缩 | 7,012,360 B，1.06 MB 压缩 |

也就是说：不只是「早期模块 GUID 不同」——他们的 SEC 里带着 `uefiplat.cfg` 的解析
（`EnableDisplayImageFv`、`UfsSmmuConfigForOtherBootDev`、`SEC Heap`、`UEFI Stack`
这些串都在 SEC 里），我们那版 SEC 走的是 Silicium 自己的配置路径，没有这份平台配置。
这条不影响「能不能启动」的最终结论（混合镜像照样失败），但解释了为什么两块 FV
不是同一个东西。

### 9.2 在本机把那套构建跑起来

他们的 CI 入口是 `./build_uefi.py -d lg-alpha` → `PlatformBuildNoSb.py`（stuart）。
stuart 的 `--init/--update` 要从 GitHub release 拉 `Mu-Basetools`、`OneCrypto`、
`Mu_CryptoBin`（合计 300 MB 级），本机对 release 资产整段 reset，只有 codeload 和
api.github.com 通。

改走 BaseTools 直编，九处坑按出现顺序：

| 轮 | 现象 | 处置 |
| --- | --- | --- |
| 1 | `SHARED_CRYPTO_PATH not defined` | 该变量由 stuart 从加密包设；改成从发布 FD 里取出 `BaseCryptoDriverDxeAARCH64`（900 KB）当 `FILE DRIVER` 用 |
| 2 | `BaseCryptLib not found` | 映射到 `CryptoPkg/Library/BaseCryptLibOnProtocolPpi/`（协议客户端，运行时由上面那个驱动提供） |
| 3 | `SurfaceDuoACPI/QcomACPI/8150/...` 找不到 | `QcomACPI` 是嵌套子模块（`acpi_oem_qcom_common_downstream`），没在顶层 `.gitmodules` 里 |
| 4 | zlib `adler32.c` K&R 定义被 `-Werror` 拦 | `zlib.inf` 加 `-Wno-deprecated-non-prototype` |
| 5 | `duplicate symbol: DefaultExceptionHandler` | CpuDxe 同时挂了 ArmPkg 与 MsCorePkg 两份异常处理库，去掉 MsCorePkg 那份 |
| 6 | `UefiRuntimeLib` 不支持 `DXE_DRIVER` | 去掉 `SecurityStubDxe` 的 `DxeImageVerificationLib`；NetworkPkg 从 `[Components]` 拿掉（FDF 本来就没放） |
| 7 | `undefined symbol: __stack_chk_guard` | `CUSTOM_STACK_CHECK_LIB=STATIC`；SEC 另外给 `SecStackCheck.c` 两个符号 |
| 8 | `llvm-objcopy: too many positional arguments` | Mu 把 `OBJCOPY_FLAGS` 写成占位文字，SEC/PEIM 规则仍然执行它——本地 `Conf/build_rule.txt` 删掉那一行 |
| 9 | `GenSec: Error opening file ... linux-$(FDT)` | `-D FDT=alpha.dtb`（平时由 stuart 设） |

跑通后：`Build/SurfaceDuo1Pkg/RELEASE_CLANGDWARF/FV/SM8150_EFI.fd`，3,145,728 B，
FVMAIN_COMPACT 69% 满。**SEC 的 FILE_GUID 与发布镜像一致**，`uefiplat.cfg`、
`BaseCryptoDriverDxeAARCH64`、`EdkShell`、`BdsDxe`、`UFSDxe` 都在——结构上复现了
他们的卷。

复现脚本与完整补丁清单：`firmware/aloha/`（`README.md` + `apply-patches.py`）。

### 9.3 把 UniXNU 放进去

四个模块编进 DXE 卷：

| 模块 | 作用 |
| --- | --- |
| `UniXNURamDiskDxe` | 把 Android initrd（`payload.img`，FAT32）发布成只读块设备 |
| `UniXNUDxe` | 在 FV 里找到 `UniXNU.efi`，注册 `Boot####` 并排到 `BootOrder` 最前 |
| `UniXNU.efi` | 菜单、配置解析、把 `xnu` 条目交给装载器 |
| `DarwinBoot` | Mach-O 校验、`DARWIN_BOOT_ARGS`、跳 EL1 |

**关键的一处平台改动**：`UniXNURamDiskDxe` 从 HOB `DAEE82E6-8090-4E72-BFB9-78C13CD4E359`
读 x0（启动器传进来的设备树指针），而 Aloha 的 PrePi（`AndromedaPkg/PrePi`）不建这个
HOB。补法是两行汇编 + 一段 C：入口把 x0（`x10`）存进 `mBootDtb`，PrePi 建内存 HOB 之后
用同一个 GUID 把它发出去。`/chosen/linux,initrd-start` 由 abl 在装载 ramdisk 时写进
那棵树，所以 payload 能被发现。

### 9.4 产物

```
boot-unixnu.img   37,687,296 B   magic ANDROID!
  kernel   4,125,096 B @ 0x8000 = gzip(BootShim 112 B + FD 3 MiB) + DTB 1,974,927 B
  ramdisk 33,554,432 B @ 0x1000000 (payload：unixnu.toml + kernel.macho + adt)
  page 4096  tags 0x100
```

payload 卷标 `ALPHASP`，内容与 `unixnu payload` 的目录布局一致
（`/EFI/UniXNU/unixnu.toml`、`Payloads/kernel.macho{,.adt}`）。内核参数沿用
`board.toml` 的 `debug=0xc serial=3 cpus=8 keepsyms=1 rd=ufsroot0 wdt=-1`。

### 9.5 下一步

1. `fastboot flash boot_a boot-unixnu.img` → 长按电源 → 看屏幕。这一步要人把机器
   切到 fastboot（关机 → 音量下 → 插线）。
2. 屏幕出现 UniXNU 菜单 = 固件卷 + payload 发现 + 菜单三件事同时成立；
   直接进 Aloha 自己的菜单/Shell = `MsBootPolicy` 覆盖了 `BootOrder`，要把它摘掉；
   黑屏/回 fastboot = 固件卷本身还没起来，回到第 9.2 节的差异继续查。
3. 菜单里选 XNU 之后：绿条 = 进了 `DarwinEnter`；`DARWINBOOT: command line:` 出现在
   屏幕 = 装载器走到了 handoff；panic = 内核阶段的活，和第 7 节不是同一个问题了。

回滚镜像仍是 `magisk_patched-30600_mZhNS.img`（`boot_a`，已校验）。

## 10. 真机跑通到 DarwinBoot（2026-11-06 深夜）

第 9 节的产物刷进真机后，一轮一轮把链路推到了 **DarwinBoot 的最后一步**。
现在每次重启不需要 9008：没有输入时 60 秒倒计时会自己擦掉 `boot_a` 进 fastboot。

### 10.1 屏幕上的里程碑

| 现象 | 含义 |
| --- | --- |
| Aloha 开机 logo → 扳手二维码页 | 固件起来了，BDS 找不到可启动项（`BootFailIndicator`） |
| `UniXNU version 0.1.0` + 菜单 | 固件卷 + UniXNU 正常 |
| `config: \EFI\UniXNU\unixnu.toml` + `LG G8 – XNU` 条目 | payload 卷被发现 |
| 选 XNU 后出现 `MARK macho entry …` | DarwinBoot 已经在读内核 |

### 10.2 四个关键结论

1. **payload 必须用 4096 字节扇区的 FAT。** 页脚实测 `bs4k 115 bs512 0` —— UFS 的
   逻辑块是 4096 字节，512 字节扇区的 FAT16/FAT32 一律挂不上（`fs 6 efi 0 cfg 0`）。
   用 `mkfs.vfat -F 16 -S 4096 -s 1` 做 64 MiB 卷、整卷刷进 `boot_b`（无分区表），
   才出现 `fs 7 efi 1 cfg 1`。
2. **ramdisk 这条路走不通。** `UniXNURamDiskDxe` 读到的 x0 = `0x81000000`，但
   `0x80000000–0x82A00000`（Kernel 段）整段扫不到 FAT 引导扇区；4 MiB ramdisk 能
   启动、32 MiB 直接黑屏。abl 并没有把 initrd 放到我们能找到的地方。
3. **按键要直接轮询设备。** 菜单原来等 `gST->ConIn->WaitForKey`，在这台机器上永远
   不触发；改成每 100 ms 轮询所有 `EFI_SIMPLE_TEXT_INPUT(_EX)_PROTOCOL` 后，
   音量上/下 = `SCAN_UP`/`SCAN_DOWN`（0x01/0x02），电源键 = `scan=0x0102`，
   任意非方向键当确认。
4. **进 fastboot 不用 9008 了。** 菜单里有 `Erase boot_a (fastboot)` 动作；把它设成
   内置配置以及 payload 配置的默认项（倒计时 20/60 s），无人值守启动会自动擦掉
   `boot_a` 并重启进 fastboot。内置配置解析完会被 `Config->DefaultIndex = 0` 覆盖，
   这一行要删掉，否则默认项永远是第一条。

### 10.3 DarwinBoot 卡在哪

给 DarwinBoot 加了直接写 framebuffer 的阶段标记（`Mark()` + `DiagDraw()`），
一次启动看到的顺序是：

```
MARK macho entry FFFFFFFF0073F1488   mach-O 解析通过（虚拟 entry）
MARK window A0004000                 窗口分配在 0xA0004000
MARK copied F68000                   段拷贝完成（用了 16.1 MiB）
MARK args A0F64000                   boot_args 地址
MARK payloads F68000                 树/信任缓存/附加件拷贝完毕
MARK map 1A70                        GetMemoryMap 返回 0x1A70 字节
（之后停住，按键无响应，不再出 EBS/jumping）
```

也就是说：**内核读入、Mach-O 校验、窗口分配、段拷贝、ADT 组装都过了，卡在
`ExitBootServices` 之前**。已排除的：控制台 `Print`（quiet 版把交接前的打印全删了，
现象不变）、FAT 卷 `Root->Close`（跳过它，现象不变）。

### 10.4 交接成功：已经跳进内核（当晚最后一段）

把标记换成整屏色块（红 = 进 `GetMemoryMap`，绿 = map 返回，蓝 = `ExitBootServices`
返回，白 = 即将跳内核），第一次就看到 **红→绿→蓝→白 一闪而过**，屏幕最后停在
「彩条 + 下半屏白色」——**`ExitBootServices` 其实一直是成功的**。

之前几次「停在 exit boot」的真因是探针自己：`Mark()/MarkColor()` 里又调了
`gBS->LocateProtocol`，而 `ExitBootServices` 之后 boot services 已经不存在，
那个调用把装载器直接带崩。把 framebuffer 信息在 EBS 之前缓存到全局后，
探针不再碰 `gBS`，链路一次走通。

现在的状态：**固件 → UniXNU → payload → DarwinBoot → ExitBootServices → 跳 EL1
内核入口** 全部完成，屏幕不再返回菜单。剩下的全在 XNU 内部（页表/串口/显示初始化），
与本仓库的固件部分已经不是同一个问题。

### 10.5 复现材料

`firmware/aloha/patches/` 里是这一轮的全部脚本：

* `wsl-fwbuild.sh`、`wsl-integrate-unixnu.py` —— 构建与 UniXNU 集成；
* `UniXNURamDiskDxe.c` —— 重写后的 initrd/FAT 探测驱动（带状态变量）；
* `wsl-patch-pollkeys.py`、`wsl-patch-keydebug.py` —— 按键轮询与键码显示；
* `wsl-patch-erase-action.py`、`wsl-patch-autowipe.py`、`wsl-patch-keepdefault.py`
  —— `Erase boot_a` 动作、默认项与倒计时；
* `wsl-patch-darwinboot-*.py` —— 阶段标记、返回码、quiet 交接；
* `wsl-pack-4k.sh`、`wsl-pack-payload2.sh` —— 4096 字节扇区 payload 与启动镜像。

## 11. 内核确实在跑：九条色带，以及一条不用重编的定位链（2026-11-07）

第 10 节把链路推到了「跳 EL1」，但那一步的证据只有 DarwinBoot 自己刷的白色整屏——
白色只说明装载器*打算*跳。这一节补上跳过去之后的证据。

### 11.1 屏幕上的九条色带是内核画的

`024.jpg`（2026-11-06 23:27 实拍）：最上 1/16 是**绿**，往下依次
**红、橙、黄、白、青、蓝、品红、灰**，下半屏白。这两套色带来自两个不同的地方，
叠在一起正好构成一次完整交接：

| 带 | 颜色 | 画它的是谁 | 位置 |
| --- | --- | --- | --- |
| 0 | 绿 | `DarwinBootPkg/Driver/Entry.S` 的 `DarwinEnter` | `br x1` 之前的交接标记 |
| 1 | 红 | `start.s` `ALPHA_PROBE_BAR` | `start_first_cpu` 入口 |
| 2 | 橙 | 同上 | `DAIFSet` 关中断后 |
| 3 | 黄 | 同上 | 装 `LowExceptionVectorBase` 后 |
| 4 | 白 | 同上 | 读完 boot args 后 |
| 5 | 青 | 同上 | 异常栈、中断栈建好后 |
| 6 | 蓝 | 同上 | bootstrap 页表建好后 |
| 7 | 品红 | 同上 | TCR、TTBR0/1、MAIR 配好后 |
| 8 | 灰 | 同上 | 最终异常向量装好、`msr SCTLR_EL1` 之前 |

色带只存在于内核代码里（`grep -rn FF00FF00 DarwinBootPkg` 只有 Entry.S 的绿带），
而且每条都靠 `boot_args` 的 `Video.v_baseAddr(0x28)` / `v_rowBytes(0x38)` /
`v_height(0x48)` 定位——所以它们出现同时证明三件事：

1. EL1 内核真的在执行；
2. `boot_args` 的 Video 段版式被内核接受（位置、步长、高度都对）；
3. 内核走完了 `start.s` 的整套前期（异常向量、boot args、栈、bootstrap 页表、
   TCR/TTBR/MAIR），**停在打开 MMU 的那条指令之前**。

第 4 节第 1 条的验收（「屏幕出现内核画的可见内容」）到这里成立。
第 2 条的「把白色标记改成洋红」也就没有必要了：白屏分不清跳没跳，色带能。

### 11.2 载荷里的内核身份

| 位置 | 文件 | 大小 | MD5 |
| --- | --- | --- | --- |
| CI 产物 `kernel-8796.zip` | `kernel/mach.development.bcm2837` | 15,249,320 | `4465ccc7bd72ba2274bfa86eeab32e6d` |
| 同上 | `kernel/mach.development.bcm2837.unstripped` | 20,575,800 | `33d44cb18aa5a11f54d7e5580d920db1` |
| payload `boot_b`（`part4k3.img`） | `EFI/UniXNU/Payloads/kernel.macho` | 15,249,320 | `4465ccc7bd72ba2274bfa86eeab32e6d` |

真机上跑的这份内核就是带 `zzzz-alphaplus-early-boot-probes.patch` 的那一次 CI 产物，
所以 11.1 的色带与源码逐条对得上。

### 11.3 内核里还留着一个不用重编的探针：`alphaplus_reset=`

同一份内核里有 `alphaplus_probe_step()`（`osfmk/kern/startup.c`），
`bsd_init_kprintf`、`PE_init_iokit`、`IOPlatformExpertDevice::configureDefaults`
以及 `kernel_bootstrap{,_thread}_log` 每次被调用都会把它带上步骤名。
当 boot-arg `alphaplus_reset=<步骤名>` 与之匹配时，它就等
`ALPHA_PROBE_RESET_SECONDS`（3 秒）再走 PSCI `SYSTEM_RESET`。

于是**任意一个运行期可达的步骤都变成一个可见的重启**，不用重编内核：

```
色带之后约 3 秒自动重启（再出 Aloha logo）  = 走到了这一步
色带一直停着、10 秒以上没动静               = 死在更早的位置
```

可用的步骤名（已在内核字符串表里逐个确认存在）：

| 来源 | 步骤名 |
| --- | --- |
| `kernel_bootstrap` / `_thread` | `vm_mem_bootstrap`、`sched_init`、`machine_init`、… |
| `PE_init_iokit` | `iokit_entry`、`iokit_printf`、`iokit_images`、`iokit_before_init`、`iokit_initiokit`、`iokit_configured` |
| `PE_lockdown_iokit` | `iokit_lockdown_entry`、`iokit_lockdown_zalloc`、`iokit_matching_started` |
| `configureDefaults` | `pe_defaults_entry`、`nvram_new`、`nvram_init`、`nvram_attach`、`nvram_start`、`pe_nvram_done`、`pe_serial_done`、`pe_uuid_done` |
| `bsd_init` | `bsd_init_entry`、`calling_vfsinit`、`calling_setconf`、…（空格写 `_`，末尾换行忽略） |

**最早**的运行期步骤是 `vm_mem_bootstrap`，它在 `machine_startup` 之后才可能被调用，
所以它一旦重启就等于「`arm_init` 整段走完」。`arm_init` 内部的
`arm_init / rebased / pe_init / vm_init / serial_init / kprintf / printf /
machine_startup` 是编译期点（`ALPHA_PROBE_RESET_AT`），要重编内核才能选。

### 11.4 定位链（按性价比）

| 顺序 | `alphaplus_reset=` | 命中说明 | 不命中说明 |
| --- | --- | --- | --- |
| 1 | `vm_mem_bootstrap` | MMU 之后的 `arm_init` 整段都过了 | 死在 `arm_init` 内，需要编译期探针 |
| 2 | `iokit_entry` | `machine_startup` 与 bootstrap 头部都过了 | 卡在 bootstrap 早期 |
| 3 | `iokit_configured` | `InitIOKit` + `ConfigureIOKit` 完成 | 卡在 PE/IOKit 起步 |
| 4 | `iokit_matching_started` | `PE_lockdown_iokit` 完成 | 卡在 IOKit 匹配 |
| 5 | `bsd_init_entry` | 进入 BSD | 卡在 `StartIOKitMatching` 之后 |
| 6 | `calling_vfsinit` … | BSD 内逐段推进 | 卡在 `bsd_init` 开头 |

每一步都是一次「刷 `boot_b` → 重启 → 菜单选 XNU → 看是否 3 秒后重启」。
`build-alphaplus/part4k-probe-{plain,vm_mem_bootstrap,machine_init,iokit_entry}.img`
都已经用 11.6 修正后的 ADT 重新生成过。

### 11.5 工具

| 文件 | 作用 |
| --- | --- |
| `firmware/aloha/patches/wsl-pack-probe.py` | 先按 `board.toml` 现生成 ADT，再生成带 `alphaplus_reset=` 的 64 MiB payload；回读校验内核 MD5、ADT MD5、TOML 与大小 |
| `probe-kernel.ps1`（工作区根） | 一条命令走完 build → `fastboot flash boot_b` → `fastboot reboot`，并打印判读方法 |

```sh
python3 firmware/aloha/patches/wsl-pack-probe.py vm_mem_bootstrap
```
```powershell
.\probe-kernel.ps1 -Step vm_mem_bootstrap          # 生成 + 刷入 + 重启
.\probe-kernel.ps1 -Step vm_mem_bootstrap -BuildOnly
```

payload 里 `[boot] default = "erase"`、`timeout = 60`：没人按键时 60 秒后自动
`Erase boot_a` 回 fastboot，所以每次试验都能自己收回机器。

### 11.6 顺手挖出来的一个真错：ADT 的 dram 窗口写成了超集

核对 ADT 时发现 `/chosen` 的两个值对不上：

```
dram-base = 0xC4000000      （devices.py 的 phys_base，CONFIRMED）
dram-size = 0xC0000000      （board.toml 的 dram_size）
窗口末端   = 0x184000000     ← 越过物理内存顶端 0x140000000（第三段 bank 起点）
```

`board.toml` 的原注释写的是「机器 6 GB，先按 3 GB 给 OS 一个安全子集，与 mh2lm 一致」。
问题在于 `dram-base` 已经不是 0x80000000 了：从 0xC4000000 起连续可用到 0x140000000，
上限只有 **0x7C000000（1.94 GiB）**。写 3 GiB 不是子集，是超集——多出的 1.06 GiB
落在没有内存的地址上。

这条值确实会被内核用上，不是没用的装饰：

- 反汇编 `_arm_init`（`0xfffffff0079e17b0` 起）能看到两次 `SecureDTGetProperty`
  取 `dram-base` / `dram-size`，紧接着写 `_gDramBase`（`0x…174ae8`）与
  `_gDramSize`（`0x…174af0`），然后才 `bl _machine_startup`；
- `_wimg_to_pte + 0x40`（`0xfffffff0073cbbcc`）把物理地址减去 `gDramBase`、再和
  `gDramSize` 比较，用它决定这个 PTE 是普通内存还是设备内存。

因此窗口写成超集以后，pmap 会把「不存在/设备」的地址当成 DRAM 处理。它是否就是
「打开 MMU 后静默卡死」的原因，**还没在真机上验证**（截止写这一节手机未连接）；
但它与 `vm_mem_bootstrap` 那一档（pmap/VM 起步）正好重合，先把它排掉。

处置：

- `board.toml` 的 `dram_size` 改成 `0x7c000000`，注释写明「base + size 必须止于 0x140000000」；
- `wsl-pack-probe.py` 不再用 `/root/aloha/uplink/out.adt` 这种历史产物，改为每次按
  `board.toml` 调 `scripts/make-alphaplus-adt.py` 现生成，并断言
  `dram-size == board.toml` 且 `dram-base + dram-size <= 0x140000000`，否则直接退出。

### 11.7 边界与当前阻塞

- 只写 `boot_b`（payload）与菜单里的 `Erase boot_a`；不碰 vendor、不碰 abl、不用 9008。
- 回滚镜像仍是 `magisk_patched-30600_mZhNS.img`。
- 2026-11-07 22:30 写这一节时手机未连接（`fastboot devices` 为空），
  上表的真机结果待补。

### 11.8 真机定位结果（2026-11-07 深夜，手机在 fastboot）

每次的流程：`fastboot flash boot_a boot-cache.img` + `fastboot flash boot_b <探针 payload>`
→ `fastboot reboot` → 菜单里选 `LG G8 - XNU` → 看色带之后约 3 秒是否自动重启。

| 档 | `alphaplus_reset=` | 结果 | 含义 |
| --- | --- | --- | --- |
| 1 | `vm_mem_bootstrap` | **未命中**：色带出现后一直停住，没有重启 | 没走到 `machine_startup` 之后的 bootstrap |
| 2 | `bsd_init_entry` | **未命中**：同上 | 同上 |

结论修正：**内核在打开 MMU 之后、`machine_startup` 之前就停住了**，也就是
`start.s` 的 `ret` 到 `arm_init` 这一段。八条色带是它最后的遗言（band 8 画在
`msr SCTLR_EL1` 之前）。

这条结论有两种可能，现有证据分不开：

1. 内核真的死在这段（MMU 映射错、`pe_identify_machine` panic、`ml_parse_cpu_topology`
   assert 等）——所有 panic 都在没有控制台的前提下静默；
2. 内核其实走到了探测点，但 `alphaplus_probe_reset()` 自己卡住（`CNTPCT_EL0` 不走、
   或 PSCI `smc` 不返回），表现与「没走到」完全一样。

要分开这两种，唯一的办法是**把检查点铺进 `arm_init` 内部**（`ALPHA_PROBE_RESET_AT`
是编译期的，一次只能选一个点），并让选择变成运行期可配——这样一次重编之后，
改 payload 的 args 就能逐点二分。这正是 §12 里 HackiOS 的做法。

已知的旁证（不影响上面结论）：这份内核的可见输出通道为零——
`PE_init_printf(FALSE)` 只接串口，而串口实现是树莓派 AUX（ADT 里没有 `gpio`/`aux` 节点，
`serial_init` 在 `0xfffffff00794f914` 直接返回 0）；视频控制台只有在 `PE_init_iokit`
那次 `PE_init_printf(TRUE)` 才可能接上，而它没有生效。所以「打一行可见输出」在现有
内核上做不到，色带已经是上限。

### 11.9 运行期检查点补丁（已就绪，等一次内核重编）

`ci/0019-unixnu-8796-ci.patch` 里新增了
`patches/xnu/zzzzz-alphaplus-stop-probes.patch`（排在探针补丁之后应用），
把「编译期选一个点」变成「运行期选任意点」：

- 内核从 `boot_args->CommandLine` 里扫 `alphaplus_stop=<n>`（不走
  `PE_parse_boot_arg_str`，因为第一个检查点在 `PE_state.bootArgs` 建立之前）；
- 命中就等 3 秒、PSCI 复位——与 `alphaplus_reset=` 同一套复位手法；
- 共 17 个点，编号与位置：

| 编号 | 位置 | 编号 | 位置 |
| --- | --- | --- | --- |
| 10 | `arm_init()` 第一条语句 | 19 | `kernel_startup_bootstrap()` 之后 |
| 11 | `PE_init_platform(FALSE)` 之后 | 20 | `timer_call_init()` + `cpu_init()` 之后 |
| 12 | 平台 stall 检查之后 | 21 | `processor_bootstrap()` 之后 |
| 13 | `ml_parse_cpu_topology()` 之后 | 22 | `arm_vm_init()` 之后 |
| 14 | `master_cpu` 选好之后 | 23 | `serial_init()` 之后 |
| 15 | `CpuDataEntries` 填好之后 | 24 | `STARTUP_SUB_KPRINTF` 之后 |
| 16 | `thread_bootstrap()` 之后 | 25 | `PE_create_console()` 之后 |
| 17 | `cpu_bootstrap()` 之后 | 26 | `PE_init_printf(FALSE)` 之后 |
| 18 | `rtclock_early_init()` 之后 | 27 | `machine_startup()` 之前 |

验证（本机可做的部分都做了）：

- 补丁对 `apple-oss-distributions/xnu` 的 `xnu-8796.141.3` 干净应用；
- 在**完整补丁栈**上验证：把 `patches/xnu/*.patch` 按名字顺序全部打到一个干净
  的 8796.141.3 树上，54 个全部成功（含这一个）；
- `ci/0019-unixnu-8796-ci.patch` 对钉住的 UniXNU 提交 `40d21cc` 干净应用；
- 选择器那段 C 单独用 `gcc -Wall -Wextra -Werror -fsyntax-only` 过了。

用法（不需要再重编）：

```sh
python3 firmware/aloha/patches/wsl-pack-probe.py none --stop 17   # → part4k-probe-stop17.img
```

判读与 11.8 相同：色带后约 3 秒自动重启 = 走到了这个点；一直停着 = 没走到。
二分顺序建议 17 → 13 → 11 → 10：先确认「有没有进 `arm_init`」，再往前夹。

### 11.10 二进制补丁：CPU 过得了 MMU 打开（2026-11-07 深夜，已真机验证）

重编还没发生，但 UniXNU 自带 `scripts/patch-xnu-entry-probe.py`（BSD-2-Clause-Patent），
可以**直接改已编好的内核**：在代码空洞里塞一段汇编，把某个位置改成「等 N 秒 → PSCI 复位」。

我们这份内核的入口后面是 `nop` 填充（不是零），工具原版要求全零，于是改了两处判定
（零或 `0xD503201F` 都算空洞），并加了 `--no-bars`（保留自己的色带，不动入口）。
本地副本：`build-alphaplus/patch-xnu-probe.py`。

打的第一个点：`msr SCTLR_EL1` 之后（`0xfffffff0073f3558`，原指令 `mov x0, #0x300000`
被搬进空洞执行）。真机结果：

> **色带出现后约 3 秒自动重启（又见 Aloha logo）。**

结论：CPU 确实执行过了 `msr SCTLR_EL1`，MMU 正常打开，`isb` 之后的取指也没问题——
页表/入口映射这条嫌疑排除。死点在它之后，即 `ret` 回 `arm_init` 到最后进入
`machine_startup` 之间。

下一步用同一工具的 stage 4（`--reset-after SYMBOL --in _arm_init`）按调用顺序往前推。
`_arm_init` 里共有 66 个 `bl`，第一个是 `_arm_set_kernel_tbi`（`0xfffffff0079e0e60`）；
命中就说明 `ret` 回 `arm_init` 是通的。

### 11.11 逐调用二分（同一晚，真机各一次）

用 `--reset-after SYMBOL --in _arm_init` 把复位点放在「调用 SYMBOL 之后再等 3 秒复位」，
每档一次刷写。结果：

| 复位点（`_arm_init` 内的 `bl`） | 地址 | 结果 |
| --- | --- | --- |
| `msr SCTLR_EL1` 之后（stage 3） | `0xfffffff0073f3558` | **命中** — MMU 打开正常 |
| `_arm_set_kernel_tbi`（第 1 个调用） | `0xfffffff0079e0e60` | **命中** — `ret` 回 `arm_init` 正常 |
| `_arm_vm_init` | `0xfffffff0079e15f4` | **命中** — 页表/VM 初始化返回 |
| `_kernel_startup_initialize_upto` | `0xfffffff0079e161c` | **命中** — `STARTUP_SUB_KPRINTF` 之前的启动子系统链全部跑完 |

也就是说：内核在真机上已经跑过 MMU、`arm_init` 前半段、`arm_vm_init`（页表/物理内存）
以及整条启动子系统链。**死点只剩最后十几条调用**：`_kprintf`、`_PE_create_console`、
`_PE_init_printf`、`_cpu_machine_idle_init`、`_PE_init_platform(TRUE)`、
`_ml_map_cpu_pio`、`_cpu_timebase_init`、`_kptimer_curcpu_up`、`_PE_init_cpu`、
`_fiq_context_init`、`_early_random`、`_machine_startup`。

下一刀：`_PE_init_platform` 的**第二次**调用（`0xfffffff0079e175c`，
`--occurrence 2`），命中则死点在其后，不命中则在其前的
`_PE_create_console`/`_PE_init_printf`/`_cpu_machine_idle_init` 之间。

工具产物脚本：`build-alphaplus/build-stage4-images.sh SYMBOL[:OCCURRENCE]`
（自动打补丁 + 打包成 `part4k-<symbol>.img`）。

### 11.12 继续二分：内核其实跑得比想象中远（同一晚，真机）

沿 `arm_init` 走到头之后，用同一手法钻进 `machine_startup` → `kernel_bootstrap`
→ `vm_mem_bootstrap`：

| 复位点 | 结果 |
| --- | --- |
| `_machine_startup` 里的 `_machine_conf` 之后 | **命中** |
| `_kernel_bootstrap` 里第一条 `_kernel_debug_string_early`（`0x…8d04`，就在 `vm_mem_bootstrap` 之前） | **命中** |
| `_vm_mem_bootstrap`（在 `_kernel_bootstrap` 里）返回之后 | **命中** — 整块 VM 内存初始化完成 |
| `_vm_mem_bootstrap` 内部：`_vm_page_bootstrap` / `_kmem_init` / 第一次 `_kernel_startup_initialize_upto` / `_vm_fault_init` | **全部命中** |
| `_kernel_bootstrap` 末尾的 `_load_context` | **未命中** — 停住 |

也就是说：内核在真机上已经走完 MMU、`arm_init` 全程、`machine_startup`、
`kernel_bootstrap` 的头部与整块 `vm_mem_bootstrap`（页表、zone、kmem、fault）。
死点落在 `kernel_bootstrap` 中段那串初始化里：`atm_init`、`console_init`、
`sched_init`、`mac_policy_init`、`machine_init`、`clock_init`、`task_init`、
`thread_init`、`exception_init`、`kernel_thread_create` … 到 `_load_context` 之间。

顺带得到一个方法论结论：**编译进内核的 `alphaplus_reset=` 探针在这份内核上不可靠**
（`vm_mem_bootstrap` 那条按 11.11/11.12 的结果本应命中，实测没响）。
此后一律以二进制补丁（`--reset-after`）的结果为准，不再用编译期探针判读。

### 11.13 收口：内核跑进了引导线程，但没到 BSD 初始化（2026-11-08 凌晨）

继续用二进制补丁往下切，最后几档：

| 复位点 | 结果 |
| --- | --- |
| `_kernel_bootstrap`：`_machine_init` / `_thread_init` / `_exception_init` / `_kernel_thread_create` | **全部命中** |
| `_load_context`（第一次线程切换）之后 | **未命中，但这是假阴性**——`_load_context` 切走后再也不返回，探头拿不回控制权 |
| `_kernel_bootstrap_thread`（切换后的线程）里的 `_current_processor` | **命中** —— 第一次线程切换成功，内核确实在跑引导线程 |
| `_kernel_bootstrap_thread.cold.1` 里的 `_bsd_init` | **未命中** —— 没进入 BSD 初始化 |

所以今晚的定位结论是：

**内核在真机上跑完了 MMU、`arm_init` 全程、`machine_startup`、`kernel_bootstrap`
（含整块 `vm_mem_bootstrap`）、第一次线程切换，并开始执行引导线程；
但没有走到 BSD 初始化。** 死点在
`idle_thread_create` / `sched_startup` / `PE_init_iokit` 这一串里。

这比开头的判断（"死在 MMU 之后"）往前推了很多：真正的问题不是入口、不是页表、
不是 VM，而是引导线程里某一步初始化。

### 11.14 这套方法的硬限制：一次启动只能回答一个问题

二进制补丁用"会不会重启"当信号，天然只有 1 bit，而且每次都要人刷机、看屏幕。
今晚一共刷了十五轮才把死点从"MMU 之后"推到"引导线程里"。

要打破这个限制，只有两条路：

1. **给内核一个真正的输出通道**（串口在这块板上不存在，视频控制台没挂上），
   或者照 HackiOS 的做法把 `kprintf` 抄进 RAM 环形缓冲，由**装载器在下次启动时读出来**——
   这样一次启动就能看到整段日志，而不是一个 bit。
2. 把进度写进一块固定的 RAM 区（多 bit 进度寄存器），复位后由 `DarwinBoot`（本地可编）
   读回来显示；前提是 PSCI 复位不清 DRAM，这一点未验证。

在这两条落地之前，继续用刷新循环二分只是在用人力换 bit，性价比已经很低——
这是决定停止二分、转去解决输出通道的原因。

### 11.15 输出通道的实现（2026-11-08 凌晨，两端都已就位）

**内核端**：`patches/xnu/zzzzzz-alphaplus-log-ring.patch`（排在检查点补丁之后）

- 在 `osfmk/kern/startup.c` 里放一个 64 KiB 环形缓冲 `alphaplus_log_ring`：
  `magic "ALPHALOG"` + `head` + `size` + `data`。**带非零初始值**，所以它落在
  `__DATA`（文件里有实体）而不是 `__BSS`——装载器才能在镜像里搜到这段 magic。
- 在 `osfmk/console/serial_console.c` 的 `console_write()` 最前面挂
  `alphaplus_log_write(str, size)`：每一行格式化好的 kprintf 都会进环，
  与有没有串口硬件无关。
- 本地验证：干净 `xnu-8796.141.3` 上 55 个补丁按序全部应用成功；
  `ci/0019` 对 UniXNU `40d21cc` 干净应用。

**装载器端**：`DarwinBoot.c` 加了两块（本地编过，36,864 B）：

- `LogRingVa()`：在**刚读进内存的内核镜像**里搜 `"ALPHALOG"`，用段的
  `FileOffset/Address` 换算出它的 VA，于是物理地址 = `Address + VA - Kernel.Base`；
- `DrawLog()`：把日志按行切开，取最后 34 行用现成的 `DiagDraw()` 画到屏幕上。

关键顺序：读环必须发生在 `ZeroMem(Address, Used)` / 段拷贝**之前**——
否则装载器自己会把上一次的日志覆盖掉。这一条是这套机制成立的前提。

用法：内核起来 → 跑一段 → 复位/断电 → 下次开机 `DarwinBoot` 把上一轮的日志画在屏幕上。
如果内核 panic，日志前面还会带上 panic 的格式化文本（`panic()` 走的是同一条
`printf` → `console_write` 路径）。

**前提**：DRAM 在 PSCI 复位后没被 abl/UEFI 清掉。这一点**还没验证**——
第一次真机试验就是这个试验本身：如果屏幕上出现 ALPHALOG 内容，机制成立；
如果什么都没有，说明复位过程清了内存，得换方案（例如先把日志写进一个
UEFI 不碰的低地址区，或改成关机不断电的复位方式）。

## 12. 参考实现对照：dipper-xnu / HackiOS（2026-11-07）

看的是 `github.com/youzjuzi/dipper-xnu`（小米 8 / SDM845，iOS 16.5 已到 SpringBoard），
以及它依赖的上游 `oosexgang/hackios-xnu-kernel`。本地副本在
`build-alphaplus/dipper-xnu`、`hakios-xnu-kernel`。两个仓库用同一个机器配置
`DEVELOPMENT_ARM64_BCM2837`，和我们是同一套 XNU 骨架，所以对照价值高。

### 12.1 它解决了我们记在 `ci/README.md` 里的那个 iig 卡点

`hakios-xnu-kernel/xnu-deps/setup.sh` 的做法：

- **不生成、直接给头文件**：Apple 的 `iig` 是闭源的，`host/bin/iig` 改成从
  macOS 13.3 SDK 的 `Kernel.framework/Headers/DriverKit` 里取现成头文件；
- **不生成、只补链接**：`gen-iig-stubs.py` 读链接器的未定义符号表，为每个
  DriverKit 方法生成返回 `kIOReturnUnsupported` 的桩，给真正存在的类补
  `OSDefineMetaClass*`；
- 宿主编译用 `-include xnu-deps/hostinc/hostcompat.h`（Apple 的构建工具在 Linux 上编译）。

也就是说「Linux 上编不了 XNU」并不是死路：846 个 `.o` 之后卡在 `iig`，用这两件事就绕过去了。
这条路一旦在本机跑起来，内核改动是分钟级，而不是 GitHub Actions 的 2–3 小时。

### 12.2 它的早期定位法比我们的 `alphaplus_reset=` 更靠前

HackiOS 在 `start.s` 里放了一个装载器可写的槽（magic `XNULDRST`），
`LOADER_CHECKPOINT n` 宏一到点就关 MMU、跳回装载器的返回桩；`arm_init.c` 里从
`loader_checkpoint(10)` 到 `(21)` 覆盖了 `PE_init_platform` 之后、`arm_vm_init`、
`serial_init`、`kprintf`、`PE_create_console`、`machine_startup` 之间每一段。
装载器只需改槽里的编号就能选停在哪，**一次内核构建、任意次定位**。

配套还有两件我们缺的：

1. `pexpert/arm/pe_kprintf.c` 里 `serial_putc_crlf()` 每字符再调一次
   `loader_log_putc()`，把内核日志写进 RAM 缓冲；
2. 早期异常向量（`LowExceptionVectorBase`）不再原地 `b .`，而是记录
   ESR/ELR/FAR/LR/SP 连同日志交回装载器打印。

我们的 `alphaplus_reset=<步骤名>` 只能覆盖**运行期可达**的步骤
（`kernel_bootstrap*`、`PE_init_iokit`、`bsd_init`），`arm_init` 内部那一段是编译期的，
正是现在需要的那一段。

### 12.3 同一个 BCM2837 配置，它改了这些

| 文件 | 改动 | 原因 |
| --- | --- | --- |
| `pexpert/pexpert/arm64/BCM2837.h` | `GENERIC_GIC_V3_IRQ 1`、`GENERIC_PSCI_SMP 1` | GICv3 Group 1 收中断；副核用 PSCI 起 |
| 同上 | `__ARM_PAN_AVAILABLE__ 1` | A55/A76 是 ARMv8.2，异常入口会置 PSTATE.PAN |
| 同上 | `VMAPPLE_UART`（PL011） | 非 Apple 板子的串口实现 |
| 同上 | 删掉固定的 `PLATFORM_PANIC_LOG_PADDR` | 树莓派的 `0x3c0fc000` 在别的板子上不是 RAM |
| `board_config.h` | `MAX_CPUS 4 → 8` | 手机是 8 核 |
| `start.s` | 树莓派的 Core Timer 路由包进 `BCM2837_CORE_TIMER_ROUTING` | 那是往 SoC 本地中断块（`0x4000004X`）写死地址，别的板子**致命** |

### 12.4 顺便把我们这份内核实测核对了一遍

| 结论 | 证据 |
| --- | --- |
| **当前内核没有任何可见控制台** | `PE_init_printf(FALSE)` 只把 kprintf 接到 `serial_putc`（`0xfffffff00794d160`）；只有传 TRUE 才 `vcattach` 接视频控制台，`arm_init` 传的是 FALSE |
| **串口在这块板上不存在** | `serial_init`（`0xfffffff00794f914`）读 `serial=` 参数后去 ADT 找 `name=gpio`、`aux` 节点再 `ml_io_map`——那是树莓派的 AUX mini-UART；我们的 ADT 里没有这些节点，于是直接返回 0 |
| `serial=3` 无效 | 同上；参数只取第一个字符，且没有对应节点 |
| `msr SCTLR_EL1` 之后那个 `bne .` 不是挂点 | 反汇编 `0xfffffff0073f3528…3554`：`x0` 与同一常量自比较，永远相等 |
| `MAX_CPUS` 够用 | `CpuDataEntries` 占 `0x80` 字节（16 个指针），`cpus=8` 不越界 |
| `ml_parse_cpu_topology` 是静默风险区 | 读 `cpus`（默认 8）、`cpumask`，遍历 `/cpus` 找 `state=running`，带 22 条 `cold` panic 路径——任何不匹配都是无声 panic（那时还没有控制台） |

结论：**「跳进内核后没有任何文字」是必然的**，与内核走到哪一步无关。
第 4 节第 1 条想要的「一行可见输出」在现有内核上不可能实现；色带已经是能做到的最强证据。

### 12.5 由这份对照得到的下一步

1. **先做一次带「编号检查点」的内核构建**：把 `alphaplus_probe_step` 扩展成
   `alphaplus_stop=<n>`，在 `arm_init` 里按 HackiOS 的位置放 10–21 号点，
   命中就 3 秒后 PSCI 复位（沿用我们已有的复位手法，不需要装载器配合）。
   之后 `arm_init` 内部的二分只改 payload 的 args，不再重编内核。
2. 顺带把 `/pram` 节点补进 ADT：`PE_create_console` 就是按 `pram` + 16 字节 `reg`
   建 panic 日志区的；有它才有机会在**下一次**启动时由装载器把 panic 日志读出来。
3. 构建这两样东西的两条路：本地 Linux 工具链（12.1，一次约一小时准备，之后分钟级），
   或现有 GitHub Actions（一次 2–3 小时，产物下载后本地验证）。

## 13. 参考实现对照 #2：红米双系统一键安装包（raphael，蜂窝上网版，2026-11-07）

路径：`F:\ai共享\安卓安装苹果\红米双系统一键安装包（蜂窝上网版）`。这是一个已经量产、
手机端到 SpringBoard、带蜂窝数据的完整交付物。解包后看到的东西：

### 13.1 包里的实际结构（实测，不是文档转述）

| 文件 | 实测内容 |
| --- | --- |
| `images/ios-recovery.img` | `ANDROID!` v2，page 4096；kernel 字段 1,784,359 B，**gzip 解开是 3,253,520 B 的 Linux ARM64 Image**；ramdisk 字段只有 5 B；cmdline 里带 `HACKiOS` |
| 同上（Linux 内核内） | 带 `XNUPX` 容器，内含 `loader.efi`；字符串有 `== XNULOADER v3 ==`、`== XNULOADER run (usb) ==`、`return slot patched at %x, checkpoint %d`、`STOPPED AT CHECKPOINT %d`、`pram`、`embedded-panic-log-size`、`RAPHIOS1` |
| `images/ios-boot-resources.bin` | `RAPHIOS1` 容器 v2，page 4096，总长 157,548,544；resident 段在 `0x02AD7000`、长 `0x06B69000`；内含 `XNUP` payload，其 `kernel` 条目是 Mach-O（`__TEXT` / `__TEXT_EXEC` / `__DATA_CONST` / `__KLD`） |
| `images/ios-offline-payload.bin` | 同一个 `XNUP` 容器（44,915,912 B 的 payload） |
| `config.json` | `resource_offset` 3 GiB、`data_first_block` 2042368、`kernel_sha256`、`wireless_inputs = modemst1/modemst2/fsg/fsc` |

也就是说，他们的交付形态是：**recovery 分区放一个精简 Linux，Linux 读 darwin 分区里的
RAPHIOS1 资源容器，解出 XNUP payload 里的 Mach-O 内核，再交给 XNU**。

### 13.2 与我们的架构差异

| | raphael 包 | 我们的 G8 |
| --- | --- | --- |
| 引导器 | 精简 Linux 内核（硬盘/显示/USB 都有驱动） | UEFI 应用 `DarwinBoot` |
| 内核放哪 | darwin 分区里的 `RAPHIOS1` 容器 | `boot_b` 上的 64 MiB FAT16 |
| 早期诊断 | Linux 侧可直接打印、读 RAM、读 panic log | 只有屏幕色带，没有任何输出通道 |

Linux 引导器天生有控制台，这是他们能"看着调"的根本原因；换到我们这里意味着要给 G8
做一套 Linux 驱动（UFS/显示/输入），成本远超收益，**不采用**。

### 13.3 能直接搬的三件

1. **`RAPHIOS1` + `XNUP` 的打包形态**：把内核/ADT/资源放进一个带校验的容器，
   装载器按条目取。比我们现在"内核塞在 FAT16 里"更整齐，等链路通了再换。
2. **检查点返回槽**（与 12.2 同一套）：他们的 Linux 侧字符串
   `return slot patched at %x, checkpoint %d` / `STOPPED AT CHECKPOINT %d` 证明生产环境就是这么用的。
3. **`/pram` 嵌入式 panic 日志**：我们这份内核里已经有全套代码——
   `PE_create_console`（`0xfffffff00794ef98`）会 `SecureDTLookupEntry("pram")`、读 `reg`
   （要求 16 字节）、再读 `/chosen/embedded-panic-log-size`。
   **但它的初始化点在 `arm_init` 后段**（kprintf 之后、`PE_init_printf` 之前），
   所以更早的 panic（例如 `ml_parse_cpu_topology` 的 22 条 assert）仍然不会被记录。

结论：`/pram` 值得补（ADT 加一个 `pram` 节点 + `embedded-panic-log-size`，装载器下次启动读回来），
但它救不了 `arm_init` 前半段；那一段仍然只能靠**编译期检查点**。

### 13.4 顺带确认的两件事

- 他们的内核确实是装进容器的 Mach-O（`__KLD` 段说明是带 kext 支持的单体内核），
  与 `docs/notes/16-ios16-route.md` 里"iOS 16 用户态要走单体内核"的判断一致。
- `config.json` 的 `wireless_inputs` 给出了蜂窝上网的最小集：`modemst1`、`modemst2`、
  `fsg`、`fsc`。等我们的链路通了再考虑，属于后期工作。
