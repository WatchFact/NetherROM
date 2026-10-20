#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-or-later
set -euo pipefail

# Kernel/HAL/Camera compatibility is device-specific; NEVER reuse S20 blobs.
# Pin the older Exynos9820 port to a reviewed immutable commit.
UPSTREAM="https://github.com/ArtisanROM/ArtisanROM.git"
REV="4d30365b4452a651cc87af8e91733ec1c862f716"
base="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
reference="${RUNNER_TEMP:-/tmp}/netherrom-exynos9820-reference"
rm -rf -- "$reference"
git clone --depth 1 --single-branch --branch v3.1.0 --filter=blob:none --sparse "$UPSTREAM" "$reference"
git -C "$reference" checkout --detach "$REV"
git -C "$reference" sparse-checkout set platform/exynos9820/patches
test "$(git -C "$reference" rev-parse HEAD)" = "$REV"

# The archived port is an input, not a guaranteed modern-Android implementation.
# Copy only the known Exynos9820 modules; never port ExtremeROM's build system.
for module in audio vendor stock_blobs camera miscs bixbykey midas hrm; do
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

# Keep the original pinned misc script but replace its malformed Bluetooth
# hex patch (old/new lengths differ) with the guarded exact-match patcher.
misc="$base/platform/exynos9820/patches/miscs/customize.sh"
python3 - "$misc" <<'PY'
from pathlib import Path
import sys
path=Path(sys.argv[1])
source=path.read_text()
old=('HEX_PATCH "$WORK_DIR/system/system/lib64/libbluetooth_jni.so" \\\n'
     '    "00122a0140395f01086bde030014" "2a00001428008052"')
new=('python3 "$SRC_DIR/scripts/port_s10/optional_binary_patch.py" '
     'bluetooth-jni-legacy "$WORK_DIR/system/system/lib64/libbluetooth_jni.so"')
if source.count(old)!=1:
    raise SystemExit("Unexpected pinned S10 Bluetooth patch")
path.write_text(source.replace(old,new))
PY

# Replace downloaded *code* with reviewed, tracked implementation. Upstream
# binary APK assets are retained, but only these scripts can mutate the ROM.
camera="$base/platform/exynos9820/patches/camera/customize.sh"
midas="$base/platform/exynos9820/patches/midas/customize.sh"
install -m 644 "$base/scripts/port_s10/camera_customize.sh" "$camera"
install -m 644 "$base/scripts/port_s10/midas_customize.sh" "$midas"
cmp -s "$camera" "$base/scripts/port_s10/camera_customize.sh"
cmp -s "$midas" "$base/scripts/port_s10/midas_customize.sh"
echo "Installed tracked Exynos9820 camera and MIDAS modules (applied by make_rom.sh)"

# Storage rule references the legacy SoC-specific fstab.
sed -i 's/fstab.exynos990/fstab.exynos9820/g' \
  "$base/platform/exynos9820/patches/storage_compat/customize.sh"
echo "Loaded pinned Exynos9820 HAL/camera patches and Android 16 multilib bridge"
