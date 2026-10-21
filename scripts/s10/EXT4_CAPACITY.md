# Read-only physical ext4 capacity

Run 39662901109 passed all assembled hardware, portrait, thermal, kernel and ODM
checks. The system image's minimum allocation was about 8248 MiB, exceeding the
fixed 7000 MiB system partition. Two runners also received shutdown signals;
their measured payloads had the same capacity problem. An unchanged rerun cannot
solve it. The physical partition sizes and installer guards are retained.

The S10 packager opts into AOSP e2fsdroid's duplicate-block sharing through
`mkuserimg_mke2fs --share_dup_blocks`. It shares identical 4096-byte data blocks,
retaining distinct inodes, file bytes, paths, UID/GID, modes and SELinux labels.
It changes neither APK/APEX signatures nor the hardware payload. Both the image
sizing pass and final pass use the same allocator. The generic image builder
keeps the option disabled by default and restricts it to ext4 OS images.

The exact pinned kernel's `ext4_feature_set_ok(sb, readonly)` checks unsupported
incompatible features, then accepts a read-only mount before checking unknown
read-only-compatible features. Shared blocks are a read-only-compatible ext4
feature. The unchanged pinned ramdisk and vendor fstab are audited to require
read-only ext4 for all four physical OS partitions. These images must remain
read-only; a writable remount would require unsharing their blocks first.

Primary sources:

- [Pinned Exynos9820 ext4 mount checks](https://github.com/Android-Artisan/android_kernel_samsung_exynos9820/blob/9a0a792d227c8ae6cddac0c9d68a8bb9782c44cb/fs/ext4/super.c)
- [AOSP mkuserimg_mke2fs duplicate-block option](https://android.googlesource.com/platform/system/extras/+/main/ext4_utils/mkuserimg_mke2fs.py)
- [AOSP e2fsdroid allocator](https://android.googlesource.com/platform/external/e2fsprogs/+/refs/heads/main/contrib/android/e2fsdroid.c)

The former per-file OTA block map can overlap after sharing. S10 full OTAs now
encode the actual sparse image ranges without an incremental file map. This is
a full update, not an incremental patch. The pinned encoder is unchanged.
Every resulting image passes read-only e2fsck and a SHA256 comparison of every
regular file with its assembled source; the existing representative hardware,
portrait and ODM metadata checks remain. After encoding, every filesystem care
block must be written by the transfer list, and the reconstructed full update
must match the audited image byte for byte before compression and signing.
Memory usage during this comparison is bounded, and the temporary raw update is
removed before building the next partition.

`shared_ext4_smoke.py` uses the actual production builder and pinned tools:
three separate 8 MiB files must fail to fit a 12 MiB ext4 image without sharing,
then fit with sharing. Independent inode ownership/mode/SELinux metadata and
all payload bytes must survive the real full OTA encoder and reconstruction.
Corrupted files, corrupted OTA payloads and missing filesystem writes must fail.
The test runs before kernel compilation in each clean device build.

Block sharing is a lossless capacity optimization; the final real images must
still fit their existing physical budgets. This document does not claim that
real firmware fits until those build checks pass, or establish physical boot
and hardware functionality without device testing.
