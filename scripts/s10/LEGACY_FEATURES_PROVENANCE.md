# S10e fingerprint and S10 Wi-Fi framework migration

The failed full build at a4a08d72c1c6d046a9bbe6fcc2246a3e041a68d9
completed all four kernels and fresh firmware extraction. S10e then rejected
the old side-fingerprint framework patch; the other models reached the missing
true-to-false Wi-Fi concurrency migration. The generic side-fingerprint app
patches also contain obsolete R8 callbacks and DEX roots, so repairing only the
first InputRune hunk would leave known incompatibilities behind.

## Reviewed inputs

[Review workflow](https://github.com/WatchFact/NetherROM/actions/runs/39584016425)
extracts the pinned S926BXXSHDZI1/S926BOXMHDZI1/S926BXXSHDZI1 firmware and decodes
its framework, Settings, SystemUI and Wi-Fi archives with the pinned toolchain.
The [review archive](https://github.com/WatchFact/NetherROM/releases/tag/s10-framework-review-5b102bff2588)
is diagnostic data, not a ROM. SHA-256:
`52cfa3873592c9925608a3db9fd44fad469862fa4815dbcc524244a981ac1b3c`.
Individual input archives, patch files, decoded classes and shared methods are
pinned in `legacy-features-v4.0.1.json`.

Stock Wi-Fi comparison uses
[the S10+ firmware JAR](https://github.com/leddaz-dump-stash/samsung_beyond2_dump/blob/ed4c525d91f1c7f708296f345732a21935f28da8/system/system/framework/semwifi-service.jar),
Git blob `2209f46c644a371e6389aab3fc452c11cf5936f9`, SHA-256
`94c2876a2f377fdabda64c04190a091251541edb61690ec7e0693ce79bc7cef7`.
Its SemWifiApChipInfo parses DualBandConcurrency and DualInterface, then derives
sharing/lite support at runtime. The donor retains these branches but overrides
the result with an unconditional true write. Removing that write restores chip
detection without falsely asserting unsupported hardware. The existing target
concurrency flag remains false; its diagnostic SPF string is updated. TWT
queries return zero/false, respecting the existing S10 target policy, while the
native optimizer/low-latency detection remains intact.

## S10e implementation

* Sensor position is 4 (power button), with Samsung capacitive sensor type 1.
  The native HIDL-to-AOSP mapping already maps position 4 to TYPE_POWER_BUTTON;
  it is preserved, rather than misclassifying the sensor as ultrasonic UDFPS.
* Side-touch input flags are enabled. Display-fingerprint, TSP, HBM and early
  wake flags are disabled with fresh locals, without clobbering source registers.
* The existing concrete provider lifecycle ABI and original boot callbacks are
  preserved. The extension creates the gesture manager once, registers HAL event
  and settings/user observers, forwards HAL restarts and dispatches gesture events.
  Feature query 1 advertises gestures; unconfigured swipe enrollment and default
  wake-off overrides remain unavailable. Gesture code is adapted to SemUtils.
* Settings retains its native power-button and gesture controllers. Its shared
  AOD icon gate is disabled; setup hides display-icon/effect rows. The existing
  b4qxxx BiometricSetting import and JDM-HAL patch are preserved.
* SystemUI retains its native AuthController sensor-property classification,
  gated keyguard listening, strong-auth checks and R8 callbacks. Its folded
  display/optical flags and geometry become false/zero, side support becomes true
  and background authentication is enabled. No obsolete callback deletion or
  generated lambda transplant is applied to this source.

## Validation and limits

Before/after guards check exact firmware archive digests, patch digests and
unique decoded classes through the actual sibling APKTOOL_DIR/WORK_DIR layout.
The SystemUI input uses the physical system/system/system_ext location; its
logical system_ext decode cache remains separate. A regression executes the
actual apktool.sh partition mapping. SystemUI/Wi-Fi bytes are also checked in
the final ext4 image, and migration provenance is included and checked in ZIPs.
Output audits require rebuilt archives and matching decoded implementations,
plus gesture wiring, power-button sensor results and runtime Wi-Fi detection.
Shared PowerManagerUtil/LsRune initializers legitimately undergo later HFR
adaptation: other methods remain pinned and fresh-local fingerprint assignments
are independently checked, including rejection of reassigned locals.

The actual production helpers and source-specific guards were exercised against
an exact-source fixture. The complete WLAN block is exercised with pipefail.
Method selection now reads declarations once: the prior unused grep pipe could
SIGPIPE on large classes, and its diagnostic regex mishandled array signatures.
A regression checks large classes, array returns and missing declarations. All five modified archives assembled with the pinned
Apktool; services.jar also assembled with the reviewed face-HIDL and virtual
vibration migrations applied together. New gesture member references resolve
against the source framework. All four hardware preflights and the regression
suite remain required. Full clean ROM, image, capacity, signature and ZIP checks
run in Actions; local DEX assembly is not a successful flashable build.

These checks establish reviewed source/build compatibility. Boot, enrollment,
unlock, gestures, Wi-Fi sharing and other hardware operation still require
physical device testing.
