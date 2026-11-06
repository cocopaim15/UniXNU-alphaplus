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
