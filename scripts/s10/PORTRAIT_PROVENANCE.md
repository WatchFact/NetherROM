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

The Exynos9820 branch now retains that complete model set. Other platforms keep
the generic target import. No stock S10 HAL, vendor model, camera APK or existing
camera validation is removed. The provenance guard compares the nexus JSON,
all portrait files and the exact bounded library patch against fresh, version-
pinned source firmware before recording their SHA256 digests. It also checks
the JSON transformation and every non-null Weightfile reference. Later camera
stages and final output must match the record. Actual ext4 extraction compares
every recorded portrait file and library; the ZIP carries the provenance and
checks its device, firmware identity and required digest entries.

The regression executes the actual platform portrait block and generic camera
import block in order for all four S10 targets. It rejects missing or changed
models, changed library bytes and wrong device provenance, and exercises the
unchanged non-S10 stock import. This is a build/runtime-file contract, not proof
of working portrait capture or editing on a physical device.
