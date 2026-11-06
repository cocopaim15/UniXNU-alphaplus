"""Make "Erase boot_a" the built-in default with a 20 s countdown.

The board has no working menu input yet, so an unattended boot has to fall
through to fastboot by itself; the first key press still cancels the timer.
"""
from pathlib import Path

path = Path("/root/aloha/extras/UniXNUPkg/Library/UniXNULib/Config.c")
text = path.read_text(encoding="utf-8")
if 'default = \\"erase-boot\\"' in text:
    print("already patched")
    raise SystemExit(0)

old = '  "[boot]\\n"\n  "timeout = 10\\n"\n  "rotate = 2\\n"'
new = ('  "[boot]\\n"\n'
       '  "timeout = 20\\n"\n'
       '  "default = \\"erase-boot\\"\\n"\n'
       '  "rotate = 2\\n"')

if old not in text:
    raise SystemExit("builtin boot section anchor missing")

text = text.replace(old, new, 1)
path.write_text(text, encoding="utf-8")
print("patched", path)
