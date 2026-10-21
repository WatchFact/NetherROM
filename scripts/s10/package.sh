#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-or-later
set -eo pipefail
: "${SRC_DIR:?Source buildenv.sh first}"
: "${WORK_DIR:?}"
[[ "$TARGET_PLATFORM" == exynos9820 && "$TARGET_USE_DYNAMIC_PARTITIONS" == false ]]
[[ "$TARGET_CODENAME" == beyond2lte && "${TARGET_FIRMWARE%%/*}" == SM-G975F ]] || {
  echo 'Refusing non-SM-G975F/beyond2lte target firmware' >&2; exit 1;
}
[[ "$TARGET_OS_FILE_SYSTEM_TYPE" == ext4 && "$ROM_VERSION" == 4.0.2 ]]
source "$SRC_DIR/scripts/utils/build_utils.sh"
python3 "$SRC_DIR/scripts/s10/odm_layout.py" finalize "$WORK_DIR" "$TARGET_CODENAME"
tmp="$OUT_DIR/s10-package-$TARGET_CODENAME"
test ! -e "$tmp"
mkdir -p "$tmp/META-INF/com/google/android" "$tmp/META-INF/com/android"
cp "$SRC_DIR/prebuilts/bootable/deprecated-ota/updater" "$tmp/META-INF/com/google/android/update-binary"
chmod 755 "$tmp/META-INF/com/google/android/update-binary"
python3 "$SRC_DIR/scripts/s10/audit_output.py" "$WORK_DIR" "$TARGET_CODENAME" "$APKTOOL_DIR"
for part in system_ext vendor_dlkm odm_dlkm system_dlkm super; do
  test ! -e "$WORK_DIR/$part"
done
printf '{}\n' > "$tmp/sizes.json"
for part in system vendor product odm; do
  image_args=()
  if [[ "$part" == odm ]]; then
    test "$TARGET_ODM_PARTITION_SIZE" = 4194304
    image_args+=(--partition-size "$TARGET_ODM_PARTITION_SIZE")
  fi
  "$SRC_DIR/scripts/build_fs_image.sh" ext4 --no-avb --sparse --generate-map \
    "${image_args[@]}" \
    --output "$tmp/$part.img" "$WORK_DIR/$part" \
    "$WORK_DIR/configs/file_context-$part" "$WORK_DIR/configs/fs_config-$part"
  size="$(GET_IMAGE_SIZE "$tmp/$part.img")"
  python3 - "$tmp/sizes.json" "$part" "$size" "$SRC_DIR" <<'PY'
import json,sys
from pathlib import Path
sys.path.insert(0,str(Path(sys.argv[4])/'scripts/s10'))
from installer import BUDGET
size=int(sys.argv[3]); part=sys.argv[2]
if size <= 0 or size > BUDGET[part]*1048576:
    raise ValueError('Expanded ext4 image exceeds the physical S10 capacity: '+part)
p=Path(sys.argv[1]); d=json.loads(p.read_text()); d[part]=size; p.write_text(json.dumps(d))
PY
  # Check the actual sparse ext4 contents before encoding the block OTA.
  bash "$SRC_DIR/scripts/s10/verify_image.sh" "$part" "$tmp/$part.img"
  img2sdat -o "$tmp" -B "$tmp/$part.map" "$tmp/$part.img"
  test -s "$tmp/$part.transfer.list" && test -s "$tmp/$part.new.dat"
  brotli --quality=4 --output="$tmp/$part.new.dat.br" "$tmp/$part.new.dat"
  python3 - "$tmp" "$part" <<'PY'
from pathlib import Path
import sys
p=Path(sys.argv[1]); part=sys.argv[2]
for ext in ('.img','.map','.new.dat'): (p/(part+ext)).unlink(missing_ok=True)
(p/(part+'.patch.dat')).touch(exist_ok=True)
PY
done
for part in boot dtb dtbo; do
  cp "$WORK_DIR/kernel/$part.img" "$tmp/$part.img"
  python3 - "$tmp/sizes.json" "$part" "$tmp/$part.img" <<'PY'
import json,sys
from pathlib import Path
p=Path(sys.argv[1]); d=json.loads(p.read_text()); d[sys.argv[2]]=Path(sys.argv[3]).stat().st_size; p.write_text(json.dumps(d))
PY
done
python3 "$SRC_DIR/scripts/s10/installer.py" "$tmp" "$TARGET_CODENAME"
cp "$WORK_DIR/kernel/kernel.json" "$tmp/kernel.json"
cp "$SRC_DIR/scripts/s10/hardware-v3.1.0.json" "$tmp/hardware-provenance.json"
cp "$SRC_DIR/scripts/s10/dvfs-stock.json" "$tmp/dvfs-provenance.json"
cp "$WORK_DIR/vintf-provenance.json" "$tmp/vintf-provenance.json"
cp "$WORK_DIR/camera-compatibility.json" "$tmp/camera-compatibility.json"
cp "$WORK_DIR/camera-portrait-provenance.json" "$tmp/camera-portrait-provenance.json"
cp "$WORK_DIR/odm-provenance.json" "$tmp/odm-provenance.json"
cp "$WORK_DIR/face-hidl-provenance.json" "$tmp/face-hidl-provenance.json"
cp "$WORK_DIR/virtual-vibration-provenance.json" "$tmp/virtual-vibration-provenance.json"
cp "$WORK_DIR/wifi-provenance.json" "$tmp/wifi-provenance.json"
if [[ "$TARGET_CODENAME" == beyond0lte ]]; then
  cp "$WORK_DIR/fingerprint-provenance.json" "$tmp/fingerprint-provenance.json"
fi
printf 'ota-type=BLOCK\npre-device=%s\npost-timestamp=%s\n' "$TARGET_CODENAME" "$(date +%s)" > "$tmp/META-INF/com/android/metadata"
printf 'device=%s\nversion=%s\nlayout=physical-ext4\n' "$TARGET_CODENAME" "$ROM_VERSION" > "$tmp/build_info.txt"
unsigned="$OUT_DIR/s10-unsigned-$TARGET_CODENAME.zip"
(cd "$tmp" && 7z a -tzip -mx=0 "$unsigned" .) >/dev/null
name="$OUT_DIR/NetherROM_${ROM_VERSION}_${TARGET_CODENAME}_EXPERIMENTAL.zip"
signapk -w "$SRC_DIR/security/aosp_testkey.x509.pem" "$SRC_DIR/security/aosp_testkey.pk8" "$unsigned" "$name"
python3 "$SRC_DIR/scripts/s10/verify_zip.py" "$name" "$TARGET_CODENAME"
(cd "$OUT_DIR" && sha256sum "$(basename "$name")" > "$(basename "$name").sha256")
echo "Validated physical S10 package: $name"
