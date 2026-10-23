#!/usr/bin/env bash
# Reject any ROM whose ext4 payload omits or alters the S10 camera patch.
set -euo pipefail
test -n "$WORK_DIR"
test "$#" -eq 2
partition="$1"
sparse_img="$2"
case "$partition" in system|vendor) ;; *) exit 2 ;; esac
for tool in simg2img debugfs cmp; do
  command -v "$tool" >/dev/null || { echo "Missing ext4 audit tool: $tool" >&2; exit 1; }
done
test -s "$sparse_img"
temp="$(mktemp -d /tmp/s10-camera-XXXXXXXX)"
trap 'rm -rf -- "$temp"' EXIT
raw="$temp/$partition.raw"
simg2img "$sparse_img" "$raw"
test -s "$raw"
if [ "$partition" = system ]; then
  files="
system/lib64/libeden_wrapper_system.so
system/lib64/libSwIsp_core.camera.samsung.so
system/lib64/libBestComposition.polarr.so
system/lib64/libmidas_core.camera.samsung.so
system/priv-app/SamsungCamera/SamsungCamera.apk
system/priv-app/SingleTakeService/SingleTakeService.apk
system/priv-app/PhotoRemasterService/PhotoRemasterService.apk
system/etc/public.libraries-polarr.txt
"
else
  files="
etc/midas/midas_config.json
etc/singletake/ClarityScorer/ClarityScorer.tflite
saiv/swisp_1.0/db/denoise_model_832x1072x4_0818.pb
"
fi
for relative in $files; do
  staged="$WORK_DIR/$partition/$relative"
  test -s "$staged" || { echo "Absent from staged ROM: $staged" >&2; exit 1; }
  extracted="$temp/$(printf '%s' "$relative" | tr / _)"
  debugfs -R "dump /$relative $extracted" "$raw" > "$temp/debugfs.log" 2>&1 || {
    cat "$temp/debugfs.log" >&2; exit 1;
  }
  test -s "$extracted" || {
    echo "ABSENT INSIDE ext4 image: $partition:/$relative" >&2
    cat "$temp/debugfs.log" >&2; exit 1;
  }
  cmp -s "$staged" "$extracted" || {
    echo "DIFFERENT BYTES INSIDE ext4 image: $partition:/$relative" >&2; exit 1;
  }
  echo "VERIFIED image contains patched camera file: $partition:/$relative"
done
echo "EXYNOS9820 CAMERA PRESENT IN FINAL $partition IMAGE"
