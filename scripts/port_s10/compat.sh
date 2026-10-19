#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-or-later
set -euo pipefail

# Kernel/HAL/Camera compatibility is device-specific; NEVER reuse S20 blobs.
# Pin the older Exynos9820 port to a reviewed immutable commit.
UPSTREAM="https://github.com/ExtremeXT/ExtremeROM.git"
REV="2056320784b7d1d88f9e7025f86f7bbd39945d6b"
base="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
reference="${RUNNER_TEMP:-/tmp}/netherrom-exynos9820-reference"
rm -rf -- "$reference"
git clone --depth 1 --single-branch --branch fifteen --filter=blob:none --sparse "$UPSTREAM" "$reference"
git -C "$reference" checkout --detach "$REV"
git -C "$reference" sparse-checkout set platform/exynos9820/patches
test "$(git -C "$reference" rev-parse HEAD)" = "$REV"

# The archived port is an input, not a guaranteed modern-Android implementation.
# Copy only the known Exynos9820 modules; never port ExtremeROM's build system.
for module in vendor stock_blobs camera miscs bixbykey midas hrm; do
    from="$reference/platform/exynos9820/patches/$module"
    test -d "$from" || { echo "Missing $module in pinned donor" >&2; exit 1; }
    mkdir -p "$base/platform/exynos9820/patches"
    rm -rf "$base/platform/exynos9820/patches/$module"
    cp -a "$from" "$base/platform/exynos9820/patches/$module"
done
# The S24+ Android 16 donor is 64-bit-only, whereas Exynos9820 still starts
# ARM32 vendor/OMX services. Reuse NetherROM's Android 16 multilib bridge,
# which imports generic ARM32 runtime APEXes and libs, not Exynos990 HALs.
for module in zzz_runtime32_compat storage_compat; do
    source_module="$base/platform/exynos990/patches/$module"
    test -d "$source_module" || { echo "Missing modern $module module" >&2; exit 1; }
    cp -a "$source_module" "$base/platform/exynos9820/patches/$module"
done
# Storage rule references the legacy SoC-specific fstab.
sed -i 's/fstab.exynos990/fstab.exynos9820/g' \
  "$base/platform/exynos9820/patches/storage_compat/customize.sh"
echo "Loaded pinned Exynos9820 HAL/camera patches and Android 16 multilib bridge"
