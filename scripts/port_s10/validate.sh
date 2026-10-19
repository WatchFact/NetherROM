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
echo "S10 static-partition safety checks passed"
