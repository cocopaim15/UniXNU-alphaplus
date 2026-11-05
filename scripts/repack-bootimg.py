#!/usr/bin/env python3
"""Repack an Android boot image produced by `unixnu bootimg`.

The pinned UniXNU always writes `gzip(BootShim + UEFI FD) + device tree` as the
kernel (scripts/unixnu/bootimg.py, no option). LG's abl on this phone drops back
to fastboot with that image, while Project-Aloha's uncompressed image boots, so
this rewrites the kernel field as the raw shim+FD and leaves everything else
alone.

    python3 scripts/repack-bootimg.py in.img out.img [--drop-ramdisk] [--tree FILE]

`--tree FILE` replaces the device tree appended to the kernel. The Aboot path on
this phone gets `android-alpha.dtb` whole (four concatenated DTBs), while
`unixnu bootimg` only accepts a single tree, so the image has to be re-packed
with the full file before flashing.
"""
import struct
import sys
import zlib


def u32(buf, off):
    return struct.unpack_from("<I", buf, off)[0]


def put32(buf, off, value):
    struct.pack_into("<I", buf, off, value)


def main():
    if len(sys.argv) < 3:
        raise SystemExit(__doc__)
    src, dst = sys.argv[1], sys.argv[2]
    drop = "--drop-ramdisk" in sys.argv
    tree_file = None
    if "--tree" in sys.argv:
        tree_file = sys.argv[sys.argv.index("--tree") + 1]

    data = open(src, "rb").read()
    if data[:8] != b"ANDROID!":
        raise SystemExit(f"{src}: not an Android boot image")

    page = u32(data, 36)
    kernel_size = u32(data, 8)
    ramdisk_size = u32(data, 16)

    kernel_off = page
    ramdisk_off = page + ((kernel_size + page - 1) // page) * page
    kernel = data[kernel_off:kernel_off + kernel_size]
    ramdisk = data[ramdisk_off:ramdisk_off + ramdisk_size]

    if kernel[:2] != b"\x1f\x8b":
        raise SystemExit("kernel is not gzip; nothing to unpack")
    stream = zlib.decompressobj(31)
    raw = stream.decompress(kernel)
    tree = stream.unused_data
    if stream.unconsumed_tail:
        raise SystemExit("trailing bytes after the gzip stream are not the device tree")
    if tree[:4] != b"\xd0\x0d\xfe\xed":
        raise SystemExit(f"appended device tree has no FDT magic ({tree[:4]!r})")
    if tree_file:
        tree = open(tree_file, "rb").read()
        if tree[:4] != b"\xd0\x0d\xfe\xed":
            raise SystemExit(f"{tree_file}: not a device tree")

    new_kernel = raw + tree
    header = bytearray(data[:page])
    put32(header, 8, len(new_kernel))
    put32(header, 16, 0 if drop else len(ramdisk))

    out = bytearray(header)
    out += new_kernel + b"\x00" * (-len(new_kernel) % page)
    if not drop:
        out += ramdisk + b"\x00" * (-len(ramdisk) % page)

    open(dst, "wb").write(out)
    print(f"{dst}: kernel {kernel_size} -> {len(new_kernel)} bytes "
          f"(shim+FD {len(raw)}, dtb {len(tree)}), ramdisk "
          f"{0 if drop else ramdisk_size}, total {len(out)}")


if __name__ == "__main__":
    main()
