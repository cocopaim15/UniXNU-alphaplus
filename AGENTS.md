# Device agent guide — LG G8 ThinQ (alphaplus / alphalm)

本仓库是 **format 1** 的 UniXNU 设备仓库（没有 `schema_version = 2`，没有 `porting.toml`）。
选择 format 1 的理由写在 [DEVIATIONS.md](DEVIATIONS.md)，开工前先读它。

## 本仓库拥有什么

| 东西 | 位置 |
| --- | --- |
| 设备描述、IPSW 版本、内核 defconfig/归档、payload、bootimg 偏移 | `board.toml` |
| 内核开关 | `configs/alphaplus_defconfig` |
| ADT 生成（板级值 + 设备树匹配） | `scripts/devices.py`、`scripts/mkadt.py`、`scripts/make-alphaplus-adt.py`、`scripts/adt.py` |
| 设备树探查工具 | `scripts/fdt-probe.py`（解析 DTB 的 compatible / memory / reserved-memory / SoC 节点） |
| 内核构建 CI（macOS + Xcode 15） | `.github/workflows/kernel-8796.yml` |
| 对 UniXNU 的改动（含 probe 补丁） | `ci/0019-unixnu-8796-ci.patch` |
| 固件输入清单 | `proprietary-files.txt` |

## 先读这些

| 主题 | 位置 |
| --- | --- |
| 为什么是 format 1 | [DEVIATIONS.md](DEVIATIONS.md) |
| 本机实测量与未决项 | [README.md](README.md) |
| 内核/补丁 | [UniXNU: source and patches](https://unixnu.com/xnu/source-and-patches)、`ci/README.md` |
| 打包/启动 | [Payload](https://unixnu.com/concepts/payload)、[UEFI firmware](https://unixnu.com/porting/uefi-firmware)、[bring-up](https://unixnu.com/porting/bring-up) |

## 本机的硬事实（2026-11-05 实测，推翻模板里的默认假设）

1. **`fastboot boot` 不可用。** LG 的 abl 对 RAM 启动做鉴权，未签名镜像一律
   `Failed to load/authenticate boot image: Load Error`。所有验证都必须
   **`fastboot flash boot_a` → 重启 → 观察 → 刷回**，不是零写入。
2. **`fastboot set_active` 未实现**（`unknown command`），A/B 切槽不可用，只能写活动槽。
3. **刷写前必须有 `boot_a` 备份**：root 下 `dd if=/dev/block/by-name/boot_a`，或保存
   Magisk 输出的 `magisk_patched-*.img`。没有备份不要覆盖 `boot_a`。
4. **Apple 产物不入库**：IPSW、kernelcache、DeviceTree、`scripts/base-*.adt`，
   一律在本地从自己的 IPSW 抽取/校验。
5. **不要用 `mkadt.py` 造出来的节点去"绕过"内核检查**（如 `/chosen`、`/options`），
   那是把问题推到后面。
6. **内核补丁与 `ci/0019-unixnu-8796-ci.patch` 必须在同一提交里**，否则 CI 与本地产物不一致。
7. **版本三角是硬约束**：iOS 16 用户态需要 **16 KiB 页内核**，不能用"源码内核 + 原厂
   kernelcache prelink"凑，见 `DEVIATIONS.md`。

## 常用命令

```sh
# 设备侧：生成 ADT（需要 scripts/base-d22ap.adt 提供 /product 节点）
python3 scripts/make-alphaplus-adt.py out.adt --dram-size 0xc0000000

# 看设备树里的板级值
python3 scripts/fdt-probe.py android-alpha.dtb

# 配置校验（在 UniXNU 检出目录执行）
python3 unixnu defconfig alphaplus_defconfig -D ../UniXNU-alphaplus
python3 unixnu status -D ../UniXNU-alphaplus

# 内核：本地编不了就在 CI 里跑 kernel-8796，取 artifact
```

## 记录方式

format 1 没有 `porting.toml` 和记录校验。证据要求：

- 每次刷写/验证都把串口或屏幕输出留档（`evidence/<阶段>/`）。
- 仓库里只放**可复现的东西**：board / defconfig / scripts / CI patch，
  叙事写进 README 或 DEVIATIONS。
