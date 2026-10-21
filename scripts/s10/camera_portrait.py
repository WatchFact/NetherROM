#!/usr/bin/env python3
"""Keep the reviewed S10 portrait adaptation and its complete model set together."""
import hashlib
import json
import re
import sys
from pathlib import Path
from camera_path_patch import OLD, NEW
from installer import DEVICES

PORTRAIT = 'system/system/cameradata/portrait_data'
LIBRARY = 'system/system/lib64/libPortraitSolution.camera.samsung.so'
SINGLE = PORTRAIT+'/single_bokeh_feature.json'
NEXUS = PORTRAIT+'/nexus_bokeh_feature.json'
RECORD = 'camera-portrait-provenance.json'
SOURCE = 'S926BXXSHDZI1/S926BOXMHDZI1/S926BXXSHDZI1'
BACKEND_TOKENS = ('COMPUTE_GPU', 'COMPUTE_NPU', 'MODEL_TYPE_INSTANCE_CAPTURE',
                  'MODEL_TYPE_OBJ_INSTANCE_CAPTURE', 'MODEL_TYPE_SEG_LIVE')


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def check_parser(library):
    for token in BACKEND_TOKENS:
        if token.encode()+b'\0' not in library:
            raise ValueError('PortraitSolution lacks the S10 model parser contract: '+token)


def weights(value):
    if isinstance(value, dict):
        for key, item in value.items():
            if key.lower() == 'weightfile' and item is not None:
                if not isinstance(item, str) or not item.startswith(('/system/', '/vendor/')):
                    raise ValueError('Unsupported portrait model path: '+str(item))
                path = Path(item)
                if '..' in path.parts:
                    raise ValueError('Unsafe portrait model path: '+item)
                yield ('system'+item if item.startswith('/system/') else item[1:])
            else:
                yield from weights(item)
    elif isinstance(value, list):
        for item in value:
            yield from weights(item)


def model_files(work):
    original = (work/NEXUS).read_bytes()
    single = (work/SINGLE).read_bytes()
    if not isinstance(json.loads(original), dict) or not isinstance(json.loads(single), dict):
        raise ValueError('Invalid portrait feature document')
    check_native_model(json.loads(original))
    if single != original.replace(b'MODEL_TYPE_INSTANCE_CAPTURE', b'MODEL_TYPE_OBJ_INSTANCE_CAPTURE'):
        raise ValueError('S10 portrait feature adaptation was replaced')
    library = (work/LIBRARY).read_bytes()
    if not library.startswith(b'\x7fELF') or library.count(NEW) != 1 or OLD in library:
        raise ValueError('PortraitSolution does not reference the preserved nexus model')
    check_parser(library)
    files = {p.relative_to(work).as_posix() for p in (work/PORTRAIT).rglob('*') if p.is_file()}
    files.add(LIBRARY)
    for relative in (NEXUS, SINGLE):
        for name in weights(json.loads((work/relative).read_bytes())):
            p = work/name
            if not p.is_file() or not p.stat().st_size:
                raise ValueError('Missing portrait model weight: '+name)
            files.add(name)
    return {name: sha(work/name) for name in sorted(files)}


def check_native_model(document):
    if document.get('deviceName') != 'exynos9820_common':
        raise ValueError('Portrait model is not for Exynos9820')
    capture = document.get('capture_segmentation', {})
    preview = document.get('preview_1st_segmentation', {})
    if (capture.get('ComputeUnit') != 'COMPUTE_GPU' or capture.get('ModelFormat') != 'SNF'
            or capture.get('ModelType') != 'MODEL_TYPE_INSTANCE_CAPTURE'
            or preview.get('ComputeUnit') != 'COMPUTE_NPU' or preview.get('ModelFormat') != 'EDEN'):
        raise ValueError('Unreviewed S10 portrait model backend')
    for path in weights(document):
        if re.search(r'ex(?:ynos)?2400|\.nnc$', path, re.I):
            raise ValueError('Exynos2400 model cannot run on the S10 NPU: '+path)


