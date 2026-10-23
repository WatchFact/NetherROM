#!/usr/bin/env bash
# Compare representative hardware files inside the actual sparse ext4 image.
set -euo pipefail
part="${1:?}"; image="${2:?}"
case "$part" in system|vendor|product|odm) ;; *) echo "Unsupported S10 partition: $part" >&2; exit 1;; esac
tmp="$(mktemp -d)"
trap 'python3 -c "import shutil,sys; shutil.rmtree(sys.argv[1])" "$tmp"' EXIT
simg2img "$image" "$tmp/raw.img"
# Verify the complete ext4 superblock, inode tables and directory structure,
# including product (which has no individual legacy hardware blob checks).
if ! e2fsck -fn "$tmp/raw.img" > "$tmp/e2fsck.log" 2>&1; then
  cat "$tmp/e2fsck.log" >&2
  echo "Invalid generated ext4 filesystem: $part" >&2
  exit 1
fi
python3 - "$SRC_DIR" "$WORK_DIR" "$tmp" "$part" <<'PY'
import hashlib,subprocess,sys
from pathlib import Path
sys.path.insert(0,str(Path(sys.argv[1])/'scripts/s10'))
from audit_output import SYSTEM_FILES,VENDOR_FILES
from camera_portrait import RECORD,validate_record
from odm_layout import image_paths,verify_image_metadata
import json,os
work,tmp,part=Path(sys.argv[2]),Path(sys.argv[3]),sys.argv[4]
paths=[]
if part in ('system','vendor'):
    portrait=validate_record(json.loads((work/RECORD).read_text()),os.environ['TARGET_CODENAME'])
    paths=list(SYSTEM_FILES if part=='system' else VENDOR_FILES)
    paths+=sorted(n.removeprefix(part+'/') for n in portrait if n.startswith(part+'/'))
if part in ('vendor','odm'):
    paths+=image_paths(work,os.environ['TARGET_CODENAME'],part)
paths=list(dict.fromkeys(paths))
for i,relative in enumerate(paths):
    dest=tmp/f'dump-{i}'
    subprocess.run(['debugfs','-R',f'dump /{relative} {dest}',str(tmp/'raw.img')],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    if not dest.is_file(): raise SystemExit('Missing hardware file in ext4: '+relative)
    expected=hashlib.sha256((work/part/relative).read_bytes()).hexdigest()
    if hashlib.sha256(dest.read_bytes()).hexdigest()!=expected:
        raise SystemExit('Hardware file differs in ext4: '+relative)
if part in ('vendor','odm'):
    verify_image_metadata(work,os.environ['TARGET_CODENAME'],part,tmp/'raw.img')
print('Actual ext4 hardware contents verified:',part)
PY
