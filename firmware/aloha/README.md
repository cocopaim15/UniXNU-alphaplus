# aloha —— 用 Project-Aloha 的构建系统产出可启动的固件卷

`firmware/uefi/` 那条路（uefi-sheng + 本仓库的 `alphaplusPkg`）能编出 3 MiB 的
FD，但真机不启动；Project-Aloha 自己的 `lg-alphaplus_NOSB.img` 能启动。这个目录
把「用他们的构建系统产出 FV、再把 UniXNU 放进去」固化成可复现的步骤。

产物：`SM8150_EFI.fd`（3 MiB，FVMAIN_COMPACT 里含 UniXNU 的四个模块）+ 一个
`boot-alphaplus-unixnu.img`（BootShim + gzip(FD) + DTB，payload 在 ramdisk）。

## 为什么不直接 `./build_uefi.py -d lg-alpha`

他们的入口是 stuart（`PlatformBuildNoSb.py`），`--init/--update` 会从 GitHub
release 拉 `Mu-Basetools`、`OneCrypto`、`Mu_CryptoBin` 等（合计 300 MB 级）。
本机链路对 `*.githubusercontent.com` / release 资产整段 reset，只有 codeload 和
api.github.com 可用。所以这里绕开 stuart：

* BaseTools 从 `MU_BASECORE` 源码编（`make -C MU_BASECORE/BaseTools`）。
* 加密驱动不下载：从 Aloha 已发布的 FD 里取出 `BaseCryptoDriverDxeAARCH64`
  （同一个 mu_basecore release、同一条工具链），用 `FILE DRIVER` 塞回 FV；
  各模块的 `BaseCryptLib`/`TlsLib` 指向 Mu 的协议客户端库
  （`CryptoPkg/Library/BaseCryptLibOnProtocolPpi/`），运行时由那个驱动提供。

## 步骤（WSL Ubuntu 24.04）

```sh
sudo apt install -y clang lld llvm iasl nasm mtools uuid-dev build-essential \
                    python3-venv python3-pip mono-devel

# 1. 取源码（git clone 在本机会卡死，用 codeload tar）
mkdir -p ~/aloha && cd ~/aloha
curl -sSL -o main.tar.gz https://codeload.github.com/Project-Aloha/mu_aloha_platforms/tar.gz/refs/heads/main
tar xzf main.tar.gz && mv mu_aloha_platforms-main mu_aloha_platforms
cd mu_aloha_platforms

# 2. 子模块（.gitmodules 的 pin 见本目录 listing；同样用 codeload 解到对应路径）
#    MU_BASECORE / Common/MU / Common/MU_OEM_SAMPLE / Binaries /
#    Platforms/SurfaceDuoACPI / Features/DFCI / Features/CONFIG /
#    Platforms/CranePkg / Platforms/OpensslPkg/.../openssl /
#    Platforms/MbedTlsPkg/.../mbedtls / MU_BASECORE 里的 brotli、libfdt、
#    mipisyst、libspdm、oniguruma；另需
#    acpi_oem_qcom_common_downstream 解到 Platforms/SurfaceDuoACPI/QcomACPI。

# 3. 两个不在 mu_aloha_platforms 里的包
cp -r <UniXNU 检出>/package/UniXNUPkg            ~/aloha/extras/
# DarwinBoot: https://codeload.github.com/UniXNU/DarwinBoot/tar.gz/refs/heads/main

# 4. 补丁（工具链差异 + UniXNU 集成）
python3 <本目录>/apply-patches.py ~/aloha/mu_aloha_platforms

# 5. BaseTools
make -C ~/aloha/mu_aloha_platforms/MU_BASECORE/BaseTools -j

# 6. 编译
export WORKSPACE=$PWD EDK_TOOLS_PATH=$PWD/MU_BASECORE/BaseTools
export PACKAGES_PATH="$PWD/Platforms:$PWD/MU_BASECORE:$PWD/Common/MU:
  $PWD/Common/MU_OEM_SAMPLE:$PWD/Features/DFCI:$PWD/Features/CONFIG:
  $PWD/Binaries:$PWD/Silicon/QC/Sm8150:$HOME/aloha/extras:
  $HOME/aloha/extras/DarwinBootPkg"
export PATH="$EDK_TOOLS_PATH/BinWrappers/PosixLike:$EDK_TOOLS_PATH/Source/C/bin:$PATH"
mkdir -p Conf && cp MU_BASECORE/BaseTools/Conf/{tools_def,build_rule}.template Conf/ \
  && mv Conf/tools_def.template Conf/tools_def.txt && mv Conf/build_rule.template Conf/build_rule.txt
build -p Platforms/SurfaceDuo1Pkg/SurfaceDuo1NoSb.dsc -a AARCH64 -t CLANGDWARF \
      -b RELEASE -D TARGET_DEVICE=lg-alpha -D FDT=alpha.dtb \
      -D SHARED_CRYPTO_PATH=$HOME/aloha/shared-crypto -D CUSTOM_STACK_CHECK_LIB=STATIC -n 8
```

`SHARED_CRYPTO_PATH` 需要 `Driver/Bin/{CryptoDriver.inc.dsc,
CryptoDriver.DXE.inc.fdf, CryptoDriver.RUNTIMEDXE.inc.fdf}`；`.inc.dsc` 为空，
`.fdf` 里用 `FILE DRIVER = bdee011f-87f2-4a7f-bc5e-44b6b61f4e20` 指向从发布镜像
里取出的那个 `.efi`。

产物：`Build/SurfaceDuo1Pkg/RELEASE_CLANGDWARF/FV/SM8150_EFI.fd`（3 MiB）。

## 打启动镜像

