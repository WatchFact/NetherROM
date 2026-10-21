# Original S10 camera compatibility

The S10 camera module includes the original ArtisanROM 3.1.0 SamsungCamera
APK, Git blob `c03527307a4d57cc0674cab800f47c07c5ec7f63`. Its classes are
different from the modern camera targeted by 4.0.1's generic SceneDetection
and SecondPicture patches. Moving those patches to another DEX directory
does not make their hunks compatible.

The original app already contains `sendTextDetectionInfoCallback`, native
`onSceneDetectionEvent` callbacks, the scene/text detection vendor keys,
`isSecondPictureConfigSupported`, and its original picture/video request
handlers. These are the legacy APIs the S10 hardware port selected.

`camera-native-v3.1.0.json` pins the APK SHA256 and 13 decoded implementation
files covering both paths. The files were decoded with the same pinned
Apktool archive and `--no-debug-info` used by Actions. Before retaining
these implementations, the build checks the original and assembled donor
APK identities, uniquely resolves every class across DEX directories,
checks its descriptor and verifies every implementation digest. Unknown,
changed, missing or duplicate implementations fail the build. The modern
CameraMetadataNative framework backport is still applied.

Compatibility provenance is recorded in the work directory, diagnostics and
flashable ZIP. Package validation requires that record and verifies the
legacy API names and class descriptors in the rebuilt camera DEX files.
The APK is also compared inside the actual ext4 image. These are input and
build checks; boot and camera operation still require physical testing.

# Pinned boot image and storage

The pinned S10 boot ramdisk already supports physical ext4/erofs OS mounts
and unencrypted F2FS userdata. The generic filesystem module needlessly
repacked it, leaving the original `kernel.json` checksums stale. The S10
path now validates the actual boot header, gzip/newc ramdisk and first-stage
fstab, plus the vendor fstab, before retaining the image unchanged. It
requires all four physical ext4 mounts and rejects logical partitions,
verification/encryption flags and an incompatible userdata filesystem.

Boot, DTB and DTBO digests are checked at import, before filesystem handling,
again before packaging, and against the images in the final signed ZIP.
