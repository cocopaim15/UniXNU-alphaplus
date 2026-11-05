#!/usr/bin/env python3
"""Dump the parts of a device tree the port's board values come from.

Prints root compatible, /memory, /reserved-memory and a few /soc nodes for
whatever DTB or DTBO is handed to it. No external dependencies.

    python3 scripts/fdt-probe.py android-alpha.dtb
"""
import struct
import sys

FDT_BEGIN_NODE = 1
FDT_END_NODE = 2
FDT_PROP = 3
FDT_NOP = 4
FDT_END = 9

INTEREST = (
    "compatible",
    "reg",
    "bootargs",
    "clock-frequency",
    "interrupts",
    "phandle",
)


def u32(buf, off):
    return struct.unpack_from(">I", buf, off)[0]


def cstr(buf, off):
    end = buf.index(b"\x00", off)
    return buf[off:end].decode("utf-8", "replace")


def parse(buf, strings_off):
    """Yield (path, prop-name, raw-value) for every property in the struct block."""
    stack = []
    off = 0
    while True:
        tag = u32(buf, off)
        off += 4
        if tag == FDT_BEGIN_NODE:
            name = cstr(buf, off)
            off += (len(name.encode("utf-8", "replace")) + 1 + 3) & ~3
            stack.append(name)
            yield ("/" + "/".join(part for part in stack if part), None, None)
        elif tag == FDT_END_NODE:
            if stack:
                stack.pop()
        elif tag == FDT_PROP:
            length = u32(buf, off)
            nameoff = u32(buf, off + 4)
            off += 8
            value = buf[off:off + length]
            off += (length + 3) & ~3
            path = "/" + "/".join(part for part in stack if part)
            yield (path, cstr(strings_off, nameoff), value)
        elif tag == FDT_NOP:
            continue
        elif tag == FDT_END:
            return
        else:
            raise SystemExit(f"bad FDT tag {tag:#x} at {off - 4:#x}")


def cells(value, count):
    return [u32(value, i * 4) for i in range(min(count, len(value) // 4))]


def describe(name, value):
    if name == "compatible":
        return " ".join(part.decode("utf-8", "replace")
                        for part in value.split(b"\x00") if part)
    if name in ("reg", "interrupts"):
        return " ".join(f"{n:#x}" for n in cells(value, len(value) // 4))
    if name == "bootargs":
        return value.split(b"\x00")[0].decode("utf-8", "replace")
    if name == "clock-frequency":
        return f"{u32(value, 0)} ({u32(value, 0) / 1e6:.1f} MHz)"
    return value.hex()


def main():
    if len(sys.argv) < 2:
        raise SystemExit(__doc__)
    data = open(sys.argv[1], "rb").read()
    if u32(data, 0) != 0xD00DFEED:
        raise SystemExit(f"{sys.argv[1]}: not a flattened device tree "
                         f"(magic {u32(data, 0):#010x})")

    total = u32(data, 4)
    off_struct = u32(data, 8)
    off_strings = u32(data, 12)
    print(f"file      {sys.argv[1]}")
    print(f"size      {total} bytes ({total / 1e6:.2f} MB)")
    print(f"version   {u32(data, 20)} (last compatible {u32(data, 24)})")
    print()

    blk = data[off_struct:total]
    strtab = data[off_strings:]

    wanted = ("/", "/memory", "/reserved-memory", "/chosen", "/soc")
    only = sys.argv[2] if len(sys.argv) > 2 else None
    seen = {}
    for path, name, value in parse(blk, strtab):
        if name is None:
            continue
        if only and only not in path:
            continue
        if name not in INTEREST:
            continue
        if not any(path == w or path.startswith(w + "/") for w in wanted):
            continue
        seen.setdefault(path, []).append((name, describe(name, value)))

    for path in sorted(seen):
        depth = path.count("/")
        if not seen[path]:
            continue
        print(f"{path}")
        for name, text in seen[path]:
            print(f"    {name:<18} {text}")


if __name__ == "__main__":
    main()
