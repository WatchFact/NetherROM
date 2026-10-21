#!/usr/bin/env bash
# Tools only: all firmware, patched filesystems, APKs and kernels start fresh.
set -euo pipefail
repo="${GITHUB_REPOSITORY:-WatchFact/NetherROM}"
mkdir -p tools-download out/tools
gh release download s10-toolchain-20261020-bootstrap --repo "$repo" \
  --pattern s10-tools.tar.gz --dir tools-download
echo '7b391625609ad129765ee6687fc387858b0c3f949856a4ea42d5cf58ed848a05  tools-download/s10-tools.tar.gz' | sha256sum -c -
python3 - <<'PY'
import tarfile
from pathlib import Path
with tarfile.open('tools-download/s10-tools.tar.gz') as t:
    links = {'bin/mke2fs': 'mke2fs.android', 'bin/mkuserimg_mke2fs': 'mkuserimg_mke2fs.py'}
    for m in t.getmembers():
        if not (m.name=='bin' or m.name.startswith('bin/')):
            raise ValueError('Unexpected tool archive member: '+m.name)
        if m.issym() or m.islnk():
            if m.name not in links or Path(m.linkname).name != links[m.name]:
                raise ValueError('Unexpected tool link: '+m.name)
    # The archived compiler runner used absolute links. Recreate only these
    # two known links relative to the new tools directory.
    t.extractall('out/tools',members=[m for m in t.getmembers() if not (m.issym() or m.islnk())],filter='data')
    for name,target in links.items():
        path=Path('out/tools')/name
        if not (path.parent/target).is_file(): raise ValueError('Missing linked tool: '+target)
        path.symlink_to(target)
PY
bash -c 'set -eo pipefail; source ./buildenv.sh beyond2lte; ./scripts/build_dependencies.sh --check-tools'
