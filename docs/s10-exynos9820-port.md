# NetherROM Galaxy S10 family (Exynos9820)

**Status: experimental port; build and physical boot validation required. Do not flash to a daily driver.**

This ports the existing NetherROM One UI/Aether source build (the same donor used for the Galaxy S20+) to S10e, S10, S10+ and S10 5G Exynos targets. It does not turn an Exynos990 S20 kernel or vendor into a functioning S10 kernel/vendor.

| Device | Codename | Compatible model family |
|---|---|---|
| Galaxy S10e | beyond0lte | G970F / G970N |
| Galaxy S10 | beyond1lte | G973F / G973N |
| Galaxy S10+ | beyond2lte | G975F / G975N |
| Galaxy S10 5G | beyondx | G977B / G977N |

**Not supported:** Snapdragon S10 models, any Note10, or unverified model suffixes. No compatibility is implied for devices lacking the proper recovery / firmware.

## Critical changes vs S20+
- Physical /system, /vendor, /product and /odm partitions: *no dynamic super partition*. The ZIP generator now omits super metadata and writes directly to physical partition paths on legacy targets.
- A recovery-side preflight checks **all actual partition capacities before any OS image is written**. A missing block device or insufficient capacity aborts the installation. The port never silently repartitions a device.
- Device-specific Exynos9820 features, model assertions, 60 Hz refresh, cutouts, side/UDFPS, and Samsung firmware selection are not copied from the S20+.
- The Actions workflow fetches the Exynos9820 compatibility modules pinned to ArtisanROM Quant v3.1.0's Android 16 Exynos9820 revision. A kernel build from the pinned Android-Artisan Exynos9820 tree is required; packaging rejects a missing boot/dtbo.
- The S10 needs a compatible custom recovery, partition layout, firmware and kernel with **ext4** support. Kernel compilation and ZIP generation do **not** prove that the system boots.

## GitHub Actions
Workflow: `.github/workflows/s10-port.yml`. Push to `port/exynos9820-s10` runs validation and a first S10+ build. Manual dispatch allows selecting each of the four devices. If compilation and ZIP checks succeed, a GitHub prerelease is created with split assets and checksums.

## Before any hardware flash / bootable claim
1. Validate the target's actual partition/PIT layout and use a known S10-specific repartitioner if necessary, after making full backups. Never flash S20 repartitioners/firmware.
2. Validate boot and dtbo images from the compiled target kernel, SELinux policy compatibility, One UI 8.5 vs One UI 8.0 Android 16 VNDK/vendor transitions, and the vendor VINTF contract. Ensure the kernel actually includes the intended ext4 support.
3. Test with physical target hardware: download mode, recovery, install preflight, first boot, ADB and logcat; then test display, fingerprint, touch, radio/IMS, Wi-Fi, camera, audio, encryption, suspend and reboot.
4. Remove the *untested* label only after successful on-device logs are attached. Any GHA release is experimental and not a declaration of bootability.

### References
- NetherROM S20+ `target/y2s` and Aether `sixteen-qpr2` donor.
- ExtremeXT/ExtremeROM `fifteen` pinned commit `2056320784b7d1d88f9e7025f86f7bbd39945d6b` for Exynos9820 device data and port modules (GPL-3.0-or-later).
- Android-Artisan `android_kernel_samsung_exynos9820` pinned commit `9a0a792d227c8ae6cddac0c9d68a8bb9782c44cb` for the Exynos9820 kernel (review licences independently).

## Legacy non-dynamic installer
The original Galaxy S10 has **physical** `system`, `vendor`, `product` and `odm` PIT partitions. The S10-specific `scripts/port_s10/build_legacy_zip.sh` creates ext4 images and physical block OTAs: `*.transfer.list` with `*.new.dat.br`. Recovery writes directly to `/dev/block/by-name/<partition>`, as in original ArtisanROM v3.1.0, and performs no dynamic-super updates, `lpmake`, `map_partition` or automatic repartitioning. The recovery preflight checks **expanded sparse image sizes** against actual block device capacities before writing. This is a safety check, not proof of successful boot.

### Boot image review
The pinned S10 kernel's original updater (`build/updater-script`) writes **boot.img, dtb.img and dtbo.img**. NetherROM now requires all three, validates each physical partition's capacity and flashes them through their original by-name devices. The kernel build explicitly disables KernelSU by default (`-k n`). This does not substitute for physical boot verification.

## ExtremeROM source audit (2026-10-19)
Compared against [ExtremeXT/ExtremeROM @2056320784b](https://github.com/ExtremeXT/ExtremeROM/tree/2056320784b7d1d88f9e7025f86f7bbd39945d6b). Its beyond-series devices use **physical** partitions (`TARGET_SUPER_PARTITION_SIZE=0`) and a target-specific kernel; its earlier Android 15 Exynos9820 profile built **EROFS**, whereas ArtisanROM v3.1.0's Android 16 Exynos9820 profile uses **ext4**. The current NetherROM port follows the latter ext4 legacy path and must not conflate legacy PIT geometry with filesystem type.

ExtremeROM's camera patch imports `a26xxx` Polarr SDK components. NetherROM lacks that donor; the three ELF libraries are byte-identical to existing `prebuilts/samsung/a73xqxx` libraries (verified by Git blob hashes). The `compat.sh` importer now checks these exact hashes, rewrites the pinned camera module to use the local donor, and removes two unnecessary names from the public-libraries allowlist. Stop building if the hashes differ. The Actions job also installs `webp` (for `cwebp`) and `ffmpeg`; these were missing and caused the first complete checkout/build-tool run to fail before Samsung firmware download. No hardware-boot claim is implied.

## Verified ArtisanROM repartition-script geometry
We downloaded and statically inspected the original [ArtisanROM v3.1.0 Exynos9820 repartitioner](https://pixeldrain.com/u/zFuXCEpb); ZIP SHA-256 `802cc8c10acbcd3c7f2b1b73f14fd8f7b26ca4ef9cb6dc12f76f958c030d4e45`. **There is no binary `.pit` in the archive**. The actual geometry is coded in `extreme/repartition.sh`, which uses `sgdisk` and `parted` on `/dev/block/sda` to resize the existing system partition, delete/recreate a set of later GPT partitions and give userdata the remaining free space. It preserves the original leading partition numbers/offsets; a portable binary PIT **cannot safely be synthesized** from its constants.

| Physical partition | Target size (MiB) | Requirement |
|---|---:|---|
| system | 7000 | required |
| vendor | 1500 | required |
| product | 1500 | required |
| odm | 4 | required |
| prism | 600 | required |
| optics | 30 | required |
| cache | 600 | required |
| omr | 50 | required |
| cp_debug | 5 | required |
| cp2_debug | 5 | only when present originally |
| spu | 50 | only when present originally |
| userdata | remaining space | required |

These values are recorded in `scripts/port_s10/artisanrom_partition_layout.tsv` and used to reject oversized built ext4 images and physical OS partitions that are significantly smaller than the expected ArtisanROM layout. The recovery script checks the actual capacities before any flash and **never repartitions automatically**. The independent read-only inspection workflow `.github/workflows/artisanrom-pit.yml` publishes extracted scripts as a GitHub Actions artifact. The repartitioner itself is **destructive and data-wiping**: do not run it casually or on an unbacked-up device.
