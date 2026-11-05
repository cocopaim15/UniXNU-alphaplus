# firmware/uefi —— 要覆盖到 uefi-sheng 检出里的文件

这个目录不是独立仓库，而是**overlay**：CI 在构建前把这里的内容按相对路径复制进
`uefi-sheng` 的检出目录。

| 路径 | 作用 |
| --- | --- |
| `Platforms/LG/alphaplusPkg/` | 平台包（DSC/FDF/Include/两个 Library） |
| `Silicium-ACPI/Platforms/LG/alphaplus/AcpiTables.inf` | ACPI 表清单；`DSDT.aml` 不入库，构建时从 Aloha 拉 |
| `../alphaplus.toml` | 对应 `uefi-sheng/Resources/Configs/alphaplus.toml` |

## 现状：骨架，未验证

`Platforms/LG/alphaplusPkg/` 是从 uefi-sheng 的 **`Platforms/LG/mh2Pkg` 机械改名而来**。
已确认 `mh2Pkg` 就是 LG G8X ThinQ（SMBIOS `G8x ThinQ` / `mh2lm` / `LM-G850EMW`），
它与 G8 同 SoC、同 LG 平台，Display Reserved 也同为 `0x9D200000 + 0x01200000`。

已完成：文件名与内容里的 `mh2` → `alphaplus`，`PLATFORM_NAME` / `OUTPUT_DIRECTORY` /
`FLASH_DEFINITION` 跟着改。

**尚未完成，且不能靠猜的三处：**

1. **`MemoryMapLib.c`** —— 必须换成 G8 的实际内存映射：
   - `Kernel` 段：`0x80000000 + 0x02A00000`（现为 G8X 的 `0x00600000`）
   - `UEFI FD` 段：`0x9FC00000 + 0x00300000`（现为 `0xA0000000`），其后
     Stack / Info Blk / DXE Heap 的地址要整体前移 4 MiB
   - 权威来源：Project-Aloha `lg-alpha` 的 `PlatformMemoryMapLib.c`
     （其结构体是 `ARM_MEMORY_REGION_DESCRIPTOR_EX` / `PlatformMemoryMapLib` 接口，
     与这里的 `EFI_MEMORY_REGION_DESCRIPTOR` / `MemoryMapLib` **不是同一个抽象**，
     需要逐字段搬运，不能整个文件替换）
2. **SMBIOS 串** —— 现在仍是 `G8x ThinQ` / `LM-G850EMW` / `mh2lm`，
   应改为 `G8 ThinQ` / `LM-G820UM` / `alphalm`。
3. **ACPI 表** —— `alphaplus.dsc` 引用的 `alphaplus/AcpiTables.inf` 不存在。
   它属于另一个 submodule `Project-Silicium/Silicium-ACPI`，而那个仓库的 LG 目录
   只有 `mh2`。G8 可用的 `DSDT.aml` 在 Project-Aloha 的
   `Platforms/SurfaceDuo1Pkg/Device/lg-alpha/ACPI/DSDT.aml`，需要搬成
   `Silicium-ACPI/Platforms/LG/alphaplus/`。

在这三处落实之前，这个包**构建不出可用固件**，也不应被当成可刷写的产物。
