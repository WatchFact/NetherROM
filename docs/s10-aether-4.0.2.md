# NetherROM / ArtisanROM Aether 4.0.2 — Galaxy S10 clean port

Base: latest available sixteen-qpr2 source in WatchFact/NetherROM, commit
`39312bda2bd001f2e60efbb4e381c421c44da630`, reporting Aether 4.0.2.
This is a **new port branch**, independently created from the source branch,
not a branch off the former experiments. ArtisanROM 4.0.1 is the latest
published stable release as of 2026-10-21. The 4.0.2 source is pre-release.

Devices: Exynos **beyond0lte** (SM-G970F/N), **beyond1lte** (SM-G973F/N),
**beyond2lte** (SM-G975F/N), **beyondx** (SM-G977B/N). Snapdragon excluded.

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
regression tests and four clean S10 builds. It compiles the pinned Exynos9820
kernel and generates signed physical-partition installer ZIPs with image,
metadata, OTA reconstruction and partition-size validation. A source
prerelease is tagged after preflight; ROM assets are published only if all
on-run build/package checks pass.

**Unverified:** boot, radio/IMS, camera, fingerprint, Wi-Fi, Bluetooth,
storage, recovery compatibility, charging and stability require on-device
logs. Static validation alone cannot establish that this ROM will boot.

Provenance: https://github.com/ArtisanROM/ArtisanROM (Aether);
ArtisanROM 3.1.0 S10 snapshot `4d30365b4452a651cc87af8e91733ec1c862f716`;
audit baseline `WatchFact/NetherROM:port/s10-v4.0.1`.
