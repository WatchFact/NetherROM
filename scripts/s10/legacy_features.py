#!/usr/bin/env python3
"""Verify the reviewed source-specific S10 fingerprint and Wi-Fi migrations."""
import hashlib
import json
import re
import sys
import zipfile
from pathlib import Path
from installer import DEVICES as BUILD_DEVICES

# Validation-only reference for legacy S10e fingerprint migration fixtures.
# This does not enable S10e as a build or install target.
DEVICES = {**BUILD_DEVICES, 'beyond0lte': ('SM-G970F', 'SM-G970N')}


def digest(data):
    return hashlib.sha256(data).hexdigest()


def manifest(repo):
    return json.loads((repo/'scripts/s10/legacy-features-v4.0.1.json').read_text())


def class_file(decoded, relative):
    matches = list(decoded.glob('smali*/'+relative))
    if len(matches) != 1:
        raise ValueError('Missing or ambiguous legacy feature class: '+relative)
    data = matches[0].read_text()
    descriptor = 'L'+relative.removesuffix('.smali')+';'
    if not re.search(r'^\.class .* '+re.escape(descriptor)+r'$', data, re.M):
        raise ValueError('Wrong legacy feature class descriptor: '+relative)
    return matches[0]


def check_classes(decoded, expected):
    for relative, expected_digest in expected.items():
        if expected_digest is None:
            if list(decoded.glob('smali*/'+relative)):
                raise ValueError('Unexpected legacy feature class: '+relative)
        elif digest(class_file(decoded, relative).read_bytes()) != expected_digest:
            raise ValueError('Unreviewed legacy feature implementation: '+relative)


def method(text, signature):
    matches = re.findall(r'^\.method[^\n]* '+re.escape(signature)+r'\n.*?^\.end method\n', text, re.M | re.S)
    if len(matches) != 1:
        raise ValueError('Missing or ambiguous legacy feature method: '+signature)
    return matches[0]


def check_output_classes(decoded, item):
    check_classes(decoded, item['output'])
    for relative, expected in item['output_methods'].items():
        text = class_file(decoded, relative).read_text()
        for signature, expected_digest in expected.items():
            if digest(method(text, signature).encode()) != expected_digest:
                raise ValueError('Changed legacy feature method: '+relative+' '+signature)
    for relative, expected in item['field_constants'].items():
        text = method(class_file(decoded, relative).read_text(), '<clinit>()V')
        for field, assignment in expected.items():
            reg, value = assignment['register'], assignment['value']
            # Fresh locals are assigned once and used for these feature flags;
            # unrelated HFR literals can change without spoofing FP hardware.
            writes = [line.strip() for line in text.splitlines()
                      if re.match(r'\s*\S+ '+reg+r',', line)
                      and not line.strip().startswith('sput-boolean ')]
            if writes != ['const/16 '+reg+', '+value]:
                raise ValueError('Fingerprint capability register is overwritten: '+relative)
            assignments = re.findall(r'sput-boolean (v\d+), L[^;]+;->'+re.escape(field)+r':Z', text)
            if assignments != [reg]:
                raise ValueError('Wrong fingerprint hardware flag: '+field)


