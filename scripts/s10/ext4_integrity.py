#!/usr/bin/env python3
"""Verify lossless ext4 payloads and reconstruct full block OTAs for tool tests."""
import hashlib
import subprocess
import shutil
import sys
from pathlib import Path


def file_digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def verify_files(source, raw, temporary):
    count = 0
    destination = temporary/'ext4-file'
    for path in sorted(source.rglob('*')):
        if path.is_symlink() or not path.is_file():
            continue
        name = path.relative_to(source).as_posix()
        if any(c in name for c in ('"', '\\', '\n', '\r')):
            raise ValueError('Unreviewed ext4 pathname: '+name)
        destination.unlink(missing_ok=True)
        subprocess.run(['debugfs', '-R', f'dump "/{name}" "{destination}"', str(raw)],
                       check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if not destination.is_file() or file_digest(destination) != file_digest(path):
            raise ValueError('File differs in ext4: '+name)
        destination.unlink()
        count += 1
    if not count:
        raise ValueError('No regular files audited in ext4')
    print('Every regular file verified in actual ext4:', source.name, count)


def reconstruct_full_ota(folder, part, image_size):
    lines = (folder/(part+'.transfer.list')).read_text().splitlines()
    if lines[0] != '4' or not (folder/(part+'.new.dat')).stat().st_size:
        raise ValueError('Invalid production block OTA')
    restored = folder/(part+'-restored.raw')
    with restored.open('wb') as stream: stream.truncate(image_size)
    with restored.open('r+b') as output, (folder/(part+'.new.dat')).open('rb') as data:
        for line in lines[4:]:
            command, ranges = line.split()
            values = list(map(int, ranges.split(',')))
            if command not in ('new', 'zero', 'erase') or values[0] != len(values)-1 or values[0] % 2:
                raise ValueError('Unexpected full OTA transfer command')
            for start, end in zip(values[1::2], values[2::2]):
                if not 0 <= start < end <= image_size//4096:
                    raise ValueError('OTA transfer exceeds physical capacity')
                size = (end-start)*4096
                output.seek(start*4096)
                while size:
                    chunk=min(size,1048576)
                    payload=data.read(chunk) if command=='new' else bytes(chunk)
                    if len(payload)!=chunk: raise ValueError('Truncated OTA payload')
                    output.write(payload); size-=chunk
        if data.read(1): raise ValueError('Unreferenced OTA payload')
    return restored


def verify_ota(image):
    # Read the actual sparse image with the same pinned AOSP parser used by
    # img2sdat. Require all care blocks to be written, then compare them byte
    # for byte against the reconstructed full update, using bounded memory.
    encoder=shutil.which('img2sdat')
    if not encoder: raise ValueError('Missing pinned OTA encoder')
    sys.path.insert(0,str(Path(encoder).resolve().parent))
    from sparse_img import SparseImage
    from rangelib import RangeSet
    source=SparseImage(str(image))
    part=image.stem; folder=image.parent
    written=RangeSet()
    for line in (folder/(part+'.transfer.list')).read_text().splitlines()[4:]:
        command,ranges=line.split()
        if command in ('new','zero'):
            current=RangeSet.parse_raw(ranges)
            if written.intersect(current).size():
                raise ValueError('Full OTA contains overlapping writes')
            written=written.union(current)
    if source.blocksize!=4096 or source.care_map.subtract(written).size():
        raise ValueError('Full OTA does not write every filesystem care block')
    restored=reconstruct_full_ota(folder,part,source.total_blocks*source.blocksize)
    try:
        with restored.open('rb') as stream:
            for start,end in source.care_map:
                for offset in range(start,end,256):
                    blocks=min(256,end-offset)
                    expected=b''.join(source.ReadBlocks(offset,blocks))
                    stream.seek(offset*4096)
                    if stream.read(blocks*4096)!=expected:
                        raise ValueError('Full OTA differs from audited ext4: '+part)
    finally:
        restored.unlink(missing_ok=True)
        source.simg_f.close()
    print('Full OTA writes and preserves every audited filesystem care block:',part)


if __name__=='__main__':
    verify_ota(Path(sys.argv[1]))
