#!/usr/bin/env python3
"""Verify the original S10 camera before retaining its native legacy APIs."""
import hashlib
import json
import re
import sys
import zipfile
from pathlib import Path
from installer import DEVICES

CAMERA = 'system/priv-app/SamsungCamera/SamsungCamera.apk'


def manifest(repo):
    return json.loads((repo/'scripts/s10/camera-native-v3.1.0.json').read_text())


def check_classes(decoded, classes):
    for relative, expected in classes.items():
        matches = [p for p in decoded.glob('smali*/'+relative)
                   if re.fullmatch(r'smali(?:_classes[0-9]+)?', p.relative_to(decoded).parts[0])]
        if len(matches) != 1:
            raise ValueError('Missing or ambiguous legacy camera class: '+relative)
        data = matches[0].read_bytes()
        descriptor = 'L'+relative.removesuffix('.smali')+';'
        if not re.search(rb'^\.class (?:[^\n]* )?'+re.escape(descriptor.encode())+rb'$', data, re.M):
            raise ValueError('Wrong camera class descriptor: '+relative)
        if hashlib.sha256(data).hexdigest() != expected:
            raise ValueError('Unreviewed camera implementation: '+relative)


def check_encoders(decoded, info):
    check_classes(decoded, info['encoder_classes'])
    for item in info['encoder_methods']:
        path = next(decoded.glob('smali*/'+item['class']))
        text = path.read_text()
        methods = re.findall(r'^\.method [^\n]* '+re.escape(item['method'])+
                             r'\n(.*?)^\.end method$', text, re.M | re.S)
        if len(methods) != 1 or any(token not in methods[0] for token in item['requires']):
            raise ValueError('Incompatible native camera encoder: '+item['class']+' '+item['method'])
    for path in decoded.glob('smali*/**/*.smali'):
        data = path.read_bytes()
        if (b'Lcom/samsung/android/sum/core/filter/EncoderFilter;' in data
                or re.search(rb'\b0x7f420888\b', data, re.I)):
            raise ValueError('Modern camera encoder is incompatible with the pinned donor: '+str(path))


def verify(repo, work, decoded, device):
    if device not in DEVICES:
        raise ValueError('Unsupported S10 camera target')
    info = manifest(repo)
    for path in (repo/info['apk'], work/'system'/CAMERA):
        if hashlib.sha256(path.read_bytes()).hexdigest() != info['apk_sha256']:
            raise ValueError('The selected camera is not the pinned 3.1.0 S10 donor')
    check_classes(decoded, info['classes'])
    check_encoders(decoded, info)
    record = dict(info, device=device, mode='native-legacy-camera')
    (work/'camera-compatibility.json').write_text(json.dumps(record, indent=2)+'\n')
    print('Verified original S10 SceneDetection, SecondPicture and OMX surface encoders:', device)


def output(repo, work, device, apktool):
    info = manifest(repo)
    record = json.loads((work/'camera-compatibility.json').read_text())
    if record != dict(info, device=device, mode='native-legacy-camera'):
        raise ValueError('Missing or changed camera compatibility provenance')
    check_encoders(apktool/'system/priv-app/SamsungCamera/SamsungCamera.apk', info)
    with zipfile.ZipFile(work/'system'/CAMERA) as z:
        dex = [z.read(n) for n in z.namelist() if re.fullmatch(r'classes(?:[0-9]+)?\.dex', n)]
    strings = ['L'+n.removesuffix('.smali')+';' for n in (*info['classes'], *info['encoder_classes'])]
    strings += ['sendTextDetectionInfoCallback', 'onSceneDetectionEvent',
                'isSecondPictureConfigSupported', 'samsung.android.control.sceneDetectionInfo',
                'samsung.android.control.textDetectionInfo']
    for value in strings:
        if not any(value.encode()+b'\0' in data for data in dex):
            raise ValueError('Legacy camera API missing from rebuilt APK: '+value)
    if any(b'Lcom/samsung/android/sum/core/filter/EncoderFilter;\0' in data for data in dex):
        raise ValueError('Rebuilt S10 camera contains the modern SUM encoder')
    print('Rebuilt APK retains the reviewed S10 camera APIs:', device)


if __name__ == '__main__':
    verify(Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3]), sys.argv[4])
