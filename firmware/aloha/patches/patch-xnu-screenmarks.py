"""Inject alpha_screen.c into a kernel copy and call it from 12 bring-up sites.

Each patched site becomes:
    b  site_cave          (replaces the original `bl target`)
    site_cave: save x0-x7 + lr, alpha_mark(n), restore, `bl target`, `b site+4`
so the original call still happens with its arguments intact.
"""
import argparse
import struct
import subprocess
import tempfile
from pathlib import Path

MARKS = [
    (1,  "_kernel_debug_string_early", "_kernel_bootstrap",                1),
    (2,  "_vm_mem_bootstrap",          "_kernel_bootstrap",                1),
    (3,  "_machine_init",              "_kernel_bootstrap",                1),
    (4,  "_thread_init",               "_kernel_bootstrap",                1),
    (5,  "_exception_init",            "_kernel_bootstrap",                1),
    (6,  "_kernel_thread_create",      "_kernel_bootstrap",                1),
    (7,  "_load_context",              "_kernel_bootstrap",                1),
    (8,  "_current_processor",         "_kernel_bootstrap_thread",         1),
    (9,  "_idle_thread_create",        "_kernel_bootstrap_thread",         1),
    (10, "_sched_startup",             "_kernel_bootstrap_thread",         1),
    (11, "_PE_init_iokit",             "_kernel_bootstrap_thread.cold.1",  1),
    (12, "_bsd_init",                  "_kernel_bootstrap_thread.cold.1",  1),
]

CAVE_BASE = 0xFFFFFFF0073F1500
CAVE_LIMIT = 0xFFFFFFF0073F1F00
PE_STATE = 0xFFFFFFF007204150
SOURCE = Path("/mnt/f/ai共享/安卓安装苹果/build-alphaplus/alpha_screen.c")


def segments(data):
    magic, _, _, _, ncmds, _, _, _ = struct.unpack_from("<IiIIIIII", data, 0)
    if magic != 0xFEEDFACF:
        raise SystemExit("not a 64-bit Mach-O")
    out, offset = [], 32
    for _ in range(ncmds):
        cmd, size = struct.unpack_from("<Ii", data, offset)
        if cmd == 0x19:
            name = data[offset + 8:offset + 24].split(b"\0")[0].decode()
            vmaddr, vmsize, fileoff, filesize = struct.unpack_from("<QQQQ", data, offset + 24)
            if filesize:
                out.append((name, vmaddr, vmsize, fileoff, filesize))
        offset += size
    return out


def file_offset(segs, va):
    for name, vmaddr, vmsize, fileoff, filesize in segs:
        if vmaddr <= va < vmaddr + min(vmsize, filesize):
            return fileoff + (va - vmaddr)
    raise SystemExit("%#x not file backed" % va)


def symbols(path):
    table = {}
    for line in subprocess.run(["llvm-nm", "-n", str(path)], capture_output=True, text=True, check=True).stdout.splitlines():
        parts = line.split()
        if len(parts) == 3:
            table.setdefault(int(parts[0], 16), parts[2])
    return table


def function_range(table, name):
    for start, symbol in table.items():
        if symbol == name:
            return start, min(address for address in table if address > start)
    raise SystemExit("no symbol %s" % name)


def find_call(data, segs, table, function, name, occurrence):
    target = next(address for address, symbol in table.items() if symbol == name)
    low, high = function_range(table, function)
    hits = []
    for va in range(low, high, 4):
        word = struct.unpack_from("<I", data, file_offset(segs, va))[0]
        if word >> 26 == 0b100101:
            delta = word & 0x3FFFFFF
            if delta & (1 << 25):
                delta -= 1 << 26
            if va + delta * 4 == target:
                hits.append(va)
    if len(hits) < occurrence:
        raise SystemExit("%s: %d hits for %s" % (function, len(hits), name))
    return hits[occurrence - 1], target


