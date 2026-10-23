#!/usr/bin/env python3
"""Generate a physical S10 block installer; capacity checks precede all writes."""
import json
import re
import sys
from pathlib import Path

BUDGET = {"system": 7000, "vendor": 1500, "product": 1500, "odm": 4}
DEVICES = {"beyond2lte": ("SM-G975F", "SM-G975F/DS")}


def generate(device, sizes):
    if device != 'beyond2lte':
        raise ValueError('This branch only supports Galaxy S10+ SM-G975F/DS (beyond2lte)')
    models = DEVICES[device]
    if set(sizes) != set(BUDGET) | {"boot", "dtb", "dtbo"}:
        raise ValueError("Unexpected or missing partition")
    preflight = ['#!/sbin/sh', 'set -eu', 'PATH=/sbin:/system/bin:/bin:/usr/bin:$PATH',
                 'command -v blockdev >/dev/null',
                 'command -v readlink >/dev/null',
                 'seen_devices="|"']
    for part, size in sizes.items():
        if type(size) is not int or size <= 0:
            raise ValueError(f"Invalid expanded image size for {part}")
        minimum = 0
        if part in BUDGET:
            # System/vendor/product sizes depend on the user's installed
            # repartitioner layout. Check their *actual* block capacity in
            # recovery before any write instead of assuming stock sizes.
            # ODM is deliberately fixed to the reviewed physical 4 MiB layout.
            if part == 'odm':
                if size > BUDGET['odm'] * 1048576:
                    raise ValueError("odm exceeds the reviewed 4 MiB physical partition")
                minimum = BUDGET['odm'] * 1048576
        preflight.extend([f'device=/dev/block/by-name/{part}',
            '[ -b "$device" ] || { echo "Missing $device"; exit 1; }',
            'resolved=$(readlink -f "$device")',
            '[ -n "$resolved" ] || { echo "Cannot resolve $device"; exit 1; }',
            'case "$resolved" in /dev/block/*) ;; *) echo "Unexpected block path: $resolved"; exit 1 ;; esac',
            'case "$seen_devices" in *"|$resolved|"*) echo "Aliased partitions: $device and $resolved"; exit 1 ;; esac',
            'seen_devices="${seen_devices}${resolved}|"',
            'capacity=$(blockdev --getsize64 "$device")',
            f'[ "$capacity" -ge {max(size, minimum)} ] || {{ echo "Partition too small: $device"; exit 1; }}'])
    # Require BOTH the proper device codename and an SM-G975F/DS model.
    # Refuse recovery environments that cannot establish both identities.
    model_checks = [f'getprop("{key}") == "{model}"'
                    for key in ("ro.boot.em.model", "ro.product.model", "ro.product.vendor.model")
                    for model in models]
    checks = f'(getprop("ro.product.device") == "{device}") && (' + ' || '.join(model_checks) + ')'
    updater = [f'ui_print("NetherROM 4.0.2 for {device} - legacy ext4 OTA");',
               'assert(' + checks + ' || abort("Wrong S10+ model/codename; expected SM-G975F (beyond2lte)"));',
               'assert(package_extract_file("s10-preflight.sh", "/tmp/s10-preflight.sh"));',
               'set_perm(0, 0, 0755, "/tmp/s10-preflight.sh");',
               'assert(run_program("/tmp/s10-preflight.sh") == 0);',
               'show_progress(0.90, 300);']
    for part in BUDGET:
        updater += [f'ui_print("Installing {part}...");',
            f'assert(block_image_update("/dev/block/by-name/{part}", package_extract_file("{part}.transfer.list"), "{part}.new.dat.br", "{part}.patch.dat"));']
    for part in ("boot", "dtb", "dtbo"):
        updater.append(f'assert(package_extract_file("{part}.img", "/dev/block/by-name/{part}"));')
    updater += ['set_progress(1.0);', 'ui_print("Installation complete.");']
    return '\n'.join(preflight) + '\n', '\n'.join(updater) + '\n'


if __name__ == "__main__":
    directory = Path(sys.argv[1])
    preflight, updater = generate(sys.argv[2], json.loads((directory / "sizes.json").read_text()))
    (directory / "s10-preflight.sh").write_text(preflight)
    (directory / "s10-preflight.sh").chmod(0o755)
    (directory / "META-INF/com/google/android/updater-script").write_text(updater)
