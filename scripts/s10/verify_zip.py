#!/usr/bin/env python3
"""Fail-closed validation of the signed S10+ physical-partition ROM ZIP."""
import hashlib
import json
import sys
import zipfile
from pathlib import Path

from installer import DEVICE, PARTS, RAW, GUARD, UPDATER, generate
from kernel_artifacts import KERNEL_REV


def verify(path, device):
    if device != DEVICE:
        raise ValueError('Wrong S10+ device')
    with zipfile.ZipFile(path) as z:
        names = z.namelist()
        if len(set(names)) != len(names) or any(
                n.startswith('/') or '\\' in n or '..' in Path(n).parts for n in names):
            raise ValueError('Unsafe or duplicated ZIP member')
        if any('super' in n or 'dynamic_partitions' in n for n in names):
            raise ValueError('Dynamic partition data in legacy S10 ZIP')
        if 's10-preflight.sh' in names:
            raise ValueError('Unexpected legacy device preflight')
        for part in PARTS:
            for suffix in ('.transfer.list', '.new.dat.br', '.patch.dat'):
                name = part + suffix
                if suffix != '.patch.dat' and not z.getinfo(name).file_size:
                    raise ValueError('Empty OTA partition payload: ' + name)
        for name in RAW:
            if z.getinfo(name + '.img').file_size < 2048:
                raise ValueError('Missing kernel image: ' + name)
        if not z.getinfo('META-INF/com/google/android/update-binary').file_size:
            raise ValueError('Missing recovery updater binary')
        sizes = json.loads(z.read('sizes.json'))
        guard, updater = generate(device, sizes)
        if z.read(GUARD).decode() != guard:
            raise ValueError('Packaged installer write guard was modified')
        if z.read(UPDATER).decode() != updater:
            raise ValueError('Packaged updater does not match audited generator')

        info = json.loads(z.read('kernel.json'))
        if (info.get('device') != device or info.get('revision') != KERNEL_REV
                or info.get('kernelsu') is not False or info.get('ext4') is not True):
            raise ValueError('Wrong S10 kernel variant, revision or configuration')
        for name in RAW:
            data = z.read(name + '.img')
            if len(data) != sizes[name] or hashlib.sha256(data).hexdigest() != info['sha256'][name + '.img']:
                raise ValueError('Kernel image changed during packaging: ' + name)

        from camera_portrait import RECORD as CAMERA, validate_record as validate_camera
        from odm_layout import RECORD as ODM, validate_record as validate_odm
        from legacy_features import manifest as legacy_manifest
        validate_camera(json.loads(z.read(CAMERA)), device)
        validate_odm(json.loads(z.read(ODM)), device)
        legacy = legacy_manifest(Path(__file__).resolve().parents[2])
        expected = dict(legacy['migrations']['wifi'], device=device,
                        source_firmware=legacy['source_firmware'], mode='wifi')
        if json.loads(z.read('wifi-provenance.json')) != expected:
            raise ValueError('Wrong packaged S10 wifi migration provenance')
        damaged = z.testzip()
        if damaged:
            raise ValueError('Corrupted ZIP member: ' + damaged)
    print('Signed S10+ ZIP structure, provenance, digests and CRC passed:', path)


if __name__ == '__main__':
    verify(Path(sys.argv[1]), sys.argv[2])
