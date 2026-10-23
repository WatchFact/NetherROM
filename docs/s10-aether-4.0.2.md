# NetherROM / ArtisanROM Aether 4.0.2 — Galaxy S10 clean port

Base: latest available sixteen-qpr2 source in WatchFact/NetherROM, commit
`39312bda2bd001f2e60efbb4e381c421c44da630`, reporting Aether 4.0.2.
This is a **new port branch**, independently created from the source branch,
not a branch off the former experiments. ArtisanROM 4.0.1 is the latest
published stable release as of 2026-10-21. The 4.0.2 source is pre-release.

**Only supported device:** Galaxy S10+ Exynos 9820, **SM-G975F / SM-G975F/DS**, codename **beyond2lte**. All other S10-family targets, including SM-G975N, and all Snapdragon/S20 build targets are removed from this branch. They cannot be selected or packaged.

## Hardware and isolation

The current 4.0.2 userland is retained. For S10 boot support the complete
Exynos9820 hardware, vendor/radio/graphics/audio/camera modules and device
trees were reintroduced from the earlier audited 3.1.0 S10 firmware work,
preserving tracked binary Git identities. The earlier 4.0.1 migration is
a source of audited hardware inputs, **not** the new base branch. The firmware
and kernel are separately pinned, and CI rebuilds from clean inputs.

S10 uses **physical ext4** system (7000 MiB), vendor (1500 MiB), product
(1500 MiB) and odm (4 MiB) partitions, not dynamic/super partitions.
The build uses model-specific Exynos9820 boot.img, dtb.img and dtbo.img.
It must not use the S20/Exynos990 partition map or boot images. Installer
checks capacities before writing and does not repartition or format userdata.
A separately verified legacy ArtisanROM S10 PIT and compatible recovery are
prerequisites. Never flash a PIT for another phone variant.

## Pipeline

`.github/workflows/s10-aether.yml` performs read-only hardware preflight,
regression tests and exactly one clean S10+ (beyond2lte) build. It compiles the pinned Exynos9820
kernel and generates signed physical-partition installer ZIPs with image,
metadata, full ext4 filesystem checks (including product), OTA reconstruction,
partition-size validation and duplicate-device safeguards before any writes.
The immutable installer/preflight scripts are checked against the package's
sizes.json before signing. A source prerelease is tagged only after independent
hardware/source regression preflight; ROM assets are published only if all
on-run build/package checks and split-volume reconstruction hashes pass.

The updater requires both the beyond2lte device codename and the approved SM-G975F model property; it aborts on wrong or unidentifiable models. The build checks the SM-G975F target firmware and refuses other device IDs.

**Unverified:** boot, radio/IMS, camera, fingerprint, Wi-Fi, Bluetooth,
storage, recovery compatibility, charging and stability require on-device
logs. Static validation alone cannot establish that this ROM will boot.

Provenance: https://github.com/ArtisanROM/ArtisanROM (Aether);
ArtisanROM 3.1.0 S10 snapshot `4d30365b4452a651cc87af8e91733ec1c862f716`;
audit baseline `WatchFact/NetherROM:port/s10-v4.0.1`.

## Release safety

The published ROM uses the AOSP test signing key (not a private production key).
Do not mistake a GitHub Actions success or intact ZIP for a bootable ROM.
The full hardware/OS compatibility matrix—including enforcing SELinux, IMS,
camera, Wi-Fi, Bluetooth, GPU, userdata and recovery—remains **unverified on
physical hardware** until S10+ boot/recovery logs and hands-on tests pass.
For installing, preserve a complete verified stock firmware and personal-data
backup; never repartition or flash another model's PIT based on this build.
