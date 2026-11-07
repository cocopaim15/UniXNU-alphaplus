"""Build a payload whose XNU entry fires alphaplus_reset=<step>.

The kernel that is already on the phone carries alphaplus_probe_step(): when the
boot-arg matches a step name, the kernel waits ALPHA_PROBE_RESET_SECONDS and
then issues PSCI SYSTEM_RESET. Every runtime-reachable step therefore turns into
a reboot, and the timing tells whether the kernel got there:

    3 s after the colour bands -> the step was reached
    nothing                    -> the kernel died before that step

Runtime steps are the ones that reach alphaplus_probe_step(), i.e. the
kernel_bootstrap kernel_bootstrap_thread names, PE_init_iokit and
IOPlatformExpertDevice::configureDefaults, and bsd_init's "calling ..." lines
(spaces become underscores, e.g. calling_vfsinit). The compile-time points
inside arm_init (arm_init, pe_init, vm_init, serial_init, printf, ...) need
ALPHA_PROBE_RESET_AT set in the source and a kernel rebuild.

Kernels built with patches/xnu/zzzzz-alphaplus-stop-probes.patch also take
alphaplus_stop=<n>, which selects one of the numbered checkpoints inside
arm_init() (10 = first statement, 27 = just before machine_startup; the full
list is in osfmk/arm64/alphaplus_probe.h). That selector is read from the
command line, so it needs no rebuild: --stop 17 is enough.

Usage:
    python3 wsl-pack-probe.py machine_init
    python3 wsl-pack-probe.py iokit_entry --default xnu --timeout 10
    python3 wsl-pack-probe.py none --stop 17
"""

import argparse
import hashlib
import subprocess
import sys
import tomllib
from pathlib import Path

ROOT = Path("/root/aloha")
BOOT = ROOT / "boot"
KERNEL = ROOT / "kernel/kernel-stripped.macho"
REPO = Path("/mnt/f/ai共享/安卓安装苹果/unixnu-alphaplus")
OUTDIR = Path("/mnt/f/ai共享/安卓安装苹果/build-alphaplus")

BASE_ARGS = "debug=0xc serial=3 cpus=8 keepsyms=1 rd=ufsroot0 wdt=-1"

TOML = """version = 1

[boot]
timeout = {timeout}
default = "{default}"

[kits]
autoload = false

[[entry]]
id = "xnu"
title = "LG G8 - XNU"
type = "xnu"
path = "Payloads/kernel.macho"
args = "{args}"

[[entry]]
id = "erase"
title = "Erase boot_a (fastboot)"
type = "action"
action = "erase-boot"
"""


def run(*argv, **kwargs):
    result = subprocess.run(argv, text=True, capture_output=True, **kwargs)
    if result.returncode != 0:
        sys.exit("%s failed:\n%s%s" % (argv[0], result.stdout, result.stderr))
    return result.stdout


