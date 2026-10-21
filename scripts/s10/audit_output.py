#!/usr/bin/env python3
"""Audit assembled S10 hardware and firmware before any release is created."""
import json
import re
import sys
import zipfile
from pathlib import Path

SYSTEM_FILES = (
    'system/framework/services.jar',
    'system/framework/framework.jar',
    'system/framework/semwifi-service.jar',
    'system/system_ext/priv-app/SystemUI/SystemUI.apk',
    'system/priv-app/SecSettings/SecSettings.apk',
    'system/priv-app/SettingsProvider/SettingsProvider.apk',
    'system/priv-app/SamsungDeviceHealthManagerService/SamsungDeviceHealthManagerService.apk',
    'system/etc/vintf/compatibility_matrix.device.xml',
    'system/priv-app/SamsungCamera/SamsungCamera.apk',
    'system/priv-app/SingleTakeService/SingleTakeService.apk',
    'system/priv-app/PhotoRemasterService/PhotoRemasterService.apk',
    'system/app/FilterProvider/FilterProvider.apk',
    'system/cameradata/camera-feature.xml',
    'system/lib64/libSwIsp_core.camera.samsung.so',
    'system/lib64/libeden_wrapper_system.so',
    'system/lib64/libBestComposition.polarr.so',
    'system/etc/public.libraries-polarr.txt',
    'system/lib64/libmidas_core.camera.samsung.so',
    'system/lib64/libImageTagger.camera.samsung.so',
    'system/apex/com.android.runtime.apex',
    'system/apex/com.android.i18n.apex',
    'system/apex/com.google.android.art_compressed.apex',
)
VENDOR_FILES = (
    'etc/fstab.exynos9820',
    'etc/vintf/manifest.xml',
    'etc/midas/midas_config.json',
    'etc/singletake/ClarityScorer/ClarityScorer.tflite',
    'saiv/swisp_1.0/db/denoise_model_832x1072x4_0818.pb',
    'lib64/hw/gralloc.exynos9820.so',
    'lib64/hw/hwcomposer.exynos9820.so',
    'bin/hw/android.hardware.audio.service',
    'bin/hw/rild',
    'bin/hw/wpa_supplicant',
    'lib64/libsec-ril.so',
)


def audit(work, device, apktool):
    from storage_audit import audit as storage_audit
    storage_audit(work, device)
    from camera_native import output as native_camera_output
    native_camera_output(Path(__file__).resolve().parents[2], work, device, apktool)
    from face_hidl import output as face_hidl_output
    face_hidl_output(Path(__file__).resolve().parents[2], work, device, apktool)
    from virtual_vibration import output as virtual_vibration_output
    virtual_vibration_output(Path(__file__).resolve().parents[2], work, device, apktool)
    from legacy_features import output as legacy_features_output
    legacy_features_output(Path(__file__).resolve().parents[2], work, device, apktool)
    from policies import output as policy_output
    policy_output(Path(__file__).resolve().parents[2], work, device)
    from camera_output_audit import check
    check(work)
    from camera_portrait import verify as portrait_output
    portrait_output(work, device)
    for part in ('system', 'vendor', 'product', 'odm'):
        if not (work / part).is_dir():
            raise ValueError('Missing partition: ' + part)
        for kind in ('fs_config', 'file_context'):
            if not (work / 'configs' / (kind+'-'+part)).stat().st_size:
                raise ValueError('Missing partition metadata: ' + part)
    for part, files in (('system', SYSTEM_FILES), ('vendor', VENDOR_FILES)):
        for relative in files:
            p = work / part / relative
            if not p.is_file() or not p.stat().st_size:
                raise ValueError('Missing S10 hardware output: ' + str(p))
            if p.suffix == '.so' or relative.startswith('bin/hw/'):
                h = p.read_bytes()[:20]
                if h[:4] != b'\x7fELF' or h[4] not in (1, 2) or int.from_bytes(h[18:20], 'little') not in (40, 183):
                    raise ValueError('Wrong hardware ELF ABI: ' + str(p))
            if p.suffix == '.apk':
                with zipfile.ZipFile(p) as z:
                    z.getinfo('AndroidManifest.xml')
                    if z.testzip():
                        raise ValueError('Corrupted camera APK: ' + str(p))
    fstab = (work / 'vendor/etc/fstab.exynos9820').read_text()
    for part in ('system', 'vendor', 'product', 'odm'):
        if not re.search(rf'^/dev/block/by-name/{part}\s+/{part}\s+ext4\s', fstab, re.M):
            raise ValueError('Missing physical ext4 mount: ' + part)
    if re.search(r'\blogical\b|\bavb\b|fileencryption=', fstab):
        raise ValueError('Vendor fstab does not match the S10 kernel storage path')
    if not (work / 'system/system/bin/linker').is_symlink():
        raise ValueError('Missing ARM32 runtime linker')
    info = json.loads((work / 'kernel/kernel.json').read_text())
    if info['device'] != device:
        raise ValueError('Wrong kernel device')
    print('S10 hardware output audit passed:', device)


if __name__ == '__main__':
    audit(Path(sys.argv[1]), sys.argv[2], Path(sys.argv[3]))
