"""Summarise LG Firehose rawprogram XMLs: per-LUN partition layout."""
import re
import sys
from collections import defaultdict
from pathlib import Path

ATTR = re.compile(r'(\w+)="([^"]*)"')


def main():
    root = Path(sys.argv[1])
    rows = []
    for xml in sorted(root.glob("rawprogram*.xml")):
        text = xml.read_text(encoding="utf-8", errors="replace")
        for tag in re.findall(r"<program\b[^>]*>", text):
            attrs = dict(ATTR.findall(tag))
            rows.append(
                {
                    "lun": int(attrs.get("physical_partition_number", 0)),
                    "label": attrs.get("label", "?"),
                    "start": int(attrs.get("start_sector", 0)),
                    "count": int(attrs.get("num_partition_sectors", 0)),
                    "kb": int(attrs.get("size_in_KB", 0)),
                }
            )

    per_lun = defaultdict(list)
    for row in rows:
        per_lun[row["lun"]].append(row)

    for lun in sorted(per_lun):
        items = sorted(per_lun[lun], key=lambda r: r["start"])
        total = defaultdict(lambda: [0, None])  # label -> [sectors, first start]
        for row in items:
            entry = total[row["label"]]
            entry[0] = max(entry[0], row["count"])
            if entry[1] is None:
                entry[1] = row["start"]
        print(f"== LUN {lun}: {len(items)} program entries")
        for label, (count, start) in sorted(total.items(), key=lambda kv: kv[1][1]):
            print(f"  {label:<20} start {start:>9}  sectors {count:>9}  {count * 4096 / 1024 / 1024:8.1f} MiB")


if __name__ == "__main__":
    sys.exit(main())
