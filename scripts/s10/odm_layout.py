#!/usr/bin/env python3
"""Expose stock S10 vendor/odm as the physical ODM required by the pinned boot."""
import hashlib
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path
from installer import DEVICES

RECORD = 'odm-provenance.json'


def props(path):
    values = {}
    for line in path.read_text().splitlines():
        if line.strip() and not line.lstrip().startswith('#') and '=' in line:
            key, value = line.split('=', 1)
            if key in values:
                raise ValueError('Duplicate ODM property: '+key)
            values[key] = value
    return values


def identity(root, device):
    if device not in DEVICES:
        raise ValueError('Unsupported S10 ODM device')
    values = props(root/'etc/build.prop')
    if (values.get('ro.product.odm.model') not in DEVICES[device]
            or values.get('ro.product.odm.device') != device.removesuffix('lte')
            or values.get('ro.odm.build.version.sdk') != '31'):
        raise ValueError('Wrong S10 ODM hardware identity')
    return {k: v for k, v in values.items() if k.startswith(('ro.product.odm.', 'ro.odm.product.cpu.'))
            or k == 'ro.odm.build.version.sdk'}


def table(path, prefix):
    result = {}
    for line in path.read_text().splitlines():
        row = line.split()
        if row and (row[0] == prefix or row[0].startswith(prefix+'/')):
            if row[0] in result:
                raise ValueError('Duplicate ODM metadata: '+row[0])
            result[row[0]] = row[1:]
    return result


def snapshot(work, relative):
    root = work/relative
    if root.is_symlink() or not root.is_dir():
        raise ValueError('Missing real S10 ODM tree: '+relative)
    part = relative.split('/')[0]
    fs = table(work/'configs'/('fs_config-'+part), relative)
    fc = table(work/'configs'/('file_context-'+part), re.escape('/'+relative))
    entries = {}
    for p in [root, *sorted(root.rglob('*'))]:
        name = p.relative_to(root).as_posix()
        if p.is_symlink() or not (p.is_file() or p.is_dir()):
            raise ValueError('Unreviewed ODM filesystem entry: '+str(p))
        key = relative if name == '.' else relative+'/'+name
        meta = fs.get(key)
        label = fc.get(re.escape('/'+key))
        if (not meta or len(meta) != 4 or not all(v.isdigit() for v in meta[:3])
                or not re.fullmatch('[0-7]{3,4}', meta[2])
                or meta[3] != 'capabilities=0x0' or not label or len(label) != 1
                or not re.fullmatch('u:object_r:[A-Za-z0-9_]+:s0', label[0])):
            raise ValueError('Missing or invalid S10 ODM metadata: '+key)
        item = dict(type='dir' if p.is_dir() else 'file', metadata=meta, context=label[0])
        if p.is_file():
            item.update(size=p.stat().st_size, sha256=hashlib.sha256(p.read_bytes()).hexdigest())
        entries[name] = item
    if 'etc/build.prop' not in entries:
        raise ValueError('ODM tree has no native build properties')
    return entries


def validate_record(info, device, final=True):
    if (device not in DEVICES or info.get('device') != device or info.get('schema') != 1
            or info.get('origin') != 'vendor/odm' or info.get('stage') not in ('prepared', 'final')
            or (final and info['stage'] != 'final')):
        raise ValueError('Wrong S10 ODM provenance identity or stage')
    native = info.get('identity', {})
    if (native.get('ro.product.odm.model') not in DEVICES[device]
            or native.get('ro.product.odm.device') != device.removesuffix('lte')
            or native.get('ro.odm.build.version.sdk') != '31'):
        raise ValueError('Wrong packaged S10 ODM hardware identity')
    source = info.get('source', {})
    entries = info.get('output', {}) if final else source
    if (not {'.', 'etc', 'etc/build.prop'} <= entries.keys()
            or entries.keys() != source.keys()):
        raise ValueError('Incomplete S10 ODM provenance')
    for inventory in (source, entries):
        for name, item in inventory.items():
            if (name != '.' and (Path(name).is_absolute() or '..' in Path(name).parts
                                 or not re.fullmatch('[A-Za-z0-9_./-]+', name))):
                raise ValueError('Unsafe ODM provenance path')
            meta = item.get('metadata', [])
            if (item.get('type') not in ('file', 'dir') or len(meta) != 4
                    or not all(isinstance(v, str) and v.isdigit() for v in meta[:3])
                    or not re.fullmatch('[0-7]{3,4}', meta[2]) or meta[3] != 'capabilities=0x0'
                    or not re.fullmatch('u:object_r:[A-Za-z0-9_]+:s0', item.get('context', ''))):
                raise ValueError('Incomplete ODM file metadata: '+name)
            if item['type'] == 'file' and (not re.fullmatch('[0-9a-f]{64}', item.get('sha256', ''))
                                          or type(item.get('size')) is not int or item['size'] < 0):
                raise ValueError('Invalid ODM file digest: '+name)
    for name, item in entries.items():
        expected = source[name]
        if name == 'etc/build.prop':
            expected = dict(expected, size=item['size'], sha256=item['sha256'])
        if item != expected:
            raise ValueError('ODM provenance differs from stock: '+name)

    return entries


