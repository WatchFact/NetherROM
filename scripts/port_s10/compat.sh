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

# ExtremeROM's pinned Exynos9820 camera uses three A26 Polarr SDK
# binaries. NetherROM already carries byte-identical binaries from A73.
# Audit the Git *blob hashes*, not names, before reusing the local copies.
# ExtremeROM fifteen @2056320784b7d1d88f9e7025f86f7bbd39945d6b
polarr_dir="$base/prebuilts/samsung/a73xqxx/system/lib64"
while read -r name expected; do
    [ "$name" ] || continue
    test -f "$polarr_dir/$name" || {
        echo "Missing vetted Polarr binary: $name" >&2
        exit 1
    }
    actual="$(git hash-object "$polarr_dir/$name")"
    test "$actual" = "$expected" || {
        echo "Polarr compatibility hash mismatch: $name ($actual)" >&2
        exit 1
    }
done <<'POLARR'
libBestComposition.polarr.so e36deee087bd650f35e06af1dc4136c71663d3ba
libFeature.polarr.so d436d1e0b7927c20e1acf94d4f0f17cd581eb087
libTracking.polarr.so 7c5e2509c2ad69d2dd1a26bb8d73e16bc2b0d181
POLARR

camera="$base/platform/exynos9820/patches/camera/customize.sh"
grep -q '"a26xxx"' "$camera" || {
    echo "Pinned upstream Polarr module changed. Re-review before building." >&2
    exit 1
}
sed -i 's/"a26xxx"/"a73xqxx"/g' "$camera"

# This module's original libstagefright.so offsets are from a different S25
# FE One UI 8 donor. The Aether S24+ One UI 8.5 binary demonstrably lacks the
# first hard-coded instruction pattern. Never write an unchecked ARM64 branch
# at an unrelated offset. Apply only if each exact original sequence exists.
python3 - "$camera" <<'PY'
from pathlib import Path
import sys
path = Path(sys.argv[1])
code = path.read_text()
replacements = {
    'HEX_PATCH "$WORK_DIR/system/system/lib64/libstagefright.so" "da4a0594e0031a2a22feff17" "da4a0594e0031a2a19000014"':
        'python3 "$SRC_DIR/scripts/port_s10/optional_binary_patch.py" stagefright-video-svc "$WORK_DIR/system/system/lib64/libstagefright.so"',
    'HEX_PATCH "$WORK_DIR/system/system/lib64/libstagefright.so" "010140f90a4d0594604d0034" "010140f90a4d05941f2003d5"':
        'python3 "$SRC_DIR/scripts/port_s10/optional_binary_patch.py" stagefright-hdr10 "$WORK_DIR/system/system/lib64/libstagefright.so"',
}
for original, replacement in replacements.items():
    if code.count(original) != 1:
        raise SystemExit(f"Unknown pinned S10 camera source for: {original}")
    code = code.replace(original, replacement)
path.write_text(code)
PY

# The pinned miscellaneous patch also contains an invalid JNI instruction
# replacement: old/new hex lengths differ. Use the reviewed equal-length
# ExtremeROM Bluetooth patch only on an exact match; otherwise leave intact.
misc="$base/platform/exynos9820/patches/miscs/customize.sh"
python3 - "$misc" <<'PY'
from pathlib import Path
import sys
path = Path(sys.argv[1])
text = path.read_text()
original = ('HEX_PATCH "$WORK_DIR/system/system/lib64/libbluetooth_jni.so" \\\n'
            '    "00122a0140395f01086bde030014" "2a00001428008052"')
replacement = ('python3 "$SRC_DIR/scripts/port_s10/optional_binary_patch.py" '
               'bluetooth-jni-legacy "$WORK_DIR/system/system/lib64/libbluetooth_jni.so"')
if text.count(original) != 1:
    raise SystemExit("Unexpected pinned Exynos9820 Bluetooth patch; review required")
path.write_text(text.replace(original, replacement))
PY

# The local A73 public-libraries list has two extra entries not required by
# the S10 camera. Match the original three-entry A26 allowlist.
cat >> "$camera" <<'POLARR_ALLOWLIST'

POLARR_PUBLIC_LIBS="$WORK_DIR/system/system/etc/public.libraries-polarr.txt"
test -f "$POLARR_PUBLIC_LIBS" || {
    ABORT "Missing Exynos9820 Polarr public-libraries list"
    return 1
}
sed -i -e '/^libPolarrSnap\.polarr\.so$/d' \
       -e '/^libYuv\.polarr\.so$/d' "$POLARR_PUBLIC_LIBS"
unset POLARR_PUBLIC_LIBS
POLARR_ALLOWLIST

# The Exynos9820 camera script was pinned from ArtisanROM v3.1.0, whose
# S21 FE donor had more blobs than this newer NetherROM r9sxxx subset.
# Use original v3.1.0 byte-identical p3sxxx libraries, not fake placeholders.
python3 - "$camera" "$base/platform/exynos9820/patches/midas/customize.sh" <<'PY'
from pathlib import Path
import sys
camera, midas = map(Path, sys.argv[1:])
src = camera.read_text()
# Two camera BLOBS_LIST loops are system-library imports; a third loop
# imports SingleTake APK/assets and MUST remain on the real r9 donor.
needle = 'ADD_TO_WORK_DIR "r9sxxx" "system" "$blob" 0 0 644 "u:object_r:system_lib_file:s0"'
if src.count(needle) != 2:
    raise SystemExit("Unexpected camera donor import structure; aborting")
src = src.replace(needle, needle.replace('"r9sxxx"', '"p3sxxx"'))
# Additional imports used to pass on upstream's full r9, but this branch
# only tracks its WFD subset. All these files exist in the reviewed p3 donor.
camera_imports = (
    ('vendor', 'saiv/swisp_1.0'),
)
for partition, name in camera_imports:
    needle = f'ADD_TO_WORK_DIR "r9sxxx" "{partition}" "{name}"'
    if src.count(needle) != 1:
        raise SystemExit(f"Unexpected S10 SWISP import: {needle}")
    src = src.replace(needle, needle.replace('"r9sxxx"', '"p3sxxx"'))
needle = 'ADD_TO_WORK_DIR "r9sxxx" "system" "$blob" 0 0 644 "u:object_r:system_file:s0"'
if src.count(needle) != 1:
    raise SystemExit("Unexpected SingleTake source list")
src = src.replace(needle, needle.replace('"r9sxxx"', '"p3sxxx"'))
camera.write_text(src)
src = midas.read_text()
for partition, name in (
    ("vendor", "etc/midas"),
    ("vendor", "etc/VslMesDetector"),
    ("system", "system/priv-app/PhotoRemasterService/PhotoRemasterService.apk"),
    ("system", "system/lib64/libmidas_core.camera.samsung.so"),
    ("system", "system/lib64/libmidas_DNNInterface.camera.samsung.so"),
):
    needle = f'ADD_TO_WORK_DIR "r9sxxx" "{partition}" "{name}"'
    if src.count(needle) != 1:
        raise SystemExit(f"Unexpected MIDAS source import: {needle}")
    src = src.replace(needle, needle.replace('"r9sxxx"', '"p3sxxx"'))
midas.write_text(src)
PY

# Storage rule references the legacy SoC-specific fstab.
sed -i 's/fstab.exynos990/fstab.exynos9820/g' \
  "$base/platform/exynos9820/patches/storage_compat/customize.sh"
echo "Loaded pinned Exynos9820 HAL/camera patches and Android 16 multilib bridge"
