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

`camera-native-v3.1.0.json` pins the APK SHA256, 13 decoded implementation
files covering those APIs, and six encoder/recording classes. The files were decoded with the same pinned
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

## Native OMX recording and encoding

The original S10 camera has no Samsung SUM `EncoderFilter`. Its two explicit
video-format builders already select `COLOR_FormatSurface` (`0x7f000789`),
whereas the modern 4.0.1 camera backport replaces `0x7f420888` in that newer
SUM class. Relocating or ignoring the missing class would not establish the
donor's actual codec behavior.

The reviewed `d3/j.b()` format builder feeds the `f3/a` MediaCodec configuration
and input-surface lifecycle. `EncodeVideo.prepareVideoCodec()` independently
sets the same surface format, configures MediaCodec and creates its input
surface. Regular camera recording retains `SessionContainer`'s MediaRecorder
and `RecordingSession.prepareMediaRecorder()`'s video encoder, input surface
and preparation calls. These six complete classes are digest-locked, and the
declared operations are checked within their actual methods. A modern SUM
encoder or `0x7f420888` appearing elsewhere in the decoded donor is rejected.

The S10 OMX module verifies these native implementations instead of applying
the modern camera-specific SUM patch. MotionPhoto, GlobalPostProcMgr when
present, and vexfwk_service retain their source-app OMX migrations. The final
camera audit rechecks the native encoder implementations and their rebuilt
DEX class presence. A complete code rebuild with the pinned Apktool, checks
for all four S10 targets, and negative tests for incompatible formats and
unrelated methods passed. The actual OMX module was exercised with the pinned
camera, including its calls to the modern-app patches. No camera APK or native
hardware payload was replaced by this correction.

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