def prepare(work, device):
    record = work/RECORD
    if record.exists():
        info = json.loads(record.read_text())
        check(work, device, final=info.get('stage') == 'final')
        return
    # Do not overwrite a pre-existing partition or metadata from another job.
    if (work/'odm').exists() or (work/'odm').is_symlink() or any(
            (work/'configs'/name).exists() for name in ('fs_config-odm', 'file_context-odm')):
        raise ValueError('Unreviewed existing physical ODM output')
    native = identity(work/'vendor/odm', device)
    source = snapshot(work, 'vendor/odm')
    # e2fsdroid first requests the empty image-root path, then paths under
    # its /odm mount point. Both entries inherit the embedded directory attrs.
    fs, fc = [' '+' '.join(source['.']['metadata'])], []
    for name, item in source.items():
        path = 'odm' if name == '.' else 'odm/'+name
        fs.append(path+' '+' '.join(item['metadata']))
        fc.append(re.escape('/'+path)+' '+item['context'])
    shutil.copytree(work/'vendor/odm', work/'odm')
    (work/'configs/fs_config-odm').write_text('\n'.join(fs)+'\n')
    (work/'configs/file_context-odm').write_text('\n'.join(fc)+'\n')
    info = dict(schema=1, device=device, origin='vendor/odm', stage='prepared',
                identity=native, source=source)
    record.write_text(json.dumps(info, indent=2)+'\n')
    check(work, device, final=False)


def check(work, device, final=True):
    info = json.loads((work/RECORD).read_text())
    validate_record(info, device, final=final)
    if snapshot(work, 'vendor/odm') != info['source']:
        raise ValueError('Stock embedded ODM bytes or metadata changed')
    if identity(work/'odm', device) != info['identity']:
        raise ValueError('ODM hardware properties were changed')
    output = snapshot(work, 'odm')
    if output.keys() != info['source'].keys():
        raise ValueError('Physical ODM file inventory changed')
    for name, item in output.items():
        expected = info['source'][name]
        # ROM modules intentionally edit operational/build properties. Hardware
        # identity is separately checked; the final file digest is then frozen.
        if name == 'etc/build.prop':
            expected = dict(expected, size=item['size'], sha256=item['sha256'])
        if item != expected:
            raise ValueError('Physical ODM file or metadata differs: '+name)
    if final and output != info['output']:
        raise ValueError('Physical ODM changed after finalization')
    return info, output


def finalize(work, device):
    info = json.loads((work/RECORD).read_text())
    if info.get('stage') == 'final':
        check(work, device)
        return
    info, output = check(work, device, final=False)
    info.update(stage='final', output=output)
    (work/RECORD).write_text(json.dumps(info, indent=2)+'\n')
    check(work, device)
    print('Complete physical ODM files, hardware identity and metadata verified:', device)


def image_paths(work, device, part):
    info = json.loads((work/RECORD).read_text())
    entries = validate_record(info, device)
    prefix = 'odm/' if part == 'vendor' else ''
    return [prefix+n for n, v in entries.items() if v['type'] == 'file']


def verify_image_metadata(work, device, part, raw):
    info = json.loads((work/RECORD).read_text())
    entries = validate_record(info, device)
    for name, item in entries.items():
        prefix = '/odm' if part == 'vendor' else ''
        path = prefix if name == '.' else prefix+'/'+name
        path = path or '/'
        result = subprocess.run(['debugfs', '-R', 'stat '+path, str(raw)],
                                check=True, capture_output=True, text=True)
        text = result.stdout+result.stderr
        mode = re.search(r'Mode:\s+([0-7]+)', text)
        owner = re.search(r'User:\s+(\d+)\s+Group:\s+(\d+)', text)
        label = re.search(r'security\.selinux.*?=\s+"([^"]+)"', text)
        if (not mode or not owner or not label
                or int(mode[1], 8) != int(item['metadata'][2], 8)
                or list(map(int, owner.groups())) != list(map(int, item['metadata'][:2]))
                or label[1].removesuffix(r'\000') != item['context']
                or 'security.capability' in text):
            raise ValueError('ODM metadata differs in ext4: '+path)


if __name__ == '__main__':
    mode, work, device = sys.argv[1:]
    {'prepare': prepare, 'finalize': finalize, 'verify': check}[mode](Path(work), device)
