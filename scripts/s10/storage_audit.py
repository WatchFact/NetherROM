#!/usr/bin/env python3
"""Verify the pinned boot ramdisk already supports physical ext4 S10 mounts."""
import gzip
import struct
import sys
from pathlib import Path, PurePosixPath
from kernel_artifacts import validate

PARTITIONS = ('system', 'vendor', 'product', 'odm')


def cpio_files(data):
    entries = {}; offset = 0
    while offset + 110 <= len(data):
        header = data[offset:offset+110]
        if header[:6] != b'070701':
            raise ValueError('Unsupported or corrupt boot ramdisk CPIO')
        fields = [int(header[6+i*8:14+i*8], 16) for i in range(13)]
        size, namesize = fields[6], fields[11]
        start = offset+110; end = start+namesize
        if namesize < 1 or end > len(data) or data[end-1] != 0:
            raise ValueError('Truncated ramdisk name')
        name = data[start:end-1].decode()
        if name == 'TRAILER!!!':
            return entries
        path = PurePosixPath(name)
        if path.is_absolute() or '..' in path.parts or str(path) in entries:
            raise ValueError('Unsafe or duplicate ramdisk path')
        start = (end+3)//4*4; end = start+size
        if end > len(data):
            raise ValueError('Truncated ramdisk entry')
        entries[str(path)] = (fields[1], data[start:end])
        offset = (end+3)//4*4
    raise ValueError('Missing CPIO trailer')


def boot_fstab(data):
    if data[:8] != b'ANDROID!' or len(data) < 1648:
        raise ValueError('Invalid S10 boot header')
    kernel_size, _, ramdisk_size, _, second_size, _, _, page, version = struct.unpack_from('<9I', data, 8)
    if version != 1 or page != 2048 or not kernel_size or not ramdisk_size or second_size:
        raise ValueError('Unexpected pinned S10 boot layout')
    start = page+(kernel_size+page-1)//page*page
    ramdisk = data[start:start+ramdisk_size]
    if len(ramdisk) != ramdisk_size:
        raise ValueError('Truncated boot ramdisk')
    files = cpio_files(gzip.decompress(ramdisk))
    matches = [(mode, content) for name, (mode, content) in files.items()
               if PurePosixPath(name).name == 'fstab.exynos9820']
    if len(matches) != 1 or matches[0][0] & 0o170000 != 0o100000:
        raise ValueError('Missing or ambiguous S10 ramdisk fstab')
    return matches[0][1].decode()


def check_fstab(text, ramdisk=False):
    rows = [line.split() for line in text.splitlines() if line.strip() and not line.lstrip().startswith('#')]
    if any(len(row) < 5 for row in rows):
        raise ValueError('Malformed S10 fstab')
    for row in rows:
        if any(flag.startswith(('logical', 'avb', 'verify', 'fileencryption', 'forceencrypt', 'encryptable', 'metadata_encryption'))
               for flag in row[4].split(',')) or '/by-name/super' in row[0]:
            raise ValueError('Unsupported dynamic, verified or encrypted S10 storage')
    for part in PARTITIONS:
        mounts = [r for r in rows if r[1] == '/'+part]
        if not mounts or any(not r[0].startswith('/dev/block/') or not r[0].endswith('/by-name/'+part)
                             or r[2] not in (('ext4', 'erofs') if ramdisk else ('ext4',))
                             or 'ro' not in r[3].split(',') for r in mounts):
            raise ValueError('Missing physical read-only ext4 mount: '+part)
        if not any(r[2] == 'ext4' and (not ramdisk or 'first_stage_mount' in r[4].split(',')) for r in mounts):
            raise ValueError('Missing first-stage ext4 support: '+part)
    data = [r for r in rows if r[1] == '/data']
    if len(data) != 1 or data[0][2] != 'f2fs' or not data[0][0].endswith('/by-name/userdata'):
        raise ValueError('S10 userdata must match the pinned F2FS kernel layout')


def audit(work, device):
    validate(work/'kernel', device)
    check_fstab(boot_fstab((work/'kernel/boot.img').read_bytes()), ramdisk=True)
    check_fstab((work/'vendor/etc/fstab.exynos9820').read_text())
    print('Pinned boot, DTB/DTBO digests and physical ext4/F2FS mounts verified:', device)


if __name__ == '__main__':
    audit(Path(sys.argv[1]), sys.argv[2])
