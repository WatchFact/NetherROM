# Physical S10 ODM

The stock S10 SDK31 firmware has its ODM files under `vendor/odm`, without a
separate extracted ODM image. The pinned Exynos9820 kernel ramdisk instead
first-stage mounts `/dev/block/platform/13d60000.ufs/by-name/odm` as `/odm`.
An absent top-level work directory is therefore a real packaging/boot-layout
mismatch. Skipping the partition audit or making an empty directory is not a fix.

After fresh target firmware extraction, `create_work_dir.sh` materializes the
entire native `vendor/odm` directory into the physical `odm` output. It retains
both trees, including zero-byte files. The extracted UID, GID, mode, capability
and SELinux metadata are rebased to the new mount path, including the image-root
fs_config entry required by e2fsdroid. There are no default metadata fallbacks.
The reviewed SDK31 ODM contains no capability-bearing files; an unexpected
capability, symlink, wrong model/device/API or missing metadata stops the build.

This happens before ROM modules, allowing the existing property helpers to edit
`/odm/etc/build.prop` (for example, the USB configuration). All native hardware
identity and ABI properties are immutable. Every other file, directory, metadata
entry and the entire embedded source remain identical to their fresh stock
snapshot. Packaging freezes the final property-file digest; subsequent changes
cannot be accepted by finalizing again. `odm-provenance.json` records the full
source and output inventories in diagnostics and in the signed ZIP.

The ODM image is explicitly 4194304 bytes, matching the configured physical
partition. All images retain capacity checks before OTA conversion and before
installer writes. The actual vendor and ODM ext4 images are audited for every
ODM file's bytes, UID/GID, mode and SELinux label. The ZIP validator checks the
provenance device, inventory, digests and stock metadata continuity.

`odm_image_smoke.py` runs in every device's clean Actions job using the pinned
real mke2fs/e2fsdroid/sparse-image/OTA tools. It executes the production image
builder, verifies the 4 MiB size, audits bytes and metadata, reconstructs the
encoded full block OTA and audits that filesystem again. Deliberately corrupted
ownership and file bytes must be rejected by the production image audit.
`test_port.py` additionally exercises the actual work-directory stage for all
four variants and rejects missing metadata, changed hardware identity, wrong
variants, pre-existing unreviewed output and changes after finalization.

These are build and image checks. Physical boot, partition geometry and hardware
operation still require testing on a compatible S10 with the expected layout.
