# 内核入口证据 · 2026-11-06 23:27

`2026-11-06-entry-bands.jpg`：真机屏幕，UniXNU 菜单选 `LG G8 - XNU` 之后。

最上 1/16 绿带由 `DarwinBootPkg/Driver/Entry.S` 的 `DarwinEnter` 在 `br x1`
之前画；下面八条（红、橙、黄、白、青、蓝、品红、灰）由内核
`osfmk/arm64/start.s` 的 `ALPHA_PROBE_BAR` 逐步画，位置由
`boot_args.Video`（0x28 / 0x38 / 0x48）算出。两条链路叠在同一张屏幕上，
所以它同时证明：

1. `ExitBootServices` 成功、EL1 内核入口真的跑起来了；
2. `boot_args` 的 Video 段版式被内核接受；
3. `start.s` 走完了异常向量、boot args、异常/中断栈、bootstrap 页表、
   TCR/TTBR0-1/MAIR，停在 `msr SCTLR_EL1`（打开 MMU）之前。

复现：`firmware/aloha/patches/wsl-pack-probe.py none` 生成不带 `alphaplus_reset`
的 payload → `fastboot flash boot_b` → 重启 → 菜单选 XNU。
内核身份见 `docs/porting-log.md` 第 11.2 节（MD5 `4465ccc7…`）。