def validate_record(info, device):
    if (device not in DEVICES or info.get('device') != device or info.get('schema') != 2
            or info.get('source_firmware') != SOURCE):
        raise ValueError('Wrong S10 portrait provenance identity')
    target = info.get('model_firmware', {})
    if (target.get('model') not in DEVICES[device] or not target.get('version')
            or info.get('native_device_name') != 'exynos9820_common'):
        raise ValueError('Wrong S10 portrait model firmware identity')
    files = info.get('files', {})
    if not {SINGLE, NEXUS, LIBRARY} <= files.keys():
        raise ValueError('Incomplete S10 portrait provenance')
    for name, value in files.items():
        if (not name.startswith(('system/system/', 'vendor/')) or '..' in Path(name).parts
                or not re.fullmatch('[0-9a-f]{64}', value)):
            raise ValueError('Invalid S10 portrait digest entry: '+name)
    return files


def inputs(source, target, device):
    if (source/'.extracted').read_text().strip() != SOURCE:
        raise ValueError('Unreviewed portrait source firmware')
    model = target.name.split('_')[0]
    version = (target/'.extracted').read_text().strip()
    if device not in DEVICES or model not in DEVICES[device] or not version:
        raise ValueError('Wrong S10 portrait input firmware')
    document = json.loads((target/SINGLE).read_bytes())
    check_native_model(document)
    for name in weights(document):
        if not (target/name).is_file() or not (target/name).stat().st_size:
            raise ValueError('Missing stock S10 portrait weight: '+name)
    library = (source/LIBRARY).read_bytes()
    if not library.startswith(b'\x7fELF') or library.count(OLD) != 1 or NEW in library:
        raise ValueError('Unreviewed PortraitSolution source binary')
    check_parser(library)
    print('Stock S10 portrait weights and pinned source parser verified:', device)
    return dict(model=model, version=version)


def record(work, device, source, target):
    firmware = inputs(source, target, device)
    original = (target/SINGLE).read_bytes()
    if (work/NEXUS).read_bytes() != original:
        raise ValueError('Nexus portrait feature differs from pristine S10 firmware')
    # Preserve all stock S10 weights, including models referenced indirectly by
    # native code. Only single_bokeh's established enum substitution may differ.
    expected = {}
    for path in (target/PORTRAIT).rglob('*'):
        if path.is_file():
            name = path.relative_to(target).as_posix()
            data = path.read_bytes()
            if name == SINGLE:
                data = data.replace(b'MODEL_TYPE_INSTANCE_CAPTURE', b'MODEL_TYPE_OBJ_INSTANCE_CAPTURE')
            expected[name] = hashlib.sha256(data).hexdigest()
    expected[NEXUS] = hashlib.sha256(original).hexdigest()
    actual = model_files(work)
    actual_portrait = {n: s for n, s in actual.items() if n.startswith(PORTRAIT+'/')}
    if actual_portrait != expected:
        raise ValueError('S10 portrait model set differs from pristine S10 firmware')
    for name in actual:
        if name.startswith('vendor/') and sha(work/name) != sha(target/name):
            raise ValueError('Vendor portrait model differs from pristine S10 firmware: '+name)
    library = (source/LIBRARY).read_bytes()
    if library.count(OLD) != 1 or NEW in library or (work/LIBRARY).read_bytes() != library.replace(OLD, NEW, 1):
        raise ValueError('Unreviewed PortraitSolution binary adaptation')
    info = dict(schema=2, device=device, source_firmware=SOURCE, files=actual,
                native_device_name='exynos9820_common', model_firmware=firmware)
    validate_record(info, device)
    (work/RECORD).write_text(json.dumps(info, indent=2)+'\n')
    verify(work, device)


def verify(work, device):
    expected = validate_record(json.loads((work/RECORD).read_text()), device)
    if model_files(work) != expected:
        raise ValueError('Portrait files changed after the reviewed S10 camera adaptation')
    print('S10 portrait model set and exact library adaptation verified:', device)


if __name__ == '__main__':
    mode, work, device = sys.argv[1:4]
    if mode == 'record':
        record(Path(work), device, Path(sys.argv[4]), Path(sys.argv[5]))
    elif mode == 'verify':
        verify(Path(work), device)
    else:
        raise ValueError('Unknown portrait audit mode: '+mode)
