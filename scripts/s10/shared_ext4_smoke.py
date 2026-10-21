#!/usr/bin/env python3
"""Exercise the actual pinned shared-block builder and OTA encoder losslessly."""
import argparse
import hashlib
import os
import re
import struct
import subprocess
import tempfile
from pathlib import Path
from ext4_integrity import verify_files, reconstruct_full_ota, verify_ota


def run(command, **kwargs):
    result = subprocess.run(command, capture_output=True, text=True, **kwargs)
    if result.returncode: raise RuntimeError(result.stdout+result.stderr)
    return result.stdout+result.stderr


def smoke(repo, tools):
    with tempfile.TemporaryDirectory(prefix='s10-shared-ext4-') as td:
        root=Path(td); source=root/'system'; (source/'system').mkdir(parents=True)
        payload=hashlib.shake_256(b'S10 deterministic unique blocks').digest(8*1048576)
        metadata={'.':(0,0,'755'), 'system':(0,0,'755'),
                  'system/one':(0,2000,'644'), 'system/two':(1000,1000,'750'),
                  'system/three':(1001,1001,'600')}
        for name in ('one','two','three'): (source/'system'/name).write_bytes(payload)
        fs=root/'fs_config'; fc=root/'file_context'
        fs.write_text('\n'.join(('' if n=='.' else n)+' '+' '.join(map(str,v))+' capabilities=0x0'
                                for n,v in metadata.items())+'\n')
        fc.write_text('\n'.join(re.escape('/' if n=='.' else '/'+n)+' u:object_r:system_file:s0'
                                for n in metadata)+'\n')
        script=(repo/'scripts/build_fs_image.sh').read_text()
        builder=script[script.index('BUILD_IMAGE_MKFS()\n'):
                       script.index('\n# https://android.googlesource.com/platform/build/',script.index('BUILD_IMAGE_MKFS()\n'))]
        setup='''set -eo pipefail
FS_TYPE=ext4; SPARSE=true; MAP_FILE=true; PARTITION=system; MOUNT_POINT=/; INODES=""
INPUT_DIR="$1/system"; OUTPUT_FILE="$2"; IMAGE_SIZE=12582912; SHARE_DUP_BLOCKS="$3"
FILE_CONTEXT_FILE="$1/file_context"; FS_CONFIG_FILE="$1/fs_config"
EVAL(){ eval "$1"; }
'''
        env=dict(os.environ,PATH=str(tools/'bin')+os.pathsep+os.environ['PATH'])
        image=root/'system.img'
        # The control really must fail: 24 MiB of distinct inodes cannot fit
        # this 12 MiB partition unless identical data blocks are shared.
        control=subprocess.run(['bash','-c',setup+builder+'\nBUILD_IMAGE_MKFS','--',str(root),str(root/'control.img'),'false'],
                               env=env,capture_output=True,text=True)
        if (control.returncode==0 or not any(message in control.stdout+control.stderr
                for message in ('Could not allocate block', 'No space left on device'))):
            raise ValueError('Unshared ext4 control did not fail on capacity: '+control.stdout+control.stderr)
        run(['bash','-c',setup+builder+'\nBUILD_IMAGE_MKFS','--',str(root),str(image),'true'],env=env)
        header=image.read_bytes()[:28]
        if (struct.unpack_from('<I',header)[0]!=0xed26ff3a or
                struct.unpack_from('<I',header,12)[0]*struct.unpack_from('<I',header,16)[0]!=12582912):
            raise ValueError('Shared sparse ext4 has wrong expanded capacity')
        raw=root/'system.raw'
        run([str(tools/'bin/simg2img'),str(image),str(raw)])
        info=run(['tune2fs','-l',str(raw)])
        if 'shared_blocks' not in info or 'has_journal' in info:
            raise ValueError('Missing read-only shared blocks or unexpected journal')
        run(['e2fsck','-f','-n',str(raw)])
        verify_files(source,raw,root)
        def attrs(path):
            ids=[]
            for name,(uid,gid,mode) in metadata.items():
                stat=run(['debugfs','-R','stat '+('/' if name=='.' else '/'+name),str(path)])
                if (not re.search(r'User:\s+'+str(uid)+r'\s+Group:\s+'+str(gid)+r'\b',stat)
                        or int(re.search(r'Mode:\s+([0-7]+)',stat)[1],8)!=int(mode,8)
                        or 'u:object_r:system_file:s0' not in stat):
                    raise ValueError('Shared data changed independent inode metadata: '+name)
                ids.append(re.search(r'Inode:\s+(\d+)',stat)[1])
            if len(ids)!=len(set(ids)): raise ValueError('Data sharing incorrectly merged inodes')
        attrs(raw)
        # File block maps overlap after deduplication. Full OTAs use the
        # sparse image's actual block ranges, with no incremental file map.
        run([str(tools/'bin/img2sdat'),'-o',str(root),str(image)])
        old_path=os.environ.get('PATH','')
        try:
            os.environ['PATH']=env['PATH']; verify_ota(image)
            data=root/'system.new.dat'
            with data.open('r+b') as stream:
                byte=stream.read(1); stream.seek(0); stream.write(bytes([byte[0]^1]))
            try: verify_ota(image)
            except ValueError as error:
                if 'OTA differs' not in str(error): raise
            else: raise ValueError('Corrupted full OTA was accepted')
            with data.open('r+b') as stream: stream.write(byte)
            transfer=root/'system.transfer.list'; saved=transfer.read_text()
            transfer.write_text('\n'.join(saved.splitlines()[:4])+'\n')
            try: verify_ota(image)
            except ValueError as error:
                if 'does not write every' not in str(error): raise
            else: raise ValueError('Incomplete full OTA was accepted')
            transfer.write_text(saved)
        finally: os.environ['PATH']=old_path
        restored=reconstruct_full_ota(root,'system',12582912)
        run(['e2fsck','-f','-n',str(restored)])
        verify_files(source,restored,root); attrs(restored)
        blocks=run(['debugfs','-R','blocks /system/one',str(restored)]).splitlines()[0].split()
        block=int(blocks[0])
        with restored.open('r+b') as stream:
            stream.seek(block*4096); byte=stream.read(1); stream.seek(block*4096); stream.write(bytes([byte[0]^1]))
        try: verify_files(source,restored,root)
        except ValueError as error:
            if 'differs in ext4' not in str(error): raise
        else: raise ValueError('Shared ext4 corruption was accepted')
        print('Real shared ext4 and OTA preserve every byte and distinct inode metadata; corruption rejected')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--repo',type=Path,required=True); p.add_argument('--tools',type=Path,required=True)
    a=p.parse_args(); smoke(a.repo.resolve(),a.tools.resolve())
