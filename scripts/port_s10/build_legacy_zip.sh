#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-or-later
# S10 Exynos9820 legacy updater, based on ArtisanROM v3.1.0 physical OTA path.
# There is deliberately no dynamic-partition or super-image support here.
set -eo pipefail

: "${SRC_DIR:?source buildenv.sh before invoking}"
: "${WORK_DIR:?}"
: "${OUT_DIR:?}"
case "$TARGET_CODENAME" in
  beyond0lte|beyond1lte|beyond2lte|beyondx) ;;
  *) echo "Refusing unknown S10 model $TARGET_CODENAME" >&2; exit 1 ;;
esac
[[ "$TARGET_PLATFORM" == exynos9820 && "$TARGET_USE_DYNAMIC_PARTITIONS" == false ]] || {
  echo "Exynos9820 physical OTA only; wrong platform" >&2; exit 1;
}
[[ "$TARGET_OS_FILE_SYSTEM_TYPE" == ext4 ]] || {
  echo "Legacy S10 physical partition requires ext4" >&2; exit 1;
}
source "$SRC_DIR/scripts/utils/build_utils.sh"
source "$SRC_DIR/scripts/utils/install_utils.sh"

tmp="$OUT_DIR/s10-legacy-tmp"
rm -rf -- "$tmp"
mkdir -p "$tmp/META-INF/com/google/android" "$tmp/META-INF/com/android"
trap 'rm -rf -- "$tmp"' EXIT
cp -a "$SRC_DIR/prebuilts/bootable/deprecated-ota/updater" "$tmp/META-INF/com/google/android/update-binary"
fstab="$SRC_DIR/target/$TARGET_CODENAME/installer/recovery.fstab"
[[ -s "$fstab" ]] || { echo "Missing legacy recovery.fstab" >&2; exit 1; }

device_for() {
  local device
  device="$(awk -v mount="/$1" '$1 !~ /^#/ && $2 == mount {print $1}' "$fstab")"
  [[ "$device" == "/dev/block/by-name/$1" ]] || {
    echo "Refusing non-physical or ambiguous mapping: $1 -> $device" >&2; return 1;
  }
  printf '%s' "$device"
}

# S10 has physical system/vendor/product/odm. Never create or write dynamic
# system_ext/dlkm or a super image. Require recovery to expose these devices.
for unexpected in system_ext vendor_dlkm odm_dlkm system_dlkm super; do
  [[ ! -d "$WORK_DIR/$unexpected" ]] || {
    echo "Unexpected legacy partition: $unexpected" >&2; exit 1;
  }
done
partitions=(system vendor product odm)
for partition in "${partitions[@]}"; do
  [[ -d "$WORK_DIR/$partition" ]] || { echo "Missing $partition tree" >&2; exit 1; }
  [[ -s "$WORK_DIR/configs/file_context-$partition" ]] || exit 1
  [[ -s "$WORK_DIR/configs/fs_config-$partition" ]] || exit 1
  device_for "$partition" >/dev/null
done

cat > "$tmp/s10-preflight.sh" <<'SH'
#!/sbin/sh
# Fail BEFORE any block update if partition layout is incompatible.
set -eu
PATH=/sbin:/system/bin:/bin:/usr/bin:$PATH
command -v blockdev >/dev/null 2>&1 || { echo "No blockdev in recovery"; exit 1; }
SH

for partition in "${partitions[@]}"; do
  "$SRC_DIR/scripts/build_fs_image.sh" ext4 --no-avb \
    --generate-map --sparse --output "$tmp/$partition.img" \
    "$WORK_DIR/$partition" \
    "$WORK_DIR/configs/file_context-$partition" \
    "$WORK_DIR/configs/fs_config-$partition"

  device="$(device_for "$partition")"
  # Sparse .img file byte length is wrong for capacity checks.
  # GET_IMAGE_SIZE calculates the real expanded logical partition size.
  needed="$(GET_IMAGE_SIZE "$tmp/$partition.img")"
  [[ "$needed" =~ ^[0-9]+$ && "$needed" -gt 0 ]] || exit 1
  printf 'device="%s"\nrequired="%s"\n' "$device" "$needed" >> "$tmp/s10-preflight.sh"
  cat >> "$tmp/s10-preflight.sh" <<'SH'
[ -b "$device" ] || { echo "Missing physical block device $device"; exit 1; }
capacity=$(blockdev --getsize64 "$device") || exit 1
[ "$capacity" -ge "$required" ] || {
  echo "Physical $device is too small: $capacity bytes, need $required"; exit 1;
}
SH

  # The original non-dynamic update format: ext4 -> transfer.list/new.dat.br.
  img2sdat -o "$tmp" "$tmp/$partition.img"
  [[ -s "$tmp/$partition.transfer.list" && -s "$tmp/$partition.new.dat" ]] || exit 1
  rm -f "$tmp/$partition.img" "$tmp/$partition.map"
  brotli --quality="${UNICA_BROTLI_QUALITY:-6}" \
    --output="$tmp/$partition.new.dat.br" "$tmp/$partition.new.dat"
  rm -f "$tmp/$partition.new.dat"
