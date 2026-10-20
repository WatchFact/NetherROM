#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-or-later
set -euo pipefail
target="${1:?S10 target required}"
case "$target" in beyond0lte|beyond1lte|beyond2lte|beyondx) ;; *) exit 1;; esac
root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
rev=9a0a792d227c8ae6cddac0c9d68a8bb9782c44cb
dir="${RUNNER_TEMP:-/tmp}/s10-kernel-$target"
test ! -e "$dir" # clean build; never continue an old kernel output
git init "$dir"
git -C "$dir" remote add origin https://github.com/Android-Artisan/android_kernel_samsung_exynos9820.git
git -C "$dir" fetch --depth=1 origin "$rev"
git -C "$dir" checkout --detach FETCH_HEAD
test "$(git -C "$dir" rev-parse HEAD)" = "$rev"
# KernelSU is disabled. Its submodule is unnecessary and is never executed.
# The exact AOSP Clang revision is available from Microsoft's AOSP mirror.
clang_rev=70a12c4fe88940ab2b0e6d763492dffa2f07e15a
clang_dir="${RUNNER_TEMP:-/tmp}/s10-clang-$target"
git init "$clang_dir"
git -C "$clang_dir" remote add origin https://github.com/msft-mirror-aosp/platform.prebuilts.clang.host.linux-x86.git
git -C "$clang_dir" sparse-checkout init --cone
git -C "$clang_dir" sparse-checkout set clang-r547379
git -C "$clang_dir" fetch --filter=blob:none --depth=1 origin "$clang_rev"
test "$(git -C "$clang_dir" rev-parse FETCH_HEAD:clang-r547379)" = a86cb6592a29d53254d3a88ff2d8282233a273e2
git -C "$clang_dir" checkout --detach FETCH_HEAD
test "$(git -C "$clang_dir" rev-parse HEAD)" = "$clang_rev"
mkdir -p "$dir/toolchain"
ln -s "$clang_dir/clang-r547379" "$dir/toolchain/clang-r547379"
test -x "$dir/toolchain/clang-r547379/bin/clang-20"
(cd "$dir" && bash build.sh -m "$target" -k n -r n)
grep -qx 'CONFIG_EXT4_FS=y' "$dir/out/.config"
grep -qx 'CONFIG_F2FS_FS=y' "$dir/out/.config"
if grep -qx 'CONFIG_KSU=y' "$dir/out/.config"; then echo 'Unexpected KernelSU' >&2; exit 1; fi
mkdir -p "$root/kernel-artifacts/$target"
cp "$dir/build/out/$target/"{boot,dtb,dtbo}.img "$root/kernel-artifacts/$target/"
cp "$dir/out/.config" "$root/kernel-artifacts/$target/kernel.config"
"$dir/toolchain/clang-r547379/bin/clang-20" --version > "$root/kernel-artifacts/$target/clang-version.txt"
python3 - "$root/kernel-artifacts/$target" "$target" "$rev" <<'PY'
import hashlib,json,sys
from pathlib import Path
p=Path(sys.argv[1])
info={'device':sys.argv[2],'revision':sys.argv[3],'kernelsu':False,'ext4':True,
      'sha256':{n:hashlib.sha256((p/n).read_bytes()).hexdigest() for n in ('boot.img','dtb.img','dtbo.img')}}
(p/'kernel.json').write_text(json.dumps(info,indent=2)+'\n')
PY
python3 "$root/scripts/s10/kernel_artifacts.py" "$root/kernel-artifacts/$target" "$root/kernel-check/$target" "$target"

# Artifacts have been validated; reclaim the source/compiler space before firmware extraction.
python3 - "$dir" "$clang_dir" <<'PY_CLEAN'
import shutil,sys
for directory in sys.argv[1:]: shutil.rmtree(directory)
PY_CLEAN
