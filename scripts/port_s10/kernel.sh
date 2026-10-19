#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-or-later
set -euo pipefail
target="${1:?Expected beyond0lte, beyond1lte, beyond2lte or beyondx}"
case "$target" in
    beyond0lte|beyond1lte|beyond2lte|beyondx) ;;
    *) echo "Unsupported kernel target: $target" >&2; exit 1;;
esac

# ArtisanROM Quant v3.1 Exynos9820 Android 16 kernel. Must be rebuilt with EROFS support; the
# original Android 12 Samsung kernel must never be shipped for One UI 8.5.
KERNEL_REV="9a0a792d227c8ae6cddac0c9d68a8bb9782c44cb"
dir="${RUNNER_TEMP:-/tmp}/netherrom-s10-kernel"
root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
rm -rf "$dir"
git clone --recursive --depth 1 https://github.com/Android-Artisan/android_kernel_samsung_exynos9820.git "$dir"
git -C "$dir" checkout --detach "$KERNEL_REV"
test "$(git -C "$dir" rev-parse HEAD)" = "$KERNEL_REV"
(cd "$dir" && bash ./build.sh -m "$target" -k y -r n)

out="$root/out/target/$target/work_dir/kernel"
mkdir -p "$out"
for img in boot dtbo; do
    test -s "$dir/build/out/$target/$img.img" || {
        echo "Kernel build did not produce $img.img - refusing to package the stock Android 12 kernel" >&2
        exit 1
    }
    cp -f "$dir/build/out/$target/$img.img" "$out/$img.img"
done
echo "Exynos9820 boot.img and dtbo.img installed for $target"
