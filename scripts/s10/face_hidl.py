#!/usr/bin/env python3
"""Guard the source-specific S10 face HIDL 2.0 migration and rebuilt JAR."""
import hashlib
import json
import re
import sys
import zipfile
from pathlib import Path
from installer import DEVICES

JAR = 'system/framework/services.jar'
V3 = (b'vendor/samsung/hardware/biometrics/face/V3_0/',
      b'vendor.samsung.hardware.biometrics.face@3.0::')


def manifest(repo):
    return json.loads((repo/'scripts/s10/face-hidl-v4.0.1.json').read_text())


def check_classes(decoded, expected):
    for relative, digest in expected.items():
        matches = list(decoded.glob('smali*/'+relative))
        if digest is None:
            if matches:
                raise ValueError('Obsolete face HAL class remains: '+relative)
            continue
        if len(matches) != 1:
            raise ValueError('Missing or ambiguous face HAL class: '+relative)
        data = matches[0].read_bytes()
        descriptor = ('L'+relative.removesuffix('.smali')+';').encode()
        if not re.search(rb'^\.class (?:[^\n]* )?'+re.escape(descriptor)+rb'$', data, re.M):
            raise ValueError('Wrong face HAL class descriptor: '+relative)
        if hashlib.sha256(data).hexdigest() != digest:
            raise ValueError('Unreviewed face HAL implementation: '+relative)


def verify(repo, work, decoded, device, stage):
    if device not in DEVICES or stage not in ('before', 'after'):
        raise ValueError('Unsupported S10 face HAL migration')
    info = manifest(repo)
    patch = repo/info['patch']
    if hashlib.sha256(patch.read_bytes()).hexdigest() != info['patch_sha256']:
        raise ValueError('Face HAL patch differs from the reviewed migration')
    if hashlib.sha256((work/'system'/JAR).read_bytes()).hexdigest() != info['source_jar_sha256']:
        raise ValueError('Face HAL input is not the pinned source framework')
    check_classes(decoded, info[stage])
    if stage == 'after':
        check_no_v3(decoded)
        check_contracts(decoded)
        record = dict(info, device=device, mode='hidl-2.0')
        (work/'face-hidl-provenance.json').write_text(json.dumps(record, indent=2)+'\n')
    print('Verified S10 face HIDL 2.0 migration:', device, stage)


def check_no_v3(decoded):
    for path in decoded.glob('smali*/**/*.smali'):
        if any(value in path.read_bytes() for value in V3):
            raise ValueError('HIDL 3.0 face reference remains: '+str(path))


def check_contracts(decoded):
    classes = {}
    for path in decoded.glob('smali*/**/*.smali'):
        if not any(name in path.as_posix() for name in
                   ('/biometrics/face/', '/sensors/face/', '/android/hidl/base/')):
            continue
        text = path.read_text()
        descriptor = re.search(r'^\.class .* (L[^;]+;)$', text, re.M)[1]
        if descriptor in classes:
            raise ValueError('Duplicate face HAL type: '+descriptor)
        methods = {m[2]: m[1] for m in re.finditer(r'^\.method (.*?)(\S+\([^\n]*)$', text, re.M)}
        bases = re.findall(r'^\.(?:super|implements) (L[^;]+;)$', text, re.M)
        classes[descriptor] = methods, bases, text

    def abstract_methods(descriptor):
        if descriptor not in classes:
            return set()
        methods, bases, _ = classes[descriptor]
        result = {name for name, flags in methods.items() if 'abstract' in flags.split()}
        for base in bases:
            result.update(abstract_methods(base))
        return result

    implementations = (
        'vendor/samsung/hardware/biometrics/face/V2_0/ISehBiometricsFace$Proxy',
        'vendor/samsung/hardware/biometrics/face/V2_0/ISehBiometricsFaceClientCallback$Proxy',
        'com/android/server/biometrics/sensors/face/hidl/TestHal',
        'com/android/server/biometrics/sensors/face/hidl/HidlToAidlCallbackConverter',
    )
    for name in implementations:
        methods, bases, _ = classes['L'+name+';']
        expected = set().union(*(abstract_methods(base) for base in bases))
        missing = expected - set(methods)
        if missing:
            raise ValueError('Incomplete face HAL contract: '+name+' '+str(sorted(missing)))
    for _, _, text in classes.values():
        for descriptor in re.findall(r'Lvendor/samsung/hardware/biometrics/face/[^;\s]+;', text):
            if descriptor not in classes:
                raise ValueError('Unresolved face HAL type: '+descriptor)
    for name, count in (('TestHal', 34), ('HidlToAidlCallbackConverter', 10)):
        _, _, text = classes['Lcom/android/server/biometrics/sensors/face/hidl/'+name+';']
        table = re.search(r'\.packed-switch 0x1\n(.*?)\.end packed-switch', text, re.S)[1]
        if len(re.findall(r':pswitch_[0-9a-f]+', table)) != count:
            raise ValueError('Wrong HIDL 2.0 transaction table: '+name)
        method = re.search(r'\.method[^\n]* getHashChain\(\).*?\.end method', text, re.S)[0]
        if len(re.findall(r'\.array-data 1\n', method)) != 3:
            raise ValueError('Wrong HIDL 2.0 interface hash chain: '+name)


def output(repo, work, device, apktool):
    info = manifest(repo)
    record = json.loads((work/'face-hidl-provenance.json').read_text())
    if record != dict(info, device=device, mode='hidl-2.0'):
        raise ValueError('Missing or changed S10 face HAL migration provenance')
    decoded = apktool/'system/framework/services.jar'
    check_classes(decoded, info['after'])
    check_no_v3(decoded)
    check_contracts(decoded)
    with zipfile.ZipFile(work/'system'/JAR) as z:
        dex = [z.read(n) for n in z.namelist() if re.fullmatch(r'classes(?:[0-9]+)?\.dex', n)]
        if not dex or z.testzip():
            raise ValueError('Invalid rebuilt services.jar')
    for relative, digest in info['after'].items():
        descriptor = ('L'+relative.removesuffix('.smali')+';').encode()+b'\0'
        present = any(descriptor in data for data in dex)
        if present != (digest is not None):
            raise ValueError('Rebuilt face HAL class mismatch: '+relative)
    if any(value in data for value in V3 for data in dex):
        raise ValueError('Rebuilt services.jar retains HIDL 3.0 face references')
    print('Rebuilt framework retains the reviewed S10 HIDL 2.0 migration:', device)


if __name__ == '__main__':
    verify(Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3]), sys.argv[4], sys.argv[5])
