#!/usr/bin/env python3
"""S10+ legacy ext4 updater: CPU gate and a separate block-write guard."""
import json
import sys
from pathlib import Path

DEVICE = 'beyond2lte'
DEVICES = {DEVICE: ('SM-G975F', 'SM-G975F/DS')}
BUDGET = {'system': 7000, 'vendor': 1500, 'product': 1500, 'odm': 4}
PARTS = tuple(BUDGET)
RAW = ('boot', 'dtb', 'dtbo')
GUARD = 's10-install-guard.sh'
UPDATER = 'META-INF/com/google/android/updater-script'


def generate(device, sizes):
    if device != DEVICE:
        raise ValueError('This ROM only supports Galaxy S10+ beyond2lte')
    if set(sizes) != set(PARTS + RAW) or any(type(v) is not int or v <= 0 for v in sizes.values()):
        raise ValueError('Missing, unexpected, or invalid partition size')
    if sizes['odm'] > BUDGET['odm'] * 1048576 or any(sizes[p] % 4096 for p in PARTS):
        raise ValueError('ODM exceeds 4 MiB or ext4 image is unaligned')

    limits = ''.join(f'{p} {max(sizes[p], 4194304 if p == "odm" else 0)}\n' for p in PARTS + RAW)
    guard = '''#!/sbin/sh
set -eu
PATH=/sbin:/system/bin:/bin:/usr/bin:$PATH
command -v blockdev >/dev/null
command -v readlink >/dev/null
[ -r /proc/mounts ] || { echo 'Cannot inspect recovery mounts'; exit 1; }
seen='|'
while read -r part minimum; do
  device=/dev/block/by-name/$part
  [ -b "$device" ] || { echo "Missing $device"; exit 1; }
  resolved=$(readlink -f "$device")
  case "$resolved" in /dev/block/*) ;; *) echo "Unexpected block path: $resolved"; exit 1 ;; esac
  case "$seen" in *"|$resolved|"*) echo "Aliased partitions: $device"; exit 1 ;; esac
  seen="$seen$resolved|"
  while read -r source rest; do
    case "$source" in /dev/block/*)
      mounted=$(readlink -f "$source" 2>/dev/null || true)
      [ "$mounted" != "$resolved" ] || { echo "Partition is mounted: $device"; exit 1; }
    ;; esac
  done < /proc/mounts
  capacity=$(blockdev --getsize64 "$device")
  [ "$capacity" -ge "$minimum" ] || { echo "Partition too small: $device"; exit 1; }
done <<'CAPACITIES'
''' + limits + 'CAPACITIES\n'

    cpu = ' || '.join(f'getprop("{key}") == "exynos9820"' for key in
                     ('ro.board.platform', 'ro.hardware', 'ro.boot.hardware', 'ro.hardware.chipname'))
    models = ' || '.join(f'getprop("{key}") == "{model}"' for key in
                         ('ro.boot.em.model', 'ro.product.model', 'ro.product.vendor.model')
                         for model in DEVICES[device])
    identity = f'(getprop("ro.product.device") == "{device}") && ({models})'
    updater = [
        'ui_print("NetherROM 4.0.2 - S10+ physical ext4");',
        f'assert(({cpu}) || abort("Unsupported CPU: Exynos9820 required"));',
        f'assert({identity} || abort("Wrong S10+ model/codename"));',
        f'assert(package_extract_file("{GUARD}", "/tmp/{GUARD}"));',
        f'set_perm(0, 0, 0755, "/tmp/{GUARD}");',
        f'assert(run_program("/tmp/{GUARD}") == 0);',
        'show_progress(0.90, 300);',
    ]
    for part in PARTS:
        updater.extend((f'ui_print("Installing {part}...");',
                        f'assert(block_image_update("/dev/block/by-name/{part}", '
                        f'package_extract_file("{part}.transfer.list"), '
                        f'"{part}.new.dat.br", "{part}.patch.dat"));'))
    for part in RAW:
        updater.append(f'assert(package_extract_file("{part}.img", "/dev/block/by-name/{part}"));')
    updater.extend(('set_progress(1.0);', 'ui_print("Installation complete.");'))
    return guard, '\n'.join(updater) + '\n'


if __name__ == '__main__':
    directory = Path(sys.argv[1])
    guard, updater = generate(sys.argv[2], json.loads((directory / 'sizes.json').read_text()))
    (directory / GUARD).write_text(guard)
    (directory / GUARD).chmod(0o755)
    (directory / UPDATER).write_text(updater)