def branch(from_va, to_va):
    delta = (to_va - from_va) // 4
    if (to_va - from_va) % 4 or not -(1 << 25) <= delta < (1 << 25):
        raise SystemExit("branch out of range")
    return 0x14000000 | (delta & 0x3FFFFFF)


def compile_binary(workdir, name, source, va, defs):
    suffix = ".c" if name == "screen" else ".S"
    asm = workdir / (name + suffix)
    obj = workdir / (name + ".o")
    elf = workdir / (name + ".elf")
    binary = workdir / (name + ".bin")
    asm.write_text(source)
    extra = name == "screen"
    cmd = ["clang", "--target=aarch64-none-elf", "-O2", "-ffreestanding",
           "-fno-stack-protector", "-mgeneral-regs-only", "-ffixed-x18", "-c", str(asm), "-o", str(obj)]
    subprocess.run(cmd, check=True)
    subprocess.run(["ld.lld", "-Ttext=%#x" % va,
                    *["--defsym=%s=%#x" % (k, v) for k, v in defs.items()],
                    "-e", "alpha_mark" if extra else "_start", str(obj), "-o", str(elf)], check=True)
    subprocess.run(["llvm-objcopy", "-O", "binary", str(elf), str(binary)], check=True)
    return binary.read_bytes()


def site_source(marker, target, back, entry):
    lines = [".text", ".global _start", "_start:"]
    lines += [
        "  stp x0, x1, [sp, #-16]!",
        "  stp x2, x3, [sp, #-16]!",
        "  stp x4, x5, [sp, #-16]!",
        "  stp x6, x7, [sp, #-16]!",
        "  stp x29, x30, [sp, #-16]!",
        "  mov x29, sp",
        "  mov w0, #%d" % marker,
        "  bl mark_entry",
        "  ldp x29, x30, [sp], #16",
        "  ldp x6, x7, [sp], #16",
        "  ldp x4, x5, [sp], #16",
        "  ldp x2, x3, [sp], #16",
        "  ldp x0, x1, [sp], #16",
        "  bl target",
        "  b back",
        ".ltorg",
    ]
    return "\n".join(lines) + "\n", {"target": target, "back": back, "mark_entry": entry}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("kernel", type=Path)
    parser.add_argument("--cave", type=lambda v: int(v, 0), default=CAVE_BASE)
    args = parser.parse_args()

    data = bytearray(args.kernel.read_bytes())
    segs = segments(data)
    table = symbols(args.kernel)
    ml_io_map = next(address for address, symbol in table.items() if symbol == "_ml_io_map")

    with tempfile.TemporaryDirectory() as tmp:
        workdir = Path(tmp)
        source = SOURCE.read_text()
        screen = compile_binary(workdir, "screen", source, args.cave, {"ml_io_map": ml_io_map})
        entry = args.cave
        off = file_offset(segs, args.cave)
        data[off:off + len(screen)] = screen
        cursor = args.cave + ((len(screen) + 0x3F) & ~0x3F)
        print("alpha_mark %d bytes at %#x (ml_io_map %#x)" % (len(screen), entry, ml_io_map))

        for marker, symbol, function, occurrence in MARKS:
            site, target = find_call(data, segs, table, function, symbol, occurrence)
            src, defs = site_source(marker, target, site + 4, entry)
            code = compile_binary(workdir, "site", src, cursor, defs)
            if len(code) > 0x80:
                raise SystemExit("site cave %d is %d bytes" % (marker, len(code)))
            if cursor + len(code) > CAVE_LIMIT:
                raise SystemExit("out of cave space at mark %d" % marker)
            site_off = file_offset(segs, cursor)
            data[site_off:site_off + len(code)] = code
            struct.pack_into("<I", data, file_offset(segs, site), branch(site, cursor))
            print("mark %2d: %-30s site %#x -> %#x" % (marker, symbol, site, cursor))
            cursor += (len(code) + 0x3F) & ~0x3F

    args.kernel.write_bytes(data)
    print("caves end at %#x" % cursor)


if __name__ == "__main__":
    main()
