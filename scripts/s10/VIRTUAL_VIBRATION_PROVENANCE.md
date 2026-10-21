# S10 virtual vibration sound migration

The pinned S926B Android 16 framework supports playing simulated vibration
sounds through a SoundPool. All four Exynos9820 target configurations declare
`TARGET_AUDIO_SUPPORT_VIRTUAL_VIBRATION_SOUND=false`. This concerns the virtual
sound feature; normal motor vibration, notification/call haptics, intensity
settings, Bluetooth audio, and fold-state registration must remain intact.

The first complete build after the native camera encoder correction reached
`unica/patches/product_feature` and failed in the generic services.jar virtual
vibration patch. That patch targets an older compiler output and service model.
The pinned firmware initializes its virtual helper inline in
`VibratorManagerService.bootCompleteReady()` and has different nested classes.
Applying the old deletions would also remove callbacks referenced by this
framework.

The Exynos9820 migration uses the exact framework and Settings inputs extracted
in [the compatibility review job](https://github.com/WatchFact/NetherROM/actions/runs/39561544252).
`virtual-vibration-v4.0.1.json` records firmware/tool provenance, original archive
digests, reviewed class digests before and after the patches, and patch digests.
The framework's pre-migration Rune fingerprint includes the preceding ACH
ringtone correction, as it does in a real build. No firmware cache is imported
into the clean ROM jobs.

The backend change removes only the virtual helper/SoundPool initialization
from `bootCompleteReady()`. Its existing `registerFoldStateListener()` call
remains. The rest of `VibratorManagerService` is byte-for-byte unchanged, including
its native vibration, cancellation, scheduling, and motor control paths. The
source's ten later helper accesses immediately branch around a null helper;
with no allocation or assignment, the virtual backend stays inactive. Existing
callbacks and classes are retained so their references remain valid.

The framework advertises the feature as unsupported. Settings hides the
unavailable controller, disables its slice/control entry points, and rejects
writes with `NOT_SUPPORT_DEVICE`. The pinned provider already initializes the
virtual-sound setting to zero; its reviewed default code is kept unchanged.
These source-specific edits preserve unrelated settings and physical haptic
preferences.

Before and after applying the migration, `virtual_vibration.py` checks source
archive/class/patch digests. Its backend audit rejects a helper allocation or
assignment, an unguarded helper read, a changed entry-point count, or any change
to motor code outside the reviewed startup method. Regression cases exercise
those rejection paths. The output audit repeats the reviewed class and backend
checks, rejects original archives where code was changed, requires valid
rebuilt ZIP archives and their DEX classes, and checks migration provenance. Image audits compare these exact rebuilt JARs and
APKs against the files inside the actual ext4 system image. The provenance also
ships inside the signed flashable package.

Validation used strict patch application and before/after guards for all four
models against the exact extracted inputs, a complete DEX assembly of both JARs
and both Settings APKs with the pinned Apktool, the rebuilt archive audits,
face-HIDL integration, and execution of the actual shell migration block.
Negative checks reject an unrebuilt original framework and a duplicate Settings
controller. All 12 port regressions, four 554-file/90-import hardware preflights,
and shell syntax checks pass. These local assemblies retain binary resources;
the clean Actions jobs still perform normal resource rebuilding and signing.

Source inspection and successful assembly establish the scope and consistency
of this migration. Boot, motor response, notification/call haptics, and audio
behavior still require physical device testing.
