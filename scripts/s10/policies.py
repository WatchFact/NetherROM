#!/usr/bin/env python3
"""Keep Samsung's model-specific thermal policies and stock VINTF contract."""
import hashlib
import json
import re
import sys
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path
from installer import DEVICES

MODELS = {'beyond0lte': 'beyond0', 'beyond1lte': 'beyond1', 'beyond2lte': 'beyond2', 'beyondx': 'beyondx'}
SDHMS = 'system/priv-app/SamsungDeviceHealthManagerService/SamsungDeviceHealthManagerService.apk'
MATRIX = 'system/etc/vintf/compatibility_matrix.device.xml'


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def inputs(repo, device):
    policy = 'siop_'+MODELS[device]+'_exynos9820'
    config = (repo/'target'/device/'config.sh').read_text()
    for name, value in (('SSRM', policy), ('DVFS', 'dvfs_policy_makalu_xx')):
        if not re.search(r'^TARGET_DVFSAPP_CONFIG_'+name+r'_POLICY_FILENAME="'+re.escape(value)+r'"$', config, re.M):
            raise ValueError('Incorrect '+name+' policy selector for '+device)
    provenance = json.loads((repo/'scripts/s10/dvfs-stock.json').read_text())
    result = {}
    for name, tag in (('siop_model.xml', 'siop_document'), ('dvfs_policy_makalu_xx.xml', 'DvfsHintList')):
        relative = f'target/{device}/dvfs/{name}'
        path = repo/relative
        expected = provenance['files'][relative]
        resource = 'res/raw/'+(policy+'.xml' if name == 'siop_model.xml' else name)
        if expected['resource'] != resource or digest(path) != expected['sha256']:
            raise ValueError('Stock S10 policy changed or wrong model: '+relative)
        root = ET.parse(path).getroot()
        if root.tag != tag:
            raise ValueError('Wrong policy XML root: '+relative)
        if name == 'siop_model.xml':
            if not root.findall('modelsettings/levels/level') or not root.findall('components/component'):
                raise ValueError('Missing thermal limits: '+relative)
        result[name] = path
    return policy, result


def matrix(path):
    root = ET.parse(path).getroot()
    names = {h.findtext('name') for h in root.findall('hal')}
    required = {'android.hardware.biometrics.fingerprint', 'vendor.samsung.hardware.radio',
                'vendor.samsung_slsi.hardware.ExynosHWCServiceTW'}
    if root.tag != 'compatibility-matrix' or root.get('type') != 'framework' or not required <= names:
        raise ValueError('Missing S10 vendor contracts in '+str(path))


def record_matrix(source, work, device, firmware):
    if firmware.split('/')[0] not in DEVICES[device]:
        raise ValueError('VINTF source firmware does not match '+device)
    matrix(source)
    installed = work/'system'/MATRIX
    if digest(source) != digest(installed):
        raise ValueError('Stock VINTF requirements changed during import')
    (work/'vintf-provenance.json').write_text(json.dumps({
        'device': device, 'firmware': firmware, 'sha256': digest(source)}, indent=2)+'\n')


def output(repo, work, device):
    policy, files = inputs(repo, device)
    with zipfile.ZipFile(work/'system'/SDHMS) as z:
        expected = {
            'assets/'+policy+'.xml': files['siop_model.xml'],
            'res/raw/dvfs_policy_makalu_xx.xml': files['dvfs_policy_makalu_xx.xml'],
            'assets/siop_default.xml': repo/'unica/patches/dvfs/assets/siop_default.xml',
            'assets/ssrm_default.xml': repo/'unica/patches/dvfs/assets/ssrm_default.xml',
        }
        for name, source in expected.items():
            if z.read(name) != source.read_bytes():
                raise ValueError('SDHMS stock policy differs: '+name)
        if any(name in z.namelist() for name in ('assets/siop_default', 'assets/siop_model', 'assets/ssrm_default')):
            raise ValueError('Obsolete encrypted SDHMS policies remain')
    features = ET.parse(work/'system/system/etc/floating_feature.xml').getroot()
    if features.findtext('SEC_FLOATING_FEATURE_SYSTEM_CONFIG_SIOP_POLICY_FILENAME') != policy:
        raise ValueError('Wrong installed thermal policy selector')
    installed = work/'system'/MATRIX
    matrix(installed)
    provenance = json.loads((work/'vintf-provenance.json').read_text())
    if (provenance['device'] != device or provenance['firmware'].split('/')[0] not in DEVICES[device]
            or digest(installed) != provenance['sha256']):
        raise ValueError('Installed VINTF contract differs from target firmware')
    print('S10 stock thermal policies and VINTF contract verified:', device)


if __name__ == '__main__':
    if len(sys.argv) != 6 or sys.argv[1] != '--record-vintf':
        raise SystemExit('Usage: policies.py --record-vintf SOURCE WORK DEVICE FIRMWARE')
    record_matrix(Path(sys.argv[2]), Path(sys.argv[3]), sys.argv[4], sys.argv[5])
