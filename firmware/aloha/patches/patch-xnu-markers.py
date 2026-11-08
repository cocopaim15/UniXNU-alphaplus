"""Write progress markers into an existing kernel binary.

Each of N call sites is redirected through a small cave that stores a marker
word in a file-backed block (magic "ALPHAMRK") and then executes the call it
replaced. One boot therefore leaves a bitmap of how far the kernel got, and
DarwinBoot can read it back on the next boot - no rebuild, no serial console.

usage: patch-xnu-markers.py <kernel-copy> [--block 0xVA] [--cave 0xVA]
"""
import argparse
import shutil
import struct
import subprocess
import tempfile
from pathlib import Path

MAGIC = b"ALPHAMRK"
SLOT_BASE = 8            # magic[8], then one u32 per mark
CAVE_SIZE = 0x60

# (marker, symbol, function, occurrence, before?)
MARKS = [
    (1,  "_kernel_debug_string_early", "_kernel_bootstrap",            1, False),
    (2,  "_vm_mem_bootstrap",          "_kernel_bootstrap",            1, False),
    (3,  "_machine_init",              "_kernel_bootstrap",            1, False),
    (4,  "_thread_init",               "_kernel_bootstrap",            1, False),
    (5,  "_exception_init",            "_kernel_bootstrap",            1, False),
    (6,  "_kernel_thread_create",      "_kernel_bootstrap",            1, False),
    (7,  "_load_context",              "_kernel_bootstrap",            1, True),
    (8,  "_current_processor",         "_kernel_bootstrap_thread",     1, False),
    (9,  "_idle_thread_create",        "_kernel_bootstrap_thread",     1, False),
    (10, "_sched_startup",             "_kernel_bootstrap_thread",     1, False),
    (11, "_PE_init_iokit",             "_kernel_bootstrap_thread.cold.1", 1, False),
    (12, "_bsd_init",                  "_kernel_bootstrap_thread.cold.1", 1, False),
]

CAVE_DEFAULT = 0xFFFFFFF0073F1500
BLOCK_DEFAULT = 0xFFFFFFF007A73900


def segments(data):
    magic, _, _, _, ncmds, _, _, _ = struct.unpack_from("<IiIIIIII", data, 0)
    if magic != 0xFEEDFACF:
        raise SystemExit("not a 64-bit Mach-O")
    out = []
    offset = 32
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
    raise SystemExit("%#x is not file backed" % va)


def kernel_symbols(path):
    table = {}
    out = subprocess.run(["llvm-nm", "-n", str(path)], capture_output=True, text=True, check=True).stdout
    for line in out.splitlines():
        parts = line.split()
        if len(parts) == 3:
            table.setdefault(int(parts[0], 16), parts[2])
    return table


def function_range(symbols, name):
    for start, symbol in symbols.items():
        if symbol == name:
            return start, min(address for address in symbols if address > start)
    raise SystemExit("no symbol %s" % name)


def find_call(data, segs, symbols, function, name, occurrence):
    target = next((address for address, symbol in symbols.items() if symbol == name), None)
    if target is None:
        raise SystemExit("no symbol %s" % name)
    low, high = function_range(symbols, function)
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
        raise SystemExit("%s has %d call(s) to %s" % (function, len(hits), name))
    return hits[occurrence - 1], target


def branch(from_va, to_va):
    delta = (to_va - from_va) // 4
    if (to_va - from_va) % 4 or not -(1 << 25) <= delta < (1 << 25):
        raise SystemExit("branch out of range")
    return 0x14000000 | (delta & 0x3FFFFFF)


def mov_imm64(reg, value, lines):
    lines.append("  movz x%d, #%d" % (reg, value & 0xFFFF))
    for shift in (16, 32, 48):
        part = (value >> shift) & 0xFFFF
        if part:
            lines.append("  movk x%d, #%d, lsl #%d" % (reg, part, shift))


def cave_source(marker, target, return_va, block_va, before):
    lines = [".text", ".global _start", "_start:"]
    store = []
    store.append("  mov w10, #%d" % marker)
    mov_imm64(9, block_va + SLOT_BASE + 4 * (marker - 1), store)
    store.append("  str w10, [x9]")
    if before:
        lines += store
        lines.append("  bl target")
    else:
        lines.append("  bl target")
        lines += ["  " + row.strip() for row in store]
    lines.append("  b back")
    lines.append(".ltorg")
    return "\n".join(lines) + "\n", {"target": target, "back": return_va}


def assemble(source, va, defs, workdir):
    asm = workdir / "cave.S"
    obj = workdir / "cave.o"
    elf = workdir / "cave.elf"
    binary = workdir / "cave.bin"
    asm.write_text(source)
    subprocess.run(["clang", "--target=aarch64-none-elf", "-c", str(asm), "-o", str(obj)], check=True)
    subprocess.run(["ld.lld", "-Ttext=%#x" % va,
                    *["--defsym=%s=%#x" % (name, value) for name, value in defs.items()],
                    "-e", "_start", str(obj), "-o", str(elf)], check=True)
    subprocess.run(["llvm-objcopy", "-O", "binary", str(elf), str(binary)], check=True)
    return binary.read_bytes()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("kernel", type=Path)
    parser.add_argument("--cave", type=lambda v: int(v, 0), default=CAVE_DEFAULT)
    parser.add_argument("--block", type=lambda v: int(v, 0), default=BLOCK_DEFAULT)
    args = parser.parse_args()

    data = bytearray(args.kernel.read_bytes())
    segs = segments(data)
    symbols = kernel_symbols(args.kernel)

    block_off = file_offset(segs, args.block)
    if any(data[block_off:block_off + 256]):
        raise SystemExit("marker block %#x is not empty" % args.block)
    data[block_off:block_off + len(MAGIC)] = MAGIC

    cave_va = args.cave
    with tempfile.TemporaryDirectory() as tmp:
        workdir = Path(tmp)
        for marker, symbol, function, occurrence, before in MARKS:
            site, target = find_call(data, segs, symbols, function, symbol, occurrence)
            source, defs = cave_source(marker, target, site + 4, args.block, before)
            code = assemble(source, cave_va, defs, workdir)
            if len(code) > CAVE_SIZE:
                raise SystemExit("marker %d cave is %d bytes" % (marker, len(code)))
            cave_off = file_offset(segs, cave_va)
            data[cave_off:cave_off + CAVE_SIZE] = b"\0" * CAVE_SIZE
            data[cave_off:cave_off + len(code)] = code
            struct.pack_into("<I", data, file_offset(segs, site), branch(site, cave_va))
            print("mark %2d: %-30s site %#x -> cave %#x" % (marker, symbol, site, cave_va))
            cave_va += CAVE_SIZE

    args.kernel.write_bytes(data)
    print("block %#x, %d marks, %d cave bytes" % (args.block, len(MARKS), len(MARKS) * CAVE_SIZE))


if __name__ == "__main__":
    main()
