"""Stop the built-in fallback from forcing the default entry back to index 0."""
from pathlib import Path

path = Path("/root/aloha/extras/UniXNUPkg/Library/UniXNULib/Config.c")
text = path.read_text(encoding="utf-8")
if "keeps the default its own" in text:
    print("already patched")
    raise SystemExit(0)

old = "    Config->DefaultIndex = 0;\n    UnicodeSPrint (Label, sizeof (Label), L\"built-in configuration\");"
new = ("    // The built-in fallback keeps the default its own [boot] section names.\n"
       "    UnicodeSPrint (Label, sizeof (Label), L\"built-in configuration\");")

if old not in text:
    raise SystemExit("anchor missing")

text = text.replace(old, new, 1)
path.write_text(text, encoding="utf-8")
print("patched", path)
