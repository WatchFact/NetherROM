#!/usr/bin/env python3
"""Exercise actual SDHMS resource compilation/signing before a full S10 build."""
import argparse
import os
import shutil
import subprocess
import tempfile
import zipfile
from pathlib import Path
from installer import DEVICES
from policies import SDHMS, inputs


def run(command, **kwargs):
    result = subprocess.run(command, text=True, stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT, **kwargs)
    if result.returncode:
        raise RuntimeError('Thermal APK compilation failed:\n'+result.stdout)
    return result.stdout


def check(repo, tools, device):
    policy, files = inputs(repo, device)
    jar = tools/'bin/apktool.jar'
    with tempfile.TemporaryDirectory(prefix='s10-thermal-apk-') as td:
        root = Path(td)
        # Use the compiler and framework bundled in the SHA256-pinned toolchain.
        with zipfile.ZipFile(jar) as archive:
            (root/'aapt2').write_bytes(archive.read('prebuilt/linux/aapt2'))
            (root/'framework.apk').write_bytes(archive.read('prebuilt/android-framework.jar'))
        (root/'aapt2').chmod(0o755)
        resources = root/'input/res/raw'
        resources.mkdir(parents=True)
        assets = root/'input/assets'
        assets.mkdir()
        expected = {
            'res/raw/dvfs_policy_makalu_xx.xml': files['dvfs_policy_makalu_xx.xml'],
            'assets/'+policy+'.xml': files['siop_model.xml'],
            'assets/siop_default.xml': repo/'unica/patches/dvfs/assets/siop_default.xml',
            'assets/ssrm_default.xml': repo/'unica/patches/dvfs/assets/ssrm_default.xml',
        }
        for name, source in expected.items():
            shutil.copyfile(source, root/'input'/name)
        manifest = root/'input/AndroidManifest.xml'
        manifest.write_text('<manifest xmlns:android="http://schemas.android.com/apk/res/android" '
                            'package="com.sec.android.sdhms" android:versionCode="1">'
                            '<uses-sdk android:minSdkVersion="31" android:targetSdkVersion="36"/>'
                            '<application android:label="Thermal policy build test"/></manifest>')
        run([str(root/'aapt2'), 'compile', '--dir', str(root/'input/res'), '-o', str(root/'compiled.zip')])
        original = root/'SamsungDeviceHealthManagerService.apk'
        run([str(root/'aapt2'), 'link', '-I', str(root/'framework.apk'), '--manifest', str(manifest),
             '-A', str(assets), '-o', str(original), str(root/'compiled.zip')])
        decoded = root/'decoded'
        framework = root/'framework'
        run(['java', '-jar', str(jar), 'd', '--no-debug-info', '-p', str(framework),
             '-o', str(decoded), str(original)])
        (decoded/'original/META-INF').mkdir(parents=True, exist_ok=True)
        # A control build must reproduce the old failure with this real compiler.
        control = root/'control'
        shutil.copytree(decoded, control)
        shortened = root/'shortened.apk'
        run(['java', '-jar', str(jar), 'b', '-j', '1', '-p', str(framework), '-srp',
             '-o', str(shortened), str(control)])
        with zipfile.ZipFile(shortened) as archive:
            if 'res/raw/dvfs_policy_makalu_xx.xml' in archive.namelist():
                raise ValueError('Pinned compiler no longer reproduces resource-path shortening')
            stock = files['dvfs_policy_makalu_xx.xml'].read_bytes()
            if not any(archive.read(name) == stock for name in archive.namelist()):
                raise ValueError('Control compilation lost the stock policy bytes')

        # Execute the current production BUILD function, including real platform
        # signing. Its actual CLI flags must retain the policy paths and bytes.
        script = (repo/'scripts/apktool.sh').read_text()
        build = script[script.index('BUILD()\n'):script.index('\nDECODE()\n')]
        work = root/'work_dir'
        output = work/'system'/SDHMS
        environment = dict(os.environ, SRC_DIR=str(repo), WORK_DIR=str(work),
                           OUTPUT_PATH=str(decoded), INPUT_FILE=str(output),
                           FILE=SDHMS, PARTITION='system', TARGET_PLATFORM='exynos9820',
                           FRAMEWORK_DIR=str(framework), HEAP_SIZE='1024', THREAD_COUNT='1',
                           ROM_IS_OFFICIAL='false', PATH=str(tools/'bin')+os.pathsep+os.environ['PATH'])
        setup = '''set -eo pipefail
LOG(){ printf '%s\\n' "$*"; }
LOGE(){ printf '%s\\n' "$*" >&2; }
EVAL(){ eval "$1"; }
DELETE_FROM_WORK_DIR(){ echo 'Unexpected fixture cleanup request' >&2; return 1; }
'''
        run(['bash', '-c', setup+build+'\nBUILD\n'], env=environment)
        with zipfile.ZipFile(output) as archive:
            for name, source in expected.items():
                if archive.read(name) != source.read_bytes():
                    raise ValueError('Compiled SDHMS stock policy differs: '+name)
            if archive.testzip() or not any(name.startswith('META-INF/') and name.endswith('.RSA')
                                            for name in archive.namelist()):
                raise ValueError('Thermal APK fixture was not correctly built and signed')
        print('Actual S10 thermal APK compilation/signing preserves stock policies:', device)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo', type=Path, required=True)
    parser.add_argument('--tools', type=Path, required=True)
    parser.add_argument('--device', choices=DEVICES, required=True)
    args = parser.parse_args()
    check(args.repo.resolve(), args.tools.resolve(), args.device)
