# S10 portrait model ordering

Run `39600243558` at `acb2bd9e790524fc90fa074f343d4e497ec92b73`
completed all four kernel, extraction, ROM and thermal policy stages. The final
camera audit correctly rejected a missing `nexus_bokeh_feature.json` on all four
targets. The logs show the platform module creating it, followed by the generic
4.0.1 camera module deleting `portrait_data` and importing the stock target tree.
The native library had already been redirected to the deleted file.

Both the original 3.1.0 hardware module at
`4d30365b4452a651cc87af8e91733ec1c862f716` and the earlier reviewed port at
`dbde7278f5931a4ff6d14d43c841037def50a348` preserve the source single-bokeh
feature under the nexus name, adapt the camera-facing enum and redirect the
PortraitSolution library. The generic 3.1.0 camera module did not replace this
directory. This ordering difference is the cause, not a missing firmware download.

Run `39634595076` then exposed why retaining the modern donor's entire model
set is insufficient. All four S10 vendors lack the source JSON's
`SRIB_ClatNetLite_FP16_V005_ex2400_enn2318b.nnc`. This is an Exynos2400-compiled
NPU model, not a portable S10 firmware dependency. Copying that foreign vendor
weight would not establish compatibility with Exynos9820.

The platform module now imports the complete **stock S10** portrait directory
before applying the earlier enum/alias/library adaptation. It leaves the S10
vendor models and HALs intact. The nexus JSON is an exact copy of the fresh
target JSON; the camera-facing single-bokeh JSON has only the established
`MODEL_TYPE_INSTANCE_CAPTURE` to `MODEL_TYPE_OBJ_INSTANCE_CAPTURE` substitution.
Other platforms keep the generic target import.

The provenance guard compares all portrait files against fresh target firmware
and the exact bounded library patch against the pinned modern source firmware.
It records both firmware identities and SHA256 digests. It requires the native
`exynos9820_common` configuration, GPU/SNF capture, native EDEN preview and
existing model weights, rejects Exynos2400/.nnc dependencies, and checks the
modern library's native compute/model enum parser strings. The firmware
preflight applies these input checks immediately after fresh extraction.
Later camera stages and final output must match the recorded model set.
Actual ext4 extraction compares every recorded portrait file and library; the
ZIP carries the provenance and checks its device and both firmware identities.

The exact pinned native input was inspected in read-only review run
`39642929451`, release `s10-framework-review-4b597d390680`. Its archive SHA256
is `a047099d5ac092863687ad29ffdb6bb618f77b8531c09f79b393882c7bb7eec4`.
The 1,401,376-byte source PortraitSolution library has SHA256
`f639370b623a46d41617319d46c92f56fceedf6759dedcf718daa080fbabcaa1`;
after the existing length-preserving path patch it has SHA256
`0d28d6f33111be73b15729ae725c842e1770ba8e81df83273eaa75bc45f7af86`.
Its native compute/model parser strings include `COMPUTE_GPU`, `COMPUTE_NPU`,
`MODEL_TYPE_INSTANCE_CAPTURE`, `MODEL_TYPE_OBJ_INSTANCE_CAPTURE` and
`MODEL_TYPE_SEG_LIVE`. The exact source JSON confirms Exynos2400-specific NPU
weights for capture, depth, matting and preview. Parser strings and a matching
file contract do not prove that native inference or camera hardware works.

The regression JSON content comes from the immutable S10 dump
`leddaz-dump-stash/samsung_beyond2_dump` at
`ed4c525d91f1c7f708296f345732a21935f28da8`, path
`system/system/cameradata/portrait_data/single_bokeh_feature.json` (Git blob
`27561657f184a05b10264e7159140a2894c72d85`, raw SHA256
`ebf002ccfdac12989dbc178a6bda147668eed09ec36e94a5f38f72e0e5329d0e`).
The checked-in test fixture normalizes CRLF and trailing whitespace, with SHA256
`b6b4f0300845d090c6c5d45f56c22d71b19901bf4192096da7920af1b6fda289`.
The two stock weights are `SRIB_HumanInsSeg_FP16_V210.snf` and
`SRIB_HumanSegLite_INT8_V001.tflite`. Builds use their freshly extracted target
files, never the small synthetic weight bytes used by the stage-order test.
An additional local integration check executed the actual platform portrait
block with the exact pinned source binary and the real dump JSON and both
weights above. All three immutable Git blob IDs were verified; the bounded
binary patch, native input checks and five-file output digest record passed.

The regression executes the actual platform portrait block and generic camera
import block in order for all four S10 targets. It rejects missing or changed
models, changed library bytes, unsupported parser enums, foreign NPU models
and wrong device provenance, and exercises the
unchanged non-S10 stock import. This is a build/runtime-file contract, not proof
of working portrait capture or editing on a physical device.
