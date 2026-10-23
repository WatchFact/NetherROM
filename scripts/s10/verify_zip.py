#!/usr/bin/env python3
import json
import hashlib
import sys
import zipfile
from pathlib import Path
from installer import BUDGET, DEVICES, generate
from kernel_artifacts import KERNEL_REV


def verify(path, device):
    with zipfile.ZipFile(path) as z:
        names = z.namelist()
        if len(names) != len(set(names)):
            raise ValueError("Duplicate ZIP entries")
        for name in names:
            if name.startswith('/') or '..' in Path(name).parts:
                raise ValueError("Unsafe ZIP member")
            if 'super' in name or 'dynamic_partitions' in name:
                raise ValueError("Dynamic partition data in legacy S10 ZIP")
        for part in BUDGET:
            for suffix in ('.transfer.list', '.new.dat.br', '.patch.dat'):
                member = z.getinfo(part + suffix)
                if suffix != '.patch.dat' and member.file_size == 0:
                    raise ValueError('Empty OTA partition payload: '+part+suffix)
        for part in ('boot', 'dtb', 'dtbo'):
            if z.getinfo(part+'.img').file_size < 2048:
                raise ValueError("Missing kernel image")
        z.getinfo('META-INF/com/google/android/update-binary')
        updater = z.read('META-INF/com/google/android/updater-script').decode()
        sizes = json.loads(z.read('sizes.json'))
        expected_preflight, expected_updater = generate(device, sizes)
        if z.read('s10-preflight.sh').decode() != expected_preflight:
            raise ValueError('Packaged device/capacity/alias preflight was modified')
        if updater != expected_updater:
            raise ValueError('Packaged updater does not match audited generator')
        if any(w in updater for w in ('map_partition', 'update_dynamic_partitions', 'repartition')):
            raise ValueError("Invalid S10 installer")
        for part in BUDGET:
            if f'block_image_update("/dev/block/by-name/{part}"' not in updater:
                raise ValueError("Missing physical block installation")
        if updater.index('run_program("/tmp/s10-preflight.sh")') > updater.index('block_image_update'):
            raise ValueError("Partition preflight occurs after block writes")
        for model in DEVICES[device]:
            if model not in updater:
                raise ValueError("Missing model assertion")
        info = json.loads(z.read('kernel.json'))
        if (info['device'] != device or info['revision'] != KERNEL_REV
                or info['kernelsu'] is not False or info['ext4'] is not True):
            raise ValueError("Wrong kernel variant, revision or configuration")
        for name in ('boot.img', 'dtb.img', 'dtbo.img'):
            if hashlib.sha256(z.read(name)).hexdigest() != info['sha256'][name]:
                raise ValueError('Kernel image changed during packaging: '+name)
        from legacy_features import manifest as legacy_manifest
        from camera_portrait import RECORD, validate_record
        validate_record(json.loads(z.read(RECORD)), device)
        from odm_layout import RECORD as ODM_RECORD, validate_record as validate_odm
        validate_odm(json.loads(z.read(ODM_RECORD)), device)
        legacy = legacy_manifest(Path(__file__).resolve().parents[2])
        for mode in ('wifi', 'fingerprint') if device == 'beyond0lte' else ('wifi',):
            expected = dict(legacy['migrations'][mode], device=device,
                            source_firmware=legacy['source_firmware'], mode=mode)
            if json.loads(z.read(mode+'-provenance.json')) != expected:
                raise ValueError('Wrong packaged S10 '+mode+' migration provenance')
        bad = z.testzip()
        if bad:
            raise ValueError("Corrupted ZIP member: " + bad)
    print('ZIP structure and CRC passed:', path)


if __name__ == '__main__':
    verify(Path(sys.argv[1]), sys.argv[2])
