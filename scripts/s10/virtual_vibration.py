#!/usr/bin/env python3
"""Verify that unsupported virtual vibration is off without altering motor code."""
import hashlib
import json
import re
import sys
import zipfile
from pathlib import Path
from installer import DEVICES

SERVICE = 'system/framework/services.jar'
MANAGER = 'com/android/server/vibrator/VibratorManagerService.smali'
HELPER = 'Lcom/android/server/vibrator/VirtualVibSoundHelper;'
FIELD = 'Lcom/android/server/vibrator/VibratorManagerService;->mVirtualVibSoundHelper:' + HELPER
BOOT = r'^\.method public final bootCompleteReady\(\)V\n.*?^\.end method\n'


def digest(data):
    return hashlib.sha256(data).hexdigest()


def manifest(repo):
    return json.loads((repo/'scripts/s10/virtual-vibration-v4.0.1.json').read_text())


def class_file(decoded, relative):
    paths = list(decoded.glob('smali*/'+relative))
    if len(paths) != 1:
        raise ValueError('Missing or ambiguous virtual vibration migration class: '+relative)
    return paths[0]


def check_classes(decoded, classes):
    for relative, expected in classes.items():
        if digest(class_file(decoded, relative).read_bytes()) != expected:
            raise ValueError('Unreviewed virtual vibration migration class: '+relative)


def check_backend(decoded, info):
    manager = class_file(decoded, MANAGER).read_text()
    boot = re.findall(BOOT, manager, re.M | re.S)
    if len(boot) != 1 or digest(boot[0].encode()) != info['boot_method_sha256']:
        raise ValueError('Virtual vibration startup does not match the S10 migration')
    rest = re.sub(BOOT, '', manager, flags=re.M | re.S)
    if digest(rest.encode()) != info['physical_vibration_code_sha256']:
        raise ValueError('Physical vibration code changed outside the virtual sound startup')
    reads = 0
    for path in decoded.glob('smali*/**/*.smali'):
        instructions = [line.strip() for line in path.read_text().splitlines() if line.strip()]
        for index, line in enumerate(instructions):
            if line.startswith('new-instance ') and HELPER in line:
                raise ValueError('Unsupported virtual sound helper is still allocated')
            if FIELD not in line:
                continue
            if not line.startswith('iget-object '):
                raise ValueError('Unsupported virtual sound helper is still assigned')
            register = line.split()[1].rstrip(',')
            if index+1 >= len(instructions) or not instructions[index+1].startswith('if-eqz '+register+', '):
                raise ValueError('Virtual sound access is not guarded against a null helper')
            reads += 1
    if reads != info['guarded_helper_reads']:
        raise ValueError('Virtual sound entry points differ from the reviewed framework')


def verify(repo, work, apktool, device, stage):
    if device not in DEVICES or stage not in ('before', 'after'):
        raise ValueError('Unsupported S10 virtual vibration migration')
    info = manifest(repo)
    for relative, item in info['artifacts'].items():
        if digest((work/'system'/relative).read_bytes()) != item['source_sha256']:
            raise ValueError('Virtual vibration input differs from the pinned firmware: '+relative)
        check_classes(apktool/relative, item[stage])
    for relative, expected in info['patches'].items():
        if digest((repo/relative).read_bytes()) != expected:
            raise ValueError('Virtual vibration patch differs from the reviewed migration')
    if stage == 'after':
        check_backend(apktool/SERVICE, info)
        (work/'virtual-vibration-provenance.json').write_text(json.dumps(dict(info,device=device),indent=2)+'\n')
    print('Verified unsupported virtual vibration migration:', device, stage)


def output(repo, work, device, apktool):
    info = manifest(repo)
    if json.loads((work/'virtual-vibration-provenance.json').read_text()) != dict(info,device=device):
        raise ValueError('Missing or changed virtual vibration migration provenance')
    for relative, item in info['artifacts'].items():
        check_classes(apktool/relative, item['after'])
        artifact = work/'system'/relative
        if item['before'] != item['after'] and digest(artifact.read_bytes()) == item['source_sha256']:
            raise ValueError('Changed virtual vibration artifact was not rebuilt: '+relative)
        with zipfile.ZipFile(artifact) as z:
            dex = [z.read(n) for n in z.namelist() if re.fullmatch(r'classes(?:[0-9]+)?\.dex',n)]
            if not dex or z.testzip():
                raise ValueError('Invalid rebuilt virtual vibration migration artifact: '+relative)
        for name in item['after']:
            descriptor = ('L'+name.removesuffix('.smali')+';').encode()+b'\0'
            if not any(descriptor in data for data in dex):
                raise ValueError('Rebuilt virtual vibration class is absent: '+name)
    check_backend(apktool/SERVICE, info)
    print('Virtual sound is disabled and physical vibration code is preserved:', device)


if __name__ == '__main__':
    verify(Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3]), sys.argv[4], sys.argv[5])