def md5(path):
    digest = hashlib.md5()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build_adt(destination):
    """Regenerate the ADT from board.toml so the payload cannot carry a stale one."""
    board = tomllib.loads((REPO / "board.toml").read_text(encoding="utf-8"))
    dram_size = int(str(board["payload"]["dram_size"]), 0)
    run(sys.executable, str(REPO / "scripts/make-alphaplus-adt.py"),
        "--output", str(destination), "--dram-size", hex(dram_size))

    sys.path.insert(0, str(REPO / "scripts"))
    import adt  # noqa: E402  (repo tool, same format the payload consumes)

    tree, _ = adt.parse(Path(destination).read_bytes())
    chosen = next(child for child in tree.children if child.name == "chosen")
    # mkadt writes the ADT in the host (little-endian) byte order.
    base = int.from_bytes(chosen.prop("dram-base"), "little")
    size = int.from_bytes(chosen.prop("dram-size"), "little")
    if size != dram_size:
        sys.exit("ADT dram-size 0x%x != board.toml 0x%x" % (size, dram_size))
    if base + size > 0x140000000:
        sys.exit("dram window 0x%x+0x%x runs past the top of RAM (0x140000000)" % (base, size))
    print("adt        dram 0x%x + 0x%x (ends 0x%x)" % (base, size, base + size))
    return destination


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("step", help="alphaplus_reset step name, or none")
    parser.add_argument("--default", default="erase",
                        help="payload default entry: erase (safe) or xnu (unattended)")
    parser.add_argument("--timeout", type=int, default=60)
    parser.add_argument("--stop", type=int, default=None,
                        help="alphaplus_stop=<n> checkpoint inside arm_init()")
    parser.add_argument("--kernel", default=None,
                        help="kernel image to pack (default: /root/aloha/kernel/kernel-stripped.macho)")
    parser.add_argument("--out", default=None)
    args = parser.parse_args()

    step = "" if args.step == "none" else args.step
    if step and args.stop is not None:
        sys.exit("give either a step name or --stop, not both")
    if args.stop is not None:
        if not 10 <= args.stop <= 27:
            sys.exit("--stop must be one of the arm_init checkpoints (10..27)")
        suffix = "stop%d" % args.stop
        command_line = BASE_ARGS + " alphaplus_stop=%d" % args.stop
    else:
        suffix = step or "plain"
        command_line = BASE_ARGS + (" alphaplus_reset=" + step if step else "")
    image = OUTDIR / (args.out or "part4k-probe-%s.img" % suffix)
    toml_path = BOOT / "unixnu-probe.toml"
    kernel = Path(args.kernel) if args.kernel else KERNEL
    if not kernel.exists():
        sys.exit("kernel not found: %s" % kernel)
    adt_path = build_adt(BOOT / "unixnu-probe.adt")

    toml_path.write_text(TOML.format(timeout=args.timeout, default=args.default,
                                     args=command_line), encoding="utf-8")

    for path in (image,):
        if path.exists():
            path.unlink()
    run("dd", "if=/dev/zero", "of=" + str(image), "bs=1M", "count=64", "status=none")
    run("mkfs.vfat", "-F", "16", "-S", "4096", "-s", "1", "-n", "ALPHASP", str(image))
    run("mmd", "-i", str(image), "::/EFI", "::/EFI/UniXNU", "::/EFI/UniXNU/Payloads")
    run("mcopy", "-i", str(image), str(toml_path), "::/EFI/UniXNU/unixnu.toml")
    run("mcopy", "-i", str(image), str(kernel), "::/EFI/UniXNU/Payloads/kernel.macho")
    run("mcopy", "-i", str(image), str(adt_path), "::/EFI/UniXNU/Payloads/kernel.macho.adt")

    print(run("mdir", "-i", str(image), "::/EFI/UniXNU").strip())
    print(run("mdir", "-i", str(image), "::/EFI/UniXNU/Payloads").strip())

    copied = run("mtype", "-i", str(image), "::/EFI/UniXNU/unixnu.toml")
    assert copied == toml_path.read_text(encoding="utf-8"), "toml round-trip mismatch"
    embedded = hashlib.md5(
        subprocess.run(["mtype", "-i", str(image), "::/EFI/UniXNU/Payloads/kernel.macho"],
                       capture_output=True, check=True).stdout).hexdigest()
    assert embedded == md5(kernel), "kernel round-trip mismatch"
    embedded_adt = hashlib.md5(
        subprocess.run(["mtype", "-i", str(image), "::/EFI/UniXNU/Payloads/kernel.macho.adt"],
                       capture_output=True, check=True).stdout).hexdigest()
    assert embedded_adt == md5(adt_path), "ADT round-trip mismatch"
    assert image.stat().st_size == 64 * 1024 * 1024, "payload is not 64 MiB"
    if step:
        assert "alphaplus_reset=" + step in copied, "arg missing from toml"
    if args.stop is not None:
        assert "alphaplus_stop=%d" % args.stop in copied, "arg missing from toml"

    print("\nimage      %s (%d bytes)" % (image, image.stat().st_size))
    print("kernel md5 %s (matches %s)" % (embedded, kernel))
    print("adt md5    %s" % embedded_adt)
    print("args       %s" % command_line)
    print("default    %s, timeout %d s" % (args.default, args.timeout))
    print("flash      fastboot flash boot_b %s" % image.name)


if __name__ == "__main__":
    main()
