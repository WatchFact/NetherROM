#!/usr/bin/env bash
# Signed S10+ physical ext4 block OTA. Never repartitions or touches userdata.
set -euo pipefail
: "${SRC_DIR:?Source buildenv.sh first}"
: "${WORK_DIR:?Missing work directory}"
[[ "$TARGET_PLATFORM" == exynos9820 && "$TARGET_USE_DYNAMIC_PARTITIONS" == false ]]
[[ "$TARGET_CODENAME" == beyond2lte && "${TARGET_FIRMWARE%%/*}" == SM-G975F ]]
[[ "$TARGET_OS_FILE_SYSTEM_TYPE" == ext4 && "$ROM_VERSION" == 4.0.2 ]]

source "$SRC_DIR/scripts/utils/build_utils.sh"
python3 "$SRC_DIR/scripts/s10/odm_layout.py" finalize "$WORK_DIR" "$TARGET_CODENAME"
python3 "$SRC_DIR/scripts/s10/trim_optional.py" "$WORK_DIR"
python3 "$SRC_DIR/scripts/s10/audit_output.py" "$WORK_DIR" "$TARGET_CODENAME" "$APKTOOL_DIR"
for forbidden in system_ext vendor_dlkm odm_dlkm system_dlkm super; do
  [[ ! -e "$WORK_DIR/$forbidden" ]] || { echo "Unexpected partition: $forbidden" >&2; exit 1; }
done

workspace=$(mktemp -d "$OUT_DIR/.s10-package.XXXXXXXX")
trap 'rm -rf -- "$workspace"' EXIT
stage="$workspace/root"
mkdir -p "$stage/META-INF/com/google/android" "$stage/META-INF/com/android"
cp "$SRC_DIR/prebuilts/bootable/deprecated-ota/updater" "$stage/META-INF/com/google/android/update-binary"
chmod 755 "$stage/META-INF/com/google/android/update-binary"
sizes="$stage/sizes.json"
printf '{}\n' > "$sizes"

record_size() {
  python3 - "$sizes" "$1" "$2" <<'PY'
import json, sys
from pathlib import Path
path, name, value = Path(sys.argv[1]), sys.argv[2], int(sys.argv[3])
if value <= 0 or (name == 'odm' and value > 4194304):
    raise ValueError('Invalid S10 partition image size: ' + name)
info = json.loads(path.read_text())
info[name] = value
path.write_text(json.dumps(info) + '\n')
PY
}

# Allow oversized images to be produced for offline analysis. This does NOT
# make them flashable: installer.py retains recovery-time block capacity checks.
# Print partition tree sizes as diagnostics rather than aborting the build.
python3 - "$WORK_DIR" <<'PY'
import os, shutil, sys
from pathlib import Path
root = Path(sys.argv[1])
for name in ('system', 'vendor', 'product', 'odm'):
    tree = root / name
    if not tree.is_dir():
        raise SystemExit(f'Missing required partition tree: {tree}')
    total = sum(p.stat().st_size for p in tree.rglob('*') if p.is_file() and not p.is_symlink())
    print(f'{name}: {total:,} logical bytes (image size unrestricted; physical fit not guaranteed)', flush=True)
usage = shutil.disk_usage(os.environ.get('OUT_DIR', str(root)))
print(f'Packaging free disk: {usage.free:,} bytes', flush=True)
if usage.free < 3 * 1024**3:
    raise SystemExit('Less than 3 GiB free before packaging.')
PY

for part in system vendor product odm; do
  options=()
  if [[ "$part" == odm ]]; then
    [[ "$TARGET_ODM_PARTITION_SIZE" == 4194304 ]]
    options=(--partition-size 4194304)
  fi
  "$SRC_DIR/scripts/build_fs_image.sh" ext4 --no-avb --sparse --generate-map \
    "${options[@]}" --output "$stage/$part.img" "$WORK_DIR/$part" \
    "$WORK_DIR/configs/file_context-$part" "$WORK_DIR/configs/fs_config-$part"
  record_size "$part" "$(GET_IMAGE_SIZE "$stage/$part.img")"
  bash "$SRC_DIR/scripts/s10/verify_image.sh" "$part" "$stage/$part.img"
  img2sdat -o "$stage" -B "$stage/$part.map" "$stage/$part.img"
  [[ -s "$stage/$part.transfer.list" && -s "$stage/$part.new.dat" ]]
  brotli --quality=4 --output="$stage/$part.new.dat.br" "$stage/$part.new.dat"
  [[ -s "$stage/$part.new.dat.br" ]]
  rm -f "$stage/$part.img" "$stage/$part.map" "$stage/$part.new.dat"
  : > "$stage/$part.patch.dat"
done

for part in boot dtb dtbo; do
  cp "$WORK_DIR/kernel/$part.img" "$stage/$part.img"
  record_size "$part" "$(stat -c %s "$stage/$part.img")"
done
python3 "$SRC_DIR/scripts/s10/installer.py" "$stage" "$TARGET_CODENAME"
cp "$WORK_DIR/kernel/kernel.json" "$stage/kernel.json"
cp "$WORK_DIR/optional-trim-provenance.json" "$stage/optional-trim-provenance.json"
cp "$SRC_DIR/scripts/s10/hardware-v3.1.0.json" "$stage/hardware-provenance.json"
cp "$SRC_DIR/scripts/s10/dvfs-stock.json" "$stage/dvfs-provenance.json"
# Only include provenance files that the build actually produces. The camera
# compatibility audit currently emits camera-compatibility.json (not a
# *-provenance.json file); missing required records still fail packaging.
for name in vintf camera-portrait odm face-hidl virtual-vibration wifi; do
  source="$WORK_DIR/$name-provenance.json"
  [[ -s "$source" ]] || { echo "Missing required provenance: $source" >&2; exit 1; }
  cp "$source" "$stage/$name-provenance.json"
done
camera_record="$WORK_DIR/camera-compatibility.json"
[[ -s "$camera_record" ]] || { echo "Missing required camera audit: $camera_record" >&2; exit 1; }
cp "$camera_record" "$stage/camera-compatibility.json"
printf 'ota-type=BLOCK\npre-device=%s\npost-timestamp=%s\n' \
  "$TARGET_CODENAME" "$(date +%s)" > "$stage/META-INF/com/android/metadata"
printf 'device=%s\nversion=%s\nlayout=physical-ext4\n' \
  "$TARGET_CODENAME" "$ROM_VERSION" > "$stage/build_info.txt"

unsigned="$workspace/unsigned.zip"
output="$OUT_DIR/NetherROM_${ROM_VERSION}_${TARGET_CODENAME}_EXPERIMENTAL.zip"
[[ ! -e "$output" ]] || { echo "Refusing to overwrite $output" >&2; exit 1; }
(cd "$stage" && 7z a -tzip -mx=0 "$unsigned" .) >/dev/null
signapk -w "$SRC_DIR/security/aosp_testkey.x509.pem" \
  "$SRC_DIR/security/aosp_testkey.pk8" "$unsigned" "$output"
python3 "$SRC_DIR/scripts/s10/verify_zip.py" "$output" "$TARGET_CODENAME"
(cd "$OUT_DIR" && sha256sum "$(basename "$output")" > "$(basename "$output").sha256")
echo "Signed, verified S10+ ROM: $output"