Aloha 的格式：`kernel = gzip(BootShim.bin + FD) + android-alpha.dtb`，
`--ramdisk payload.img`，`page=4096`、`kernel_offset=0x8000`、
`ramdisk_offset=0x1000000`、`tags_offset=0x100`、header v0。

```sh
bash build_boot_shim.sh -b 0x9FC00000 -s 0x00300000   # BootShim/BootShim.bin，112 B
python3 PythonLibs/mkbootimg.py --header_version 0 --pagesize 4096 \
  --kernel_offset 0x8000 --ramdisk_offset 0x1000000 --tags_offset 0x100 \
  --os_version 11.0.0 --os_patch_level 2023-04-01 \
  --kernel kernel.bin --ramdisk payload.img -o boot.img
```

`payload.img` 是 32 MiB FAT32，卷标 `ALPHASP`：

```
/EFI/UniXNU/unixnu.toml
/EFI/UniXNU/Payloads/kernel.macho
/EFI/UniXNU/Payloads/kernel.macho.adt
```

## 补丁清单

| 补丁 | 原因 |
| --- | --- |
| zlib `-Wno-deprecated-non-prototype` | zlib 是 K&R 定义，clang 18 + `-Werror` 直接报错 |
| SecurityStubDxe 去掉 `DxeImageVerificationLib` | 它把 `UefiRuntimeLib` 拖进 DXE_DRIVER，EDK2 拒绝；NOSB 不需要 |
| CpuDxe 去掉 `MemoryProtectionExceptionHandlerLib` | 与 ArmPkg 的异常处理库符号重名，lld 报 duplicate symbol |
| NetworkPkg 从 `[Components]` 去掉 | FDF 本来就没放，TlsDxe 是唯一还需要真加密库的模块 |
| `BaseCryptLib/TlsLib` → `BaseCryptLibOnProtocolPpi` | 走协议调用预编译加密驱动，不编 OpenSSL |
| SEC 链接 `StackCheckLib` + 本地 `SecStackCheck.c` | LTO 在链接期重新插入栈保护，SEC 没有对应符号 |
| PrePi 关闭 `-fstack-protector` | SEC 阶段没有可用的栈保护运行时 |
| `Conf/build_rule.txt` 删掉 OBJCOPY 行 | Mu 把 `OBJCOPY_FLAGS` 写成占位文字，`llvm-objcopy` 报 too many positional arguments |
| `-D FDT=alpha.dtb` | FDF 里 `linux-$(FDT)` 需要这个宏，stuart 平时替我们设 |
| PrePi 把 x0 存进 HOB `DAEE82E6-…` | UniXNURamDiskDxe 靠这个找 `/chosen/linux,initrd-start`，Aloha 的 PrePi 原本不传 |
| DSC/FDF 增加 UniXNU 四个模块 | 启动菜单（UniXNU.efi）、Boot#### 注册（UniXNUDxe）、initrd 磁盘（UniXNURamDiskDxe）、XNU 装载器（DarwinBoot） |

## 实测（2026-11-06）

* `SM8150_EFI.fd` 3,145,728 B；FVMAIN_COMPACT 69% 满（余 965,352 B）；
  SEC 的 FILE_GUID 与发布镜像一致（`3e401783-94cc-4fcd-97bc-bd35ac369d2f`），
  `uefiplat.cfg`、`BaseCryptoDriverDxeAARCH64`、`EdkShell`、`BdsDxe`、`UFSDxe`
  都在，另有 UniXNU 四个模块。
* `boot-alphaplus-unixnu.img` 37,687,296 B：kernel 4,125,096（gzip 段 2,150,169 +
  DTB 1,974,927），ramdisk 33,554,432。
* **尚未在真机验证。**

## 已知缺口

1. `payload.img` 由 mtools 手工组装，`unixnu payload` 还需要 macOS 的 hdiutil
   （Data seed 步骤），两条路目前不产出同一份镜像。
2. ADT 用的是本仓库 `scripts/make-alphaplus-adt.py` 生成的 `out.adt`，没有
   `RAMDisk`/`PackedRAMDisk` 占位；不传 Data ramdisk 时不触发。
3. Aloha 的 `MsBootPolicy` 会不会覆盖 `BootOrder`、把 UniXNU 挤掉，要真机才能确认。

## 真机实测（2026-11-06）

固件在 LG G8 上跑通了到 DarwinBoot 的最后一步。三条与打包直接相关的结论：

* **payload 卷用 4096 字节扇区的 FAT16**（UFS 逻辑块是 4096，512 字节扇区挂不上）：

  ```sh
  dd if=/dev/zero of=payload.img bs=1M count=64
  mkfs.vfat -F 16 -S 4096 -s 1 -n ALPHASP payload.img
  mmd -i payload.img ::/EFI ::/EFI/UniXNU ::/EFI/UniXNU/Payloads
  mcopy -i payload.img unixnu.toml ::/EFI/UniXNU/unixnu.toml
  mcopy -i payload.img kernel.macho ::/EFI/UniXNU/Payloads/kernel.macho
  mcopy -i payload.img kernel.macho.adt ::/EFI/UniXNU/Payloads/kernel.macho.adt
  fastboot flash boot_b payload.img      # 整卷裸刷，不要分区表
  ```

* **payload 的 `unixnu.toml` 里放一条 `erase-boot` 动作并设成默认**，没有输入时
  60 秒后自动擦 `boot_a` 进 fastboot——不用 9008。
* **ramdisk 不可用**：abl 传的 x0 不是设备树，Kernel 段里也扫不到 initrd。

按键、payload 探测、DarwinBoot 阶段标记等改动见 `patches/`，结论见
`docs/porting-log.md` 第 10 节。
