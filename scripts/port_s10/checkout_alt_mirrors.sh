#!/usr/bin/env bash
set -euo pipefail
# This exact pinned git SHA is present at LineageOS' AOSP mirror.
# Use an insteadOf rewrite rather than altering the repo's pinned SHAs.
git config --global url."https://github.com/LineageOS/android_packages_modules_adb.git".insteadOf \
  "https://android.googlesource.com/platform/packages/modules/adb.git"
# Every mirror/commit pair was verified using the GitHub commit API.
# Do not rewrite other repositories without confirming their pinned SHA.
# c92ce4cb9a1b6d20a1bc11b7e5864af9f78615bb
git config --global url."https://github.com/LineageOS/android_external_avb.git".insteadOf \
  "https://android.googlesource.com/platform/external/avb"
# b815dded1eafbf06191a6ae306956bb6ed6fb415
git config --global url."https://github.com/LineageOS/android_build.git".insteadOf \
  "https://android.googlesource.com/platform/build.git"
# e9d1fa3705d7fbd0ac1c942bc4c276161bfbfed1
git config --global url."https://github.com/LineageOS/android_system_core.git".insteadOf \
  "https://android.googlesource.com/platform/system/core.git"
# 3f52a5ab49ba53bc463de658db1d112e001c0280
git config --global url."https://github.com/LineageOS/android_system_extras.git".insteadOf \
  "https://android.googlesource.com/platform/system/extras.git"
# 10c6b5f81069d6d78c7ef3833458f4d51d02e2a6
git config --global url."https://github.com/LineageOS/android_system_libufdt.git".insteadOf \
  "https://android.googlesource.com/platform/system/libufdt.git"
# 94db64a81930e4cc8bacca4010bf935f664c97e1
git config --global url."https://github.com/LineageOS/android_system_libziparchive.git".insteadOf \
  "https://android.googlesource.com/platform/system/libziparchive"
# 58dac317ea08b8f275ebd01ce864acab2de30b93
git config --global url."https://github.com/LineageOS/android_system_logging.git".insteadOf \
  "https://android.googlesource.com/platform/system/logging.git"
# 954bc3ead5e679005fddf3484d247f2557b3c2c9
git config --global url."https://github.com/LineageOS/android_system_tools_mkbootimg.git".insteadOf \
  "https://android.googlesource.com/platform/system/tools/mkbootimg"
# 40e035a9e5d721b3b7c15c46259d782ffe7d9e96
git config --global url."https://github.com/google/boringssl.git".insteadOf \
  "https://boringssl.googlesource.com/boringssl.git"
git config --global http.version HTTP/1.1
git config --global http.lowSpeedLimit 1000
git config --global http.lowSpeedTime 180
for attempt in 1 2 3 4; do
  if git -c submodule.fetchJobs=4 submodule update --init --recursive --jobs 4; then
    break
  fi
  if (( attempt == 4 )); then
    echo "Submodule checkout failed even with alternate ADB mirror" >&2
    exit 1
  fi
  echo "Retrying submodule checkout, attempt $((attempt + 1))"
  sleep $((attempt * 10))
done
test "$(git -C external/android-tools/vendor/adb rev-parse HEAD)" = \
  "78f769e0904c21771cccf6e4e7b239b21800e189"
test "$(git -C external/android-tools/vendor/avb rev-parse HEAD)" = "c92ce4cb9a1b6d20a1bc11b7e5864af9f78615bb"
test "$(git -C external/android-tools/vendor/build rev-parse HEAD)" = "b815dded1eafbf06191a6ae306956bb6ed6fb415"
test "$(git -C external/android-tools/vendor/core rev-parse HEAD)" = "e9d1fa3705d7fbd0ac1c942bc4c276161bfbfed1"
test "$(git -C external/android-tools/vendor/extras rev-parse HEAD)" = "3f52a5ab49ba53bc463de658db1d112e001c0280"
test "$(git -C external/android-tools/vendor/libufdt rev-parse HEAD)" = "10c6b5f81069d6d78c7ef3833458f4d51d02e2a6"
test "$(git -C external/android-tools/vendor/libziparchive rev-parse HEAD)" = "94db64a81930e4cc8bacca4010bf935f664c97e1"
test "$(git -C external/android-tools/vendor/logging rev-parse HEAD)" = "58dac317ea08b8f275ebd01ce864acab2de30b93"
test "$(git -C external/android-tools/vendor/mkbootimg rev-parse HEAD)" = "954bc3ead5e679005fddf3484d247f2557b3c2c9"
test "$(git -C external/android-tools/vendor/boringssl rev-parse HEAD)" = "40e035a9e5d721b3b7c15c46259d782ffe7d9e96"
