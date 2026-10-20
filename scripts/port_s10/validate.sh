#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-or-later
set -euo pipefail
root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$root"
for target in beyond0lte beyond1lte beyond2lte beyondx; do
    bash -n "target/$target/config.sh"
    bash -n "target/$target/sff.sh"
    grep -q 'TARGET_PLATFORM="exynos9820"' "target/$target/config.sh"
    grep -q '^TARGET_USE_DYNAMIC_PARTITIONS=false' "target/$target/config.sh"
    grep -q '^TARGET_LCD_CONFIG_HFR_DEFAULT_REFRESH_RATE="60"' "target/$target/config.sh"
    for partition in system vendor product odm boot dtb dtbo; do
        grep -q "/dev/block/by-name/$partition " "target/$target/installer/recovery.fstab"
    done
    TARGET_MODEL="$(sed -n 's/^TARGET_FIRMWARE="\([^/]*\).*/\1/p' "target/$target/config.sh")"
    test -n "$TARGET_MODEL" || exit 1
    echo "Configuration OK: $target ($TARGET_MODEL)"
done
bash -n scripts/internal/build_flashable_zip.sh
bash -n scripts/port_s10/compat.sh
bash -n scripts/port_s10/build_legacy_zip.sh
bash -n scripts/port_s10/kernel.sh
grep -q 'exynos9820' scripts/internal/build_flashable_zip.sh
grep -q 'block_image_update' scripts/port_s10/build_legacy_zip.sh
grep -q 'GET_IMAGE_SIZE' scripts/port_s10/build_legacy_zip.sh
grep -q 'dtb.img' scripts/port_s10/build_legacy_zip.sh
grep -q 'for img in boot dtb dtbo' scripts/port_s10/kernel.sh
# KernelSU requires an explicit decision and cannot be silently enabled.
grep -q '\-k n -r n' scripts/port_s10/kernel.sh
grep -q 's10-preflight.sh' scripts/port_s10/build_legacy_zip.sh
# All source assets required by ExtremeROM's Exynos9820 camera must be
# provided by a vetted local donor or explicitly imported into the build.
grep -q 'libBestComposition.polarr.so e36deee087bd650f35e06af1dc4136c71663d3ba' scripts/port_s10/compat.sh
grep -q 'a73xqxx' scripts/port_s10/compat.sh
# Pinned partition geometry extracted from official ArtisanROM Exynos9820_Repartition.zip.
layout=scripts/port_s10/artisanrom_partition_layout.tsv
test -s "$layout"
for row in 'system 7000 required' 'vendor 1500 required' 'product 1500 required' 'odm 4 required' \
           'prism 600 required' 'optics 30 required' 'cache 600 required' 'omr 50 required' \
           'cp_debug 5 required' 'cp2_debug 5 optional' 'spu 50 optional' 'userdata remaining required'; do
    grep -Fxq "$row" "$layout" || { echo "Missing pinned GPT row: $row" >&2; exit 1; }
done
grep -Fq '802cc8c10acbcd3c7f2b1b73f14fd8f7b26ca4ef9cb6dc12f76f958c030d4e45' "$layout"
grep -q 'layout_minimum' scripts/port_s10/build_legacy_zip.sh
# Unit-test every legacy firmware patch without shipping an unreviewed donor.
python3 - <<'PY'
import importlib.util, tempfile
from pathlib import Path
spec = importlib.util.spec_from_file_location(
    "optional_patch", "scripts/port_s10/optional_binary_patch.py")
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
with tempfile.TemporaryDirectory() as d:
    f = Path(d) / "firmware.so"
    for feature, (old, new) in mod.PATCHES.items():
        f.write_bytes(b"\x7fELF" + bytes.fromhex(old) + b"TEST")
        assert mod.patch(f, feature) == "patched"
        assert mod.patch(f, feature) == "already-patched"
        assert f.read_bytes() == b"\x7fELF" + bytes.fromhex(new) + b"TEST"
        f.write_bytes(b"\x7fELF" + b"\x00" * 128)
        assert mod.patch(f, feature) == "unsupported-donor"
        assert f.read_bytes() == b"\x7fELF" + b"\x00" * 128
        f.write_bytes(bytes.fromhex(old) * 2)
        try:
            mod.patch(f, feature)
        except ValueError:
            pass
        else:
            raise AssertionError(f"{feature}: ambiguous patch did not fail")
print("Optional binary patch unit tests passed")
PY
python3 -m py_compile scripts/port_s10/strict_preflight.py
python3 scripts/port_s10/strict_preflight.py --stage index
echo "S10 static-partition safety checks passed"
