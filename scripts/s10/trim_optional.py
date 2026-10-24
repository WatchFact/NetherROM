#!/usr/bin/env python3
"""Remove measured optional Samsung AI/creative payloads from S10 system tree.

Run only after all firmware patches/APK rebuilds have completed. The explicit
allowlist is intentionally narrow: no framework, kernel, vendor, system_ext,
radio, Wi-Fi, Bluetooth, NFC, camera or runtime components may be removed.
"""
import json
import os
import shutil
import sys
from pathlib import Path

# Observed in GitHub Actions run 40121852710. Names are relative to the
# physical system partition root (WORK_DIR/system).
OPTIONAL = (
    'system/priv-app/SemanticSearchCore',       # 233 MB, AI semantic search
    'system/priv-app/MediaSearch',              # 217 MB, AI media indexing
    'system/etc/mediasearch',                   # 232 MB, media search models
    'system/etc/mediacontextanalyzer',          # 239 MB, AI context models
    'system/priv-app/SamsungSmartSuggestions',  # 207 MB, suggestions
    'system/app/OCRDataProvider',               # 171 MB, optional OCR
    'system/priv-app/PhotoEditor_AIFull',       # 113 MB, generative editing
    'system/app/SketchBook',                    # 72 MB, drawing app
    'system/priv-app/AREmoji',                  # 70 MB, AR emoji
    'system/priv-app/DressRoom',                # 70 MB, avatar customization
    'system/priv-app/Routines',                 # 78 MB, routines
    'system/priv-app/LiveEffectService',        # 52 MB, optional live effects
    'system/priv-app/SamsungCloudClient',       # 77 MB, cloud sync client
    'system/priv-app/SamsungIntelliVoiceServices',  # 66 MB, AI voice extras
)
PROTECTED = (
    'system/framework/services.jar',
    'system/framework/framework.jar',
    'system/system_ext/priv-app/SystemUI/SystemUI.apk',
    'system/priv-app/SecSettings/SecSettings.apk',
    'system/priv-app/SamsungCamera/SamsungCamera.apk',
    'system/priv-app/SingleTakeService/SingleTakeService.apk',
    'system/priv-app/PhotoRemasterService/PhotoRemasterService.apk',
    'system/apex/com.android.runtime.apex',
)

def size_of(path):
    total = 0
    for parent, dirs, files in os.walk(path, followlinks=False):
        for name in files:
            item = Path(parent) / name
            if not item.is_symlink():
                total += item.stat().st_size
        for name in dirs:
            if (Path(parent) / name).is_symlink():
                raise ValueError('Symlinked optional directory: ' + str(Path(parent) / name))
    return total

def trim(work):
    work = Path(work).resolve()
    root = work / 'system'
    if not root.is_dir() or root.is_symlink():
        raise ValueError('Missing physical system partition tree')
    if len(OPTIONAL) != len(set(OPTIONAL)):
        raise ValueError('Duplicate optional path')
    for name in OPTIONAL:
        parts = Path(name).parts
        if len(parts) < 3 or parts[0] != 'system' or '..' in parts:
            raise ValueError('Unsafe optional path: ' + name)
        if any(name == p or p.startswith(name + '/') or name.startswith(p + '/')
               for p in PROTECTED):
            raise ValueError('Optional path overlaps protected component: ' + name)
    before = {name: (root / name).is_file() for name in PROTECTED}
    # Validate every target before removing any data, avoiding partial trims.
    candidates = {}
    for name in OPTIONAL:
        dest = root / name
        if not dest.exists() and not dest.is_symlink():
            continue
        if dest.is_symlink() or not dest.is_dir():
            raise ValueError('Unexpected optional payload type: ' + name)
        if any(parent.is_symlink() for parent in dest.parents if parent != root.parent):
            raise ValueError('Symlinked optional payload parent: ' + name)
        candidates[name] = size_of(dest)
    removed = {}
    for name, size in candidates.items():
        shutil.rmtree(root / name)
        removed[name] = size
        print(f'S10 optional payload removed: {name}: {size:,} bytes', flush=True)
    for name, present in before.items():
        if (root / name).is_file() != present:
            raise ValueError('Protected system component changed: ' + name)
    report = {'policy': 's10-optional-payloads-v1',
              'device': 'beyond2lte', 'removed_bytes': sum(removed.values()),
              'removed': removed}
    (work / 'optional-trim-provenance.json').write_text(
        json.dumps(report, indent=2, sort_keys=True) + '\n')
    print(f'S10 optional payload total removed: {report["removed_bytes"]:,} bytes', flush=True)
    return report

if __name__ == '__main__':
    if len(sys.argv) != 2:
        raise SystemExit('Usage: trim_optional.py WORK_DIR')
    trim(sys.argv[1])
