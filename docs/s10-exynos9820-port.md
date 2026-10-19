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
- The Actions workflow fetches the Exynos9820 compatibility modules pinned to ArtisanROM Quant v3.1.0's Android 16 Exynos9820 revision. A kernel build from the pinned M62-backport is required; packaging rejects a missing boot/dtbo.
- The S10 needs a compatible custom recovery, partition layout, firmware and kernel with **ext4** support. Kernel compilation and ZIP generation do **not** prove that the system boots.

## GitHub Actions
Workflow: `.github/workflows/s10-port.yml`. Push to `port/exynos9820-s10` runs validation and a first S10+ build. Manual dispatch allows selecting each of the four devices. If compilation and ZIP checks succeed, a GitHub prerelease is created with split assets and checksums.

## Before any hardware flash / bootable claim
1. Validate the target's actual partition/PIT layout and use a known S10-specific repartitioner if necessary, after making full backups. Never flash S20 repartitioners/firmware.
2. Validate boot and dtbo images from the compiled target kernel, SELinux policy compatibility, One UI 8.5 vs One UI 8.0 Android 16 VNDK/vendor transitions, and the vendor VINTF contract. Ensure the kernel actually includes EROFS.
3. Test with physical target hardware: download mode, recovery, install preflight, first boot, ADB and logcat; then test display, fingerprint, touch, radio/IMS, Wi-Fi, camera, audio, encryption, suspend and reboot.
4. Remove the *untested* label only after successful on-device logs are attached. Any GHA release is experimental and not a declaration of bootability.

### References
- NetherROM S20+ `target/y2s` and Aether `sixteen-qpr2` donor.
- ExtremeXT/ExtremeROM `fifteen` pinned commit `2056320784b7d1d88f9e7025f86f7bbd39945d6b` for Exynos9820 device data and port modules (GPL-3.0-or-later).
- ExtremeXT/M62-backport pinned commit `e6e5dc977097c3eb3f924e4ab215ca29037c858d` for the Exynos9820 kernel (review kernel licences independently).