done

# Only new target-specific boot/dtbo, never an S20 kernel or kernel from stock.
for image in boot dtb dtbo; do
  [[ -s "$WORK_DIR/kernel/$image.img" ]] || {
    echo "Missing rebuilt S10 kernel component $image.img" >&2; exit 1;
  }
  cp "$WORK_DIR/kernel/$image.img" "$tmp/$image.img"
  # Physical kernel/DT partitions must also fit before touching system.
  device="$(device_for "$image")"
  required="$(stat -c%s "$tmp/$image.img")"
  printf 'device="%s"\nrequired="%s"\n' "$device" "$required" >> "$tmp/s10-preflight.sh"
  cat >> "$tmp/s10-preflight.sh" <<'SH'
[ -b "$device" ] || { echo "Missing kernel block device $device"; exit 1; }
capacity=$(blockdev --getsize64 "$device") || exit 1
[ "$capacity" -ge "$required" ] || {
  echo "Kernel/DT partition $device too small: $capacity < $required"; exit 1;
}
SH
done

chmod 755 "$tmp/s10-preflight.sh"
script="$tmp/META-INF/com/google/android/updater-script"
{
  printf 'ui_print("NetherROM S10 legacy ext4 OTA: %s");\n' "$TARGET_CODENAME"
  printf 'assert(getprop("ro.product.device") == "%s"' "$TARGET_CODENAME"
  IFS=':' read -r -a models <<< "$TARGET_ASSERT_MODEL"
  for model in "${models[@]}"; do
    [[ "$model" =~ ^SM-[A-Za-z0-9]+$ ]] || exit 1
    printf ' || getprop("ro.boot.em.model") == "%s"' "$model"
  done
  echo ' || abort("Wrong device for this S10 package"));'
  echo 'package_extract_file("s10-preflight.sh", "/tmp/s10-preflight.sh");'
  echo 'set_perm(0, 0, 0755, "/tmp/s10-preflight.sh");'
  echo 'assert(run_program("/tmp/s10-preflight.sh") == 0);'
  echo 'show_progress(0.95, 200);'
  for partition in "${partitions[@]}"; do
    device="$(device_for "$partition")"
    printf 'ui_print("Installing physical %s...");\n' "$partition"
    printf 'assert(block_image_update("%s", package_extract_file("%s.transfer.list"), "%s.new.dat.br", "%s.patch.dat"));\n' "$device" "$partition" "$partition" "$partition"
  done
  echo 'assert(package_extract_file("boot.img", "/dev/block/by-name/boot"));'
  echo 'assert(package_extract_file("dtb.img", "/dev/block/by-name/dtb"));'
  echo 'assert(package_extract_file("dtbo.img", "/dev/block/by-name/dtbo"));'
  echo 'set_progress(1.0);'
  echo 'ui_print("Installation finished; boot testing required.");'
} > "$script"

cat > "$tmp/META-INF/com/android/metadata" <<EOF
ota-type=BLOCK
pre-device=$TARGET_CODENAME
post-timestamp=$(date +%s)
EOF
printf 'device=%s\nversion=%s\nlayout=legacy-physical\nfilesystem=ext4\n' \
  "$TARGET_CODENAME" "$ROM_VERSION" > "$tmp/build_info.txt"

# Extra guard against accidentally invoking the modern S20 packager.
! find "$tmp" -name '*super*' -o -name 'dynamic_partitions_op_list' | grep -q .

name="NetherROM_EXPERIMENTAL_${ROM_VERSION}_$(date +%Y%m%d)_${TARGET_CODENAME}.zip"
unsigned="$tmp/rom-unsigned.zip"
(cd "$tmp" && 7z a -tzip -mx=0 "$unsigned" . -x'!rom-unsigned.zip') >/dev/null

if [[ "${ROM_IS_OFFICIAL:-false}" == true ]]; then
  key="$SRC_DIR/security/artisanrom_ota"
else
  key="$SRC_DIR/security/aosp_testkey"
fi
[[ -s "$key.pk8" && -s "$key.x509.pem" ]] || {
  echo "Missing signing key; refusing unsigned ROM" >&2; exit 1;
}
signapk -w "$key.x509.pem" "$key.pk8" "$unsigned" "$OUT_DIR/$name"
echo "Created physical-partition legacy S10 installer: $OUT_DIR/$name"
