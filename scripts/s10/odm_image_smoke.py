#!/usr/bin/env python3
"""Exercise the production ODM import and image builder with pinned real tools."""
import argparse
import os
import struct
import subprocess
import tempfile
from pathlib import Path
from installer import DEVICES
from odm_layout import prepare, finalize


def fixture(work, device):
    root = work/'vendor/odm'
    (root/'etc').mkdir(parents=True)
    (root/'etc/build.prop').write_text(
        'ro.product.odm.model='+DEVICES[device][0]+'\nro.product.odm.device='+
        device.removesuffix('lte')+'\nro.odm.build.version.sdk=31\npersist.sys.usb.config=mtp\n')
    (root/'etc/NOTICE.xml.gz').write_bytes(b'ODM image regression payload')
    (root/'etc/group').touch()
    (root/'etc/passwd').touch()
    (work/'configs').mkdir()
    fs, fc = [], []
    import re
    for p in [root, *sorted(root.rglob('*'))]:
        name = p.relative_to(work).as_posix()
        fs.append(name+' 0 2000 '+('755' if p.is_dir() else '640')+' capabilities=0x0')
        fc.append(re.escape('/'+name)+' u:object_r:vendor_file:s0')
    (work/'configs/fs_config-vendor').write_text('\n'.join(fs)+'\n')
    (work/'configs/file_context-vendor').write_text('\n'.join(fc)+'\n')


def smoke(repo, tools, device):
    with tempfile.TemporaryDirectory(prefix='s10-odm-image-') as td:
        root = Path(td); work = root/'work'
        fixture(work, device)
        prepare(work, device)
        finalize(work, device)
        image = root/'odm.img'
        env = dict(os.environ, SRC_DIR=str(repo), WORK_DIR=str(work), TARGET_CODENAME=device,
                   PATH=str(tools/'bin')+os.pathsep+os.environ['PATH'])
        source = (repo/'scripts/build_fs_image.sh').read_text()
        builder = source[source.index('BUILD_IMAGE_MKFS()\n'):
                         source.index('\n# https://android.googlesource.com/platform/build/',
                                      source.index('BUILD_IMAGE_MKFS()\n'))]
        script = '''set -eo pipefail
FS_TYPE=ext4; SPARSE=true; SHARE_DUP_BLOCKS=true; MAP_FILE=true; PARTITION=odm; MOUNT_POINT=odm
INPUT_DIR="$1/odm"; OUTPUT_FILE="$2"; IMAGE_SIZE=4194304; INODES=""
FILE_CONTEXT_FILE="$1/configs/file_context-odm"; FS_CONFIG_FILE="$1/configs/fs_config-odm"
EVAL(){ eval "$1"; }
'''+builder+'\nBUILD_IMAGE_MKFS\n'
        result = subprocess.run(['bash', '-c', script, '--', str(work), str(image)],
                                env=env, capture_output=True, text=True)
        if result.returncode:
            raise RuntimeError(result.stdout+result.stderr)
        header = image.read_bytes()[:28]
        if struct.unpack_from('<I', header)[0] != 0xed26ff3a:
            raise ValueError('ODM smoke did not build the actual sparse image')
        if struct.unpack_from('<I', header, 12)[0]*struct.unpack_from('<I', header, 16)[0] != 4194304:
            raise ValueError('ODM expanded image exceeds its real 4 MiB partition')
        if not image.with_suffix('.map').is_file():
            raise ValueError('ODM block OTA map was not generated')
        subprocess.run(['bash', str(repo/'scripts/s10/verify_image.sh'), 'odm', str(image)],
                       env=env, check=True)
        raw = root/'raw.img'
        subprocess.run([str(tools/'bin/simg2img'), str(image), str(raw)], check=True)
        # Use the same OTA encoder as package.sh. Reconstruct its full-update
        # transfer commands and audit the resulting filesystem as an installer
        # would see it, including files and SELinux/ownership attributes.
        encoded = subprocess.run([str(tools/'bin/img2sdat'), '-o', str(root), str(image)],
                                 capture_output=True, text=True)
        if encoded.returncode: raise RuntimeError(encoded.stdout+encoded.stderr)
        lines = (root/'odm.transfer.list').read_text().splitlines()
        if lines[0] != '4' or not (root/'odm.new.dat').stat().st_size:
            raise ValueError('Invalid production ODM block OTA')
        restored = root/'restored.raw'; restored.write_bytes(bytes(4194304))
        with restored.open('r+b') as output, (root/'odm.new.dat').open('rb') as data:
            for line in lines[4:]:
                command, ranges = line.split()
                values = list(map(int, ranges.split(',')))
                if command not in ('new', 'zero', 'erase') or values[0] != len(values)-1 or values[0] % 2:
                    raise ValueError('Unexpected full ODM OTA transfer command')
                for start, end in zip(values[1::2], values[2::2]):
                    if not 0 <= start < end <= 1024:
                        raise ValueError('ODM OTA transfer exceeds physical capacity')
                    size = (end-start)*4096
                    payload = data.read(size) if command == 'new' else bytes(size)
                    if len(payload) != size: raise ValueError('Truncated ODM OTA payload')
                    output.seek(start*4096); output.write(payload)
            if data.read(1): raise ValueError('Unreferenced ODM OTA payload')
        restored_sparse = root/'restored.img'
        subprocess.run([str(tools/'bin/img2simg'), str(restored), str(restored_sparse)], check=True)
        subprocess.run(['bash', str(repo/'scripts/s10/verify_image.sh'), 'odm', str(restored_sparse)],
                       env=env, check=True)
        subprocess.run(['debugfs', '-w', '-R', 'set_inode_field /etc/build.prop uid 1234', str(raw)],
                       check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        bad_owner = root/'bad-owner.img'
        subprocess.run([str(tools/'bin/img2simg'), str(raw), str(bad_owner)], check=True)
        rejected = subprocess.run(['bash', str(repo/'scripts/s10/verify_image.sh'), 'odm', str(bad_owner)],
                                  env=env, capture_output=True, text=True)
        if rejected.returncode == 0 or 'metadata differs in ext4' not in rejected.stdout+rejected.stderr:
            raise ValueError('ODM image audit accepted or misclassified changed ownership')
        subprocess.run(['debugfs', '-w', '-R', 'set_inode_field /etc/build.prop uid 0', str(raw)],
                       check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        damaged = root/'changed.prop'; damaged.write_bytes(b'wrong ODM hardware payload')
        for command in ('rm /etc/build.prop', 'write '+str(damaged)+' /etc/build.prop'):
            subprocess.run(['debugfs', '-w', '-R', command, str(raw)], check=True,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        corrupt = root/'corrupt.img'
        subprocess.run([str(tools/'bin/img2simg'), str(raw), str(corrupt)], check=True)
        rejected = subprocess.run(['bash', str(repo/'scripts/s10/verify_image.sh'), 'odm', str(corrupt)],
                                  env=env, capture_output=True, text=True)
        if rejected.returncode == 0 or 'differs in ext4' not in rejected.stdout+rejected.stderr:
            raise ValueError('ODM image audit accepted or misclassified corrupted payload')
        print('Real 4 MiB sparse ext4 ODM, metadata, OTA reconstruction and corruption rejection passed:', device)


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--repo', type=Path, required=True)
    p.add_argument('--tools', type=Path, required=True)
    p.add_argument('--device', choices=DEVICES, required=True)
    args = p.parse_args()
    smoke(args.repo.resolve(), args.tools.resolve(), args.device)