def check_semantics(apktool, mode):
    def read(artifact, relative):
        return class_file(apktool/artifact, relative).read_text()

    def returns(artifact, relative, signature, value):
        body = method(read(artifact, relative), signature)
        if not re.search(r'const/4 (v\d+|p\d+), '+value+r'\s+return \1', body):
            raise ValueError('Wrong S10 hardware result: '+signature)

    if mode == 'wifi':
        artifact = 'system/framework/semwifi-service.jar'
        relative = 'com/samsung/android/server/wifi/ap/SemWifiApChipInfo.smali'
        text = read(artifact, relative)
        sharing = method(text, 'checkWifiSharingAndPowerSave()V')
        if ('mSupportWifiSharing:Z = false' not in text
                or 'DualBandConcurrency' not in text or 'DualInterface' not in text
                or sharing.count('sput-boolean v5, Lcom/samsung/android/server/wifi/ap/SemWifiApChipInfo;->mSupportWifiSharing:Z') != 3
                or not re.search(r':cond_3\s+:goto_0\s+new-instance', sharing)):
            raise ValueError('S10 Wi-Fi sharing must retain chip capability detection')
        config = read(artifact, 'com/samsung/android/server/wifi/ap/SemSoftApConfiguration.smali')
        if 'SPF_Concurrency=true' in config or 'SPF_Concurrency=false' not in config:
            raise ValueError('Wi-Fi sharing must not advertise a forced concurrency override')
        relative = 'com/samsung/android/server/wifi/driver/WifiDriverFeatureProvider.smali'
        returns(artifact, relative, 'getTwtFeature()I', '0x0')
        returns(artifact, relative, 'isTwtSupported()Z', '0x0')
    else:
        artifact = 'system/framework/framework.jar'
        returns(artifact, 'android/hardware/fingerprint/FingerprintManager.smali', 'semGetSensorPosition()I', '0x4')
        returns(artifact, 'com/samsung/android/bio/fingerprint/SemFingerprintManager$Characteristics.smali', 'getSensorType()I', '0x1')
        artifact = 'system/framework/services.jar'
        base = 'com/android/server/biometrics/sensors/fingerprint/'
        extension = method(read(artifact, base+'SemFingerprintServiceExtImpl.smali'),
                           'onHalStarted(Lcom/android/server/biometrics/sensors/fingerprint/ServiceProvider;)V')
        if 'SemFpGestureManager;->start()V' not in extension or 'SemFpGestureManager;->onHalStarted(' not in extension:
            raise ValueError('Side fingerprint gesture startup is disconnected')
        response = read(artifact, base+'aidl/SemFpAidlResponseHandler$$ExternalSyntheticLambda8.smali')
        if 'invoke-interface {v1, v5}, Lcom/android/server/biometrics/sensors/fingerprint/SemFpEventListener;->onGestureEvent(I)V' not in response:
            raise ValueError('Side fingerprint HAL gesture callback is disconnected')
        start = method(read(artifact, base+'SemFpGestureManager.smali'), 'start()V')
        for capability in ('semAddEventListener', 'registerUserSwitchObserver', 'registerContentObserver',
                           'fingerprint_gesture_quick', 'fingerprint_gesture_spay'):
            if capability not in start:
                raise ValueError('Side fingerprint gesture settings are incomplete: '+capability)


def verify(repo, work, apktool, device, mode, stage):
    if device not in DEVICES or mode not in ('fingerprint', 'wifi') or stage not in ('before', 'after'):
        raise ValueError('Unsupported S10 legacy feature migration')
    if mode == 'fingerprint' and device != 'beyond0lte':
        raise ValueError('Side fingerprint migration is only valid for S10e')
    info = manifest(repo)
    migration = info['migrations'][mode]
    for relative, expected in migration['patches'].items():
        if digest((repo/relative).read_bytes()) != expected:
            raise ValueError('Legacy feature patch differs from the reviewed migration')
    for item in migration['artifacts'].values():
        if digest((work/item['work_path']).read_bytes()) != item['source_sha256']:
            raise ValueError('Legacy feature input differs from the pinned source firmware: '+item['path'])
        check_classes(apktool/item['partition']/item['path'].removeprefix('system/'), item[stage])
    if stage == 'after':
        check_semantics(apktool, mode)
        record = dict(migration, device=device, source_firmware=info['source_firmware'], mode=mode)
        (work/(mode+'-provenance.json')).write_text(json.dumps(record, indent=2)+'\n')
    print('Verified S10 legacy feature migration:', device, mode, stage)


def output(repo, work, device, apktool):
    info = manifest(repo)
    for mode in ('wifi', 'fingerprint') if device == 'beyond0lte' else ('wifi',):
        migration = info['migrations'][mode]
        expected = dict(migration, device=device, source_firmware=info['source_firmware'], mode=mode)
        if json.loads((work/(mode+'-provenance.json')).read_text()) != expected:
            raise ValueError('Missing or changed S10 '+mode+' migration provenance')
        for item in migration['artifacts'].values():
            decoded = apktool/item['partition']/item['path'].removeprefix('system/')
            check_output_classes(decoded, item)
            artifact = work/item['work_path']
            if digest(artifact.read_bytes()) == item['source_sha256']:
                raise ValueError('Legacy feature archive was not rebuilt: '+str(artifact))
            with zipfile.ZipFile(artifact) as archive:
                dex = [archive.read(n) for n in archive.namelist() if re.fullmatch(r'classes(?:[0-9]+)?\.dex', n)]
                if not dex or archive.testzip():
                    raise ValueError('Invalid rebuilt legacy feature archive: '+str(artifact))
            for relative in item['after']:
                descriptor = ('L'+relative.removesuffix('.smali')+';').encode()+b'\0'
                if not any(descriptor in data for data in dex):
                    raise ValueError('Rebuilt legacy feature class is absent: '+relative)
        check_semantics(apktool, mode)
        print('Verified rebuilt S10 legacy feature archives:', device, mode)


if __name__ == '__main__':
    verify(Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3]), sys.argv[4], sys.argv[5], sys.argv[6])
