#!/usr/bin/env bash
# Restore Android build tools compiled by an independent GitHub Actions runner.
# Verified seed run: 39473364128, tools job 118803016498.
# Publish once to a persistent GitHub prerelease: no further Googlesource
# submodule downloads are required by the ROM assembler.
set -euo pipefail

repo="${GITHUB_REPOSITORY:-WatchFact/NetherROM}"
tag="s10-toolchain-20261020-bootstrap"
run_id=39473364128
artifact="s10-build-tools-22255ab0f7cca9705a4afad6c2905512b917834a"
root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$root"

command -v gh >/dev/null || { echo "Missing GitHub CLI" >&2; exit 1; }
test -n "${GH_TOKEN:-}" || { echo "Missing GitHub token (actions:read, contents:write)" >&2; exit 1; }
mkdir -p precompiled-tools

if gh release view "$tag" --repo "$repo" >/dev/null 2>&1; then
    echo "Downloading Android toolchain from durable GitHub release $tag"
    gh release download "$tag" --repo "$repo" \
        --pattern 's10-tools.tar.gz*' --dir precompiled-tools --clobber
else
    echo "Using successful independent tools runner (run $run_id), without recompilation"
    gh run download "$run_id" --repo "$repo" \
        --name "$artifact" --dir precompiled-tools
fi

test -s precompiled-tools/s10-tools.tar.gz
test -s precompiled-tools/s10-tools.tar.gz.sha256
(cd precompiled-tools && sha256sum --check s10-tools.tar.gz.sha256)

# Reject path escapes before extracting build tools.
tar -tzf precompiled-tools/s10-tools.tar.gz | python3 -c '
import pathlib, sys
for line in sys.stdin:
    name = line.rstrip("\n")
    path = pathlib.PurePosixPath(name)
    if not name or path.is_absolute() or path.parts[0] != "bin" or ".." in path.parts:
        sys.exit("Unsafe toolchain archive member: " + name)
'
mkdir -p out/tools
tar -C out/tools -xzf precompiled-tools/s10-tools.tar.gz
for tool in adb avbtool e2fsdroid mkbootimg apktool img2sdat samloader signapk; do
    test -x "out/tools/bin/$tool" || {
        echo "Missing or non-executable build tool: $tool" >&2
        exit 1
    }
done

# Old buildenv.sh dereferences unset variables; do not source with nounset.
bash -c '
    set -eo pipefail
    source ./buildenv.sh beyond2lte
    ./scripts/build_dependencies.sh --check-tools
'

# Artifact expires in seven days. Promote the validated toolchain to a
# persistent GitHub prerelease after passing complete tool inventory.
if ! gh release view "$tag" --repo "$repo" >/dev/null 2>&1; then
    gh release create "$tag" \
        precompiled-tools/s10-tools.tar.gz \
        precompiled-tools/s10-tools.tar.gz.sha256 \
        --repo "$repo" --target "${GITHUB_SHA:?}" --prerelease \
        --title "S10 build-toolchain bootstrap (NOT A ROM)" \
        --notes "Build tools from the independently successful tools runner, workflow 39473364128. Not flashable firmware."
fi
echo "Verified Android tools restored; no Googlesource submodule checkout needed"
