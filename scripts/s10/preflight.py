#!/usr/bin/env python3
"""Check complete hardware inventory and all declared firmware imports."""
import argparse
import json
import re
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path
from policies import inputs as policy_inputs, matrix as check_matrix

ROOT = Path(__file__).resolve().parents[2]
DEVICES = ('beyond0lte', 'beyond1lte', 'beyond2lte', 'beyondx')


def index():
    entries = {}
    for row in subprocess.check_output(['git', 'ls-files', '--stage'], cwd=ROOT, text=True).splitlines():
        info, path = row.split('\t', 1)
        entries[path] = info.split()[1]
    return entries


def contains(entries, relative):
    if relative in entries or relative+'.00' in entries:
        return True
    return any(p.startswith(relative.rstrip('/')+'/') for p in entries)


def declared_imports(text):
    text = text.replace('\\\n', ' ')
    pattern = r'ADD_TO_WORK_DIR\s+"([^"\n]+)"\s+"([^"\n]+)"\s+"([^"\n]+)"'
    for donor, part, name in re.findall(pattern, text):
        if '$' not in name:
            yield donor, part, name
    for values, body in re.findall(r'BLOBS_LIST="(.*?)"\s*for\s+blob\s+in\s+\$BLOBS_LIST\s*do\s*(.*?)\s*done', text, re.S):
        for donor, part, name in re.findall(pattern, body):
            if name == '$blob':
                for name in values.split():
                    yield donor, part, name
    # Explicit rules for the multilib bridge's dynamic import loops.
    for var, donor in (('RUNTIME_LIBS', 'r11sxxx'), ('LEGACY_AUDIO_LIBS', '$TARGET_FIRMWARE')):
        m = re.search(r'(?m)^'+var+r'="\s*\n(.*?)\n"', text, re.S)
        if m:
            for name in m.group(1).split():
                yield donor, 'system', 'system/lib/'+name
    for var in ('RUNTIME_APEX', 'I18N_APEX', 'ART_APEX'):
        m = re.search(r'(?m)^'+var+r'="([^"]+)"', text)
        if m:
            yield ('m35xxx' if var == 'RUNTIME_APEX' else 'r11sxxx'), 'system', m.group(1)


def audit(device, firmware=False):
    entries = index()
    lock = json.loads((ROOT/'scripts/s10/hardware-lock.json').read_text())
    for path, sha in lock['files'].items():
        if entries.get(path) != sha:
            raise ValueError('Missing or changed hardware input: '+path)
    if len(lock['files']) < 380:
        raise ValueError('Hardware inventory is incomplete')
    for d in DEVICES:
        policy_inputs(ROOT, d)
        root = ET.parse(ROOT/'target'/d/'camera/camera-feature.xml').getroot()
        modes = [e.get('name') for e in root if e.get('name','').startswith('SHOOTING_MODE_')]
        if root.tag != 'resources' or len(modes) != len(set(modes)) or 'SHOOTING_MODE_PHOTO' not in modes or 'SHOOTING_MODE_VIDEO' not in modes:
            raise ValueError('Invalid camera modes for '+d)
    if firmware:
        model, region = __import__('os').environ['TARGET_FIRMWARE'].split('/')[:2]
        check_matrix(ROOT/'out/fw'/f'{model}_{region}'/'system/system/etc/vintf/compatibility_matrix.device.xml')
    count = 0
    for script in sorted((ROOT/'platform/exynos9820/patches').glob('*/customize.sh')):
        module = script.parent.name
        if module == 'hrm' and device in ('beyond0lte','beyondx'):
            continue
        text = script.read_text()
        if '$SOURCE_CODENAME' in text:
            raise ValueError('Undefined legacy SOURCE_CODENAME: '+str(script))
        for donor, part, name in declared_imports(text):
            if part == 'system':
                name = name.removeprefix('system/')
            if donor.startswith('$'):
                if not firmware:
                    continue
                if donor != '$TARGET_FIRMWARE':
                    raise ValueError('Unreviewed firmware import: '+donor)
                if device == 'beyondx' and re.search(r'cover\.(flip|ledbackcover|nfcledcover)\.xml$', name):
                    continue
                model, region = __import__('os').environ['TARGET_FIRMWARE'].split('/')[:2]
                base = ROOT/'out/fw'/f'{model}_{region}'
                p = base/part/('system' if part=='system' else '')/name
                if not p.exists():
                    raise ValueError('Missing stock firmware dependency: '+str(p))
            else:
                relative = f'prebuilts/samsung/{donor}/{part}/{name}'.rstrip('/')
                if not contains(entries, relative):
                    raise ValueError(f'{module}: missing donor dependency {relative}')
            count += 1
    print(f'S10 {device}: {len(lock["files"])} locked hardware files; {count} imports checked')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--device', required=True, choices=DEVICES)
    parser.add_argument('--firmware', action='store_true')
    args = parser.parse_args()
    audit(args.device, args.firmware)
