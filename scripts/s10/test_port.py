#!/usr/bin/env python3
"""Regressions for physical installation, kernel integrity and model migration."""
import hashlib
import gzip
import json
import struct
import subprocess
import tempfile
import unittest
import zipfile
from pathlib import Path
from installer import BUDGET, DEVICES, generate
from kernel_artifacts import KERNEL_REV, install
from validate_midas import verify
from optional_binary_patch import PATCHES, patch
from policies import inputs as policy_inputs, output as policy_output, record_matrix, MATRIX, SDHMS
from camera_native import check_classes, check_encoders
from storage_audit import boot_fstab, check_fstab
from verify_zip import verify as verify_zip
from virtual_vibration import check_backend, digest, FIELD, HELPER, MANAGER, BOOT


class PortTests(unittest.TestCase):
    def test_portrait_models_survive_actual_platform_and_generic_camera_stages(self):
        import shutil
        from camera_portrait import PORTRAIT, LIBRARY, NEXUS, SINGLE, RECORD, SOURCE, verify as portrait_verify
        from camera_path_patch import OLD, NEW
        repo = Path(__file__).resolve().parents[2]
        platform = (repo/'platform/exynos9820/patches/camera/customize.sh').read_text()
        platform = platform[platform.index('LOG_STEP_IN "- Fixing AI Photo Editor"'):
                            platform.index('LOG_STEP_IN "- Adding S21 FE', platform.index('LOG_STEP_IN "- Fixing AI Photo Editor"'))]
        generic = (repo/'unica/patches/camera/customize.sh').read_text()
        generic = generic[generic.index('if [[ "$TARGET_PLATFORM" == exynos9820 ]]; then'):
                          generic.index('if [ -f "$SRC_DIR/target/$TARGET_CODENAME/camera/singletake/')]
        for device in DEVICES:
            with self.subTest(device=device), tempfile.TemporaryDirectory() as td:
                root = Path(td); work = root/'work'; fw = root/'fw'
                source = fw/'SM-S926B_EUX'
                (source/PORTRAIT).mkdir(parents=True)
                (source/'.extracted').write_text(SOURCE)
                model = {'capture_segmentation': {
                    'Weightfile': '/system/cameradata/portrait_data/donor.snf',
                    'ModelType': 'MODEL_TYPE_INSTANCE_CAPTURE'}}
                (source/SINGLE).write_text(json.dumps(model))
                (source/PORTRAIT/'donor.snf').write_bytes(b'original donor model weights')
                (source/LIBRARY).parent.mkdir(parents=True)
                (source/LIBRARY).write_bytes(b'\x7fELF'+b'\0'*64+OLD+b'\0unrelated native code')
                shutil.copytree(source, work)
                script = '''set -eo pipefail
SRC_DIR="$1"; WORK_DIR="$2"; FW_DIR="$3"; TARGET_CODENAME="$4"
SOURCE_FIRMWARE=SM-S926B/EUX/350330051234562; TARGET_PLATFORM=exynos9820
LOG_STEP_IN(){ :; }; LOG_STEP_OUT(){ :; }
SET_METADATA(){ printf '%s\\n' "$*" > "$WORK_DIR/metadata"; }
DELETE_FROM_WORK_DIR(){ echo 'generic camera deleted S10 models' >&2; exit 90; }
ADD_TO_WORK_DIR(){ echo 'generic camera replaced S10 models' >&2; exit 91; }
'''+platform+generic
                subprocess.run(['bash', '-c', script, '--', str(repo), str(work), str(fw), device],
                               check=True, capture_output=True, text=True)
                portrait_verify(work, device)
                self.assertEqual((work/NEXUS).read_bytes(), (source/SINGLE).read_bytes())
                self.assertIn('system/cameradata/portrait_data/nexus_bokeh_feature.json 0 0 644',
                              (work/'metadata').read_text())
                self.assertEqual((work/LIBRARY).read_bytes(), (source/LIBRARY).read_bytes().replace(OLD, NEW, 1))
                for path in (NEXUS, PORTRAIT+'/donor.snf', LIBRARY, SINGLE):
                    saved = (work/path).read_bytes()
                    (work/path).unlink()
                    with self.assertRaises((ValueError, FileNotFoundError)):
                        portrait_verify(work, device)
                    (work/path).write_bytes(saved+b'changed')
                    with self.assertRaises((ValueError, json.JSONDecodeError)):
                        portrait_verify(work, device)
                    (work/path).write_bytes(saved)
                info = json.loads((work/RECORD).read_text())
                info['device'] = 'wrong-device'
                (work/RECORD).write_text(json.dumps(info))
                with self.assertRaisesRegex(ValueError, 'identity'):
                    portrait_verify(work, device)
                # Other platforms still execute the original stock import.
                stock = root/'stock'; stock.mkdir()
                (stock/'single_bokeh_feature.json').write_bytes(b'stock target camera data')
                other = '''set -e
SRC_DIR="$1"; WORK_DIR="$2"; TARGET_PLATFORM=exynos990; STOCK="$3"
DELETE_FROM_WORK_DIR(){ rm -rf "$WORK_DIR/$1/$2"; }
ADD_TO_WORK_DIR(){ cp -a "$STOCK" "$WORK_DIR/$2/$3"; }
'''+generic
                subprocess.run(['bash', '-c', other, '--', str(repo), str(work), str(stock)],
                               check=True, capture_output=True, text=True)
                self.assertFalse((work/NEXUS).exists())
                self.assertEqual((work/SINGLE).read_bytes(), b'stock target camera data')

    def test_smali_method_selection_handles_large_classes_and_array_signatures(self):
        repo = Path(__file__).resolve().parents[2]
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            path = root/'system/framework/service.jar/smali/com/example/Large.smali'
            path.parent.mkdir(parents=True)
            methods = ''.join('.method public longMethodName'+str(n)+'()I\n'
                              '    .locals 1\n    const/4 v0, 0x0\n    return v0\n.end method\n'
                              for n in range(2000))
            selected = ('.method public values()[I\n    .locals 1\n    const/4 v0, 0x0\n'
                        '    new-array v0, v0, [I\n    return-object v0\n.end method\n')
            reference = ('# invoke-virtual {p0}, Lcom/example/Large;->missing()[I\n')
            path.write_text('.class public Lcom/example/Large;\n.super Ljava/lang/Object;\n'+methods+selected+reference)
            script = '''set -eo pipefail
SRC_DIR="$1"; APKTOOL_DIR="$2"
source "$SRC_DIR/scripts/utils/module_utils.sh"
DECODE_APK(){ return 0; }
EVAL(){ eval "$1"; }
SMALI_PATCH system system/framework/service.jar smali/com/example/Large.smali replace "$3" 'const/4 v0, 0x0' 'const/4 v0, 0x1'
'''
            result = subprocess.run(['bash', '-c', script, '--', str(repo), str(root), 'values()[I'],
                                    capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn(methods, path.read_text())
            self.assertIn(selected.replace('const/4 v0, 0x0', 'const/4 v0, 0x1'), path.read_text())
            missing = subprocess.run(['bash', '-c', script, '--', str(repo), str(root), 'missing()[I'],
                                     capture_output=True, text=True)
            self.assertNotEqual(missing.returncode, 0)
            self.assertIn('Method "missing()[I" not found', missing.stderr)
            # Whole-class replacement has no method argument or declaration.
            # It must not enter the declaration check or search for an empty name.
            path.write_text(path.read_text()+'# UNIQUE_BEFORE\n')
            whole_class = script[:script.index('SMALI_PATCH system')] + (
                'SMALI_PATCH system system/framework/service.jar '
                'smali/com/example/Large.smali replaceall UNIQUE_BEFORE UNIQUE_AFTER\n')
            replaced = subprocess.run(['bash', '-c', whole_class, '--', str(repo), str(root)],
                                      capture_output=True, text=True)
            self.assertEqual(replaced.returncode, 0, replaced.stderr)
            self.assertIn('# UNIQUE_AFTER', path.read_text())

    def test_legacy_feature_guards_check_source_patch_and_real_decode_roots(self):
        from legacy_features import verify as legacy_verify
        repo_path = Path(__file__).resolve().parents[2]
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            repo, work, apktool = root/'repo', root/'out/work_dir', root/'out/apktool'
            artifact = 'priv-app/SystemUI/SystemUI.apk'
            name = 'com/example/PowerButton.smali'
            original = b'.class public Lcom/example/PowerButton;\n.super Ljava/lang/Object;\n'
            actual = apktool/'system_ext'/artifact/'smali_classes4'/name
            actual.parent.mkdir(parents=True)
            actual.write_bytes(original)
            # Execute apktool.sh's actual physical partition mapping. S10
            # merges system_ext in system, while its decode cache stays separate.
            import re
            prepare = (repo_path/'scripts/apktool.sh').read_text()
            mapping = prepare[prepare.index('    local FILE_PATH="$WORK_DIR"'):
                              prepare.index('    OUTPUT_PATH="$APKTOOL_DIR/')]
            result = subprocess.check_output(['bash', '-c',
                'WORK_DIR="$1"; PARTITION=system_ext; FILE="$2"; '
                'TARGET_OS_BUILD_SYSTEM_EXT_PARTITION=false; '
                'prepare(){ '+mapping.rstrip()+'; printf "%s" "$INPUT_FILE"; }; prepare',
                '--', str(work), artifact], text=True)
            archive = Path(result)
            self.assertEqual(archive.relative_to(work).as_posix(),
                             'system/system/system_ext/'+artifact)
            archive.parent.mkdir(parents=True)
            archive.write_bytes(b'pinned source APK')
            patch = repo/'migration.patch'
            patch.parent.mkdir(parents=True)
            patch.write_bytes(b'reviewed patch')
            info = {'source_firmware': 'pinned', 'migrations': {'fingerprint': {
                'patches': {'migration.patch': digest(patch.read_bytes())},
                'artifacts': {'SystemUI.apk': {'partition': 'system_ext', 'path': artifact,
                    'source_sha256': digest(archive.read_bytes()),
                    'work_path': archive.relative_to(work).as_posix(),
                    'before': {name: digest(original)}}}}}}
            lock = repo/'scripts/s10/legacy-features-v4.0.1.json'
            lock.parent.mkdir(parents=True)
            lock.write_text(json.dumps(info))
            legacy_verify(repo, work, apktool, 'beyond0lte', 'fingerprint', 'before')
            with self.assertRaisesRegex(ValueError, 'only valid for S10e'):
                legacy_verify(repo, work, apktool, 'beyond2lte', 'fingerprint', 'before')
            patch.write_bytes(b'unreviewed patch')
            with self.assertRaisesRegex(ValueError, 'patch differs'):
                legacy_verify(repo, work, apktool, 'beyond0lte', 'fingerprint', 'before')
            patch.write_bytes(b'reviewed patch')
            archive.write_bytes(b'different source APK')
            with self.assertRaisesRegex(ValueError, 'pinned source firmware'):
                legacy_verify(repo, work, apktool, 'beyond0lte', 'fingerprint', 'before')
            archive.write_bytes(b'pinned source APK')
            actual.write_bytes(original+b'# changed callback\n')
            with self.assertRaisesRegex(ValueError, 'Unreviewed'):
                legacy_verify(repo, work, apktool, 'beyond0lte', 'fingerprint', 'before')
            actual.write_bytes(original)
            duplicate = apktool/'system_ext'/artifact/'smali'/name
            duplicate.parent.mkdir(parents=True)
            duplicate.write_bytes(original)
            with self.assertRaisesRegex(ValueError, 'ambiguous'):
                legacy_verify(repo, work, apktool, 'beyond0lte', 'fingerprint', 'before')
            duplicate.unlink()
            stale = work/'apktool/system_ext'/artifact/'smali'/name
            stale.parent.mkdir(parents=True)
            stale.write_bytes(original)
            actual.unlink()
            with self.assertRaisesRegex(ValueError, 'ambiguous'):
                legacy_verify(repo, work, apktool, 'beyond0lte', 'fingerprint', 'before')

    def test_fingerprint_flags_reject_reassignment_and_sensor_type_drift(self):
        from legacy_features import check_output_classes, method as legacy_method
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            name = 'com/example/Hardware.smali'
            path = root/'smali_classes2'/name
            path.parent.mkdir(parents=True)
            text = '''.class public Lcom/example/Hardware;
.super Ljava/lang/Object;
.method static constructor <clinit>()V
    .locals 19
    const/16 v18, 0x0
    const-string v1, "3"
    sput-boolean v18, Lcom/example/Hardware;->IN_DISPLAY:Z
    return-void
.end method
.method public static sensorType()I
    .locals 1
    const/4 v0, 0x4
    return v0
.end method
'''
            item = {'output': {}, 'output_methods': {name: {
                'sensorType()I': digest(legacy_method(text, 'sensorType()I').encode())}},
                'field_constants': {name: {'IN_DISPLAY': {'register': 'v18', 'value': '0x0'}}}}
            path.write_text(text)
            check_output_classes(root, item)
            # HFR adapts an unrelated literal in the same shared initializer.
            path.write_text(text.replace('"3"', '"0"'))
            check_output_classes(root, item)
            path.write_text(text.replace('    return-void', '    const/16 v18, 0x1\n    return-void'))
            with self.assertRaisesRegex(ValueError, 'register is overwritten'):
                check_output_classes(root, item)
            path.write_text(text.replace('sput-boolean v18', 'sput-boolean v1'))
            with self.assertRaisesRegex(ValueError, 'hardware flag'):
                check_output_classes(root, item)
            path.write_text(text.replace('const/4 v0, 0x4', 'const/4 v0, 0x2'))
            with self.assertRaisesRegex(ValueError, 'Changed legacy feature method'):
                check_output_classes(root, item)

    def test_virtual_migration_cli_uses_explicit_buildenv_decode_directory(self):
        import re
        import sys
        repo = Path(__file__).resolve().parents[2]
        exports = '\n'.join(re.findall(r'^export (?:APKTOOL_DIR|WORK_DIR)=.*$',
                                     (repo/'buildenv.sh').read_text(), re.M))
        self.assertEqual(len(exports.splitlines()), 2)
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            # Execute the actual buildenv assignments, rather than assuming a
            # fixture layout that differs from GitHub Actions.
            result = subprocess.check_output(['bash', '-c',
                'OUT_DIR="$1"; SELECTED_TARGET=beyond2lte; '+exports+
                '; printf "%s\\n%s\\n" "$WORK_DIR" "$APKTOOL_DIR"',
                '--', str(root/'out')], text=True).splitlines()
            work, decoded = map(Path, result)
            self.assertNotEqual(decoded, work/'apktool')
            relative = 'system/framework/services.jar'
            name = 'com/example/Reviewed.smali'
            original = b'.class public Lcom/example/Reviewed;\n.super Ljava/lang/Object;\n'
            archive = work/'system'/relative
            archive.parent.mkdir(parents=True)
            archive.write_bytes(b'pinned input')
            good = decoded/relative/'smali'/name
            good.parent.mkdir(parents=True)
            good.write_bytes(original)
            stale = work/'apktool'/relative/'smali'/name
            stale.parent.mkdir(parents=True)
            stale.write_bytes(b'stale decoded class')
            fixture = root/'repo/scripts/s10'
            fixture.mkdir(parents=True)
            (fixture/'virtual-vibration-v4.0.1.json').write_text(json.dumps({
                'artifacts': {relative: {'source_sha256': digest(archive.read_bytes()),
                                        'before': {name: digest(original)}}},
                'patches': {}}))
            command = [sys.executable, str(repo/'scripts/s10/virtual_vibration.py'),
                       str(root/'repo'), str(work), str(decoded), 'beyond2lte', 'before']
            subprocess.run(command, check=True, capture_output=True, text=True)
            good.write_bytes(b'changed actual class')
            rejected = subprocess.run(command, capture_output=True, text=True)
            self.assertNotEqual(rejected.returncode, 0)
            self.assertIn('Unreviewed virtual vibration migration class', rejected.stderr)
            # A valid stale directory must never substitute for missing real output.
            stale.write_bytes(original)
            good.unlink()
            rejected = subprocess.run(command, capture_output=True, text=True)
            self.assertNotEqual(rejected.returncode, 0)
            self.assertIn('Missing or ambiguous virtual vibration migration class', rejected.stderr)

    def test_virtual_sound_gate_preserves_motor_code_and_rejects_reactivation(self):
        import re
        with tempfile.TemporaryDirectory() as td:
            root=Path(td); path=root/'smali_classes2'/MANAGER
            path.parent.mkdir(parents=True)
            original='''.class public Lcom/android/server/vibrator/VibratorManagerService;
.super Ljava/lang/Object;
.method public final bootCompleteReady()V
    .locals 0
    return-void
.end method
.method public vibrate()V
    .locals 0
    return-void
.end method
.method public cancel()V
    .locals 1
    iget-object v0, p0, '''+FIELD+'''
    if-eqz v0, :done
    :done
    return-void
.end method
'''
            path.write_text(original)
            info={'boot_method_sha256':digest(re.findall(BOOT,original,re.M|re.S)[0].encode()),
                  'physical_vibration_code_sha256':digest(re.sub(BOOT,'',original,flags=re.M|re.S).encode()),
                  'guarded_helper_reads':1}
            check_backend(root,info)
            path.write_text(original.replace('vibrate()V','brokenMotor()V'))
            with self.assertRaises(ValueError): check_backend(root,info)
            path.write_text(original)
            extra=root/'smali_classes2/Unexpected.smali'
            for line in ('new-instance v0, '+HELPER, 'iput-object v0, p0, '+FIELD,
                         'iget-object v0, p0, '+FIELD+'\n    return-void'):
                extra.write_text(line+'\n')
                with self.assertRaises(ValueError): check_backend(root,info)

    def test_native_encoder_rejects_modern_format_and_wrong_method(self):
        with tempfile.TemporaryDirectory() as td:
            decoded=Path(td); relative='example/Encoder.smali'
            path=decoded/'smali_classes2'/relative; path.parent.mkdir(parents=True)
            original='''.class public Lexample/Encoder;
.super Ljava/lang/Object;
.method public configure()V
    .locals 1
    const v0, 0x7f000789
    return-void
.end method
'''
            info={'encoder_classes':{}, 'encoder_methods':[
                {'class':relative,'method':'configure()V','requires':['0x7f000789']}]}
            def write(text):
                path.write_text(text)
                info['encoder_classes'][relative]=hashlib.sha256(path.read_bytes()).hexdigest()
            write(original); check_encoders(decoded,info)
            # Even a new digest cannot authorize the incompatible format.
            write(original.replace('0x7f000789','0x7f420888'))
            with self.assertRaises(ValueError): check_encoders(decoded,info)
            # A compatible value in an unrelated method is insufficient.
            write(original.replace('configure()V','unrelated()V'))
            with self.assertRaises(ValueError): check_encoders(decoded,info)
            write(original)
            other=decoded/'smali_classes2/example/Unexpected.smali'
            other.write_text('.class Lexample/Unexpected;\n# 0x7f420888\n')
            with self.assertRaises(ValueError): check_encoders(decoded,info)

    def test_native_camera_classes_reject_changed_or_duplicate_implementations(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td); relative='com/example/Camera.smali'
            path=root/'smali_classes2'/relative; path.parent.mkdir(parents=True)
            original=b'.class Lcom/example/Camera;\n.super Ljava/lang/Object;\n'
            path.write_bytes(original)
            expected={relative:hashlib.sha256(original).hexdigest()}
            check_classes(root,expected)
            other=root/'smali_classes5'/relative; other.parent.mkdir(parents=True)
            other.write_bytes(original)
            with self.assertRaises(ValueError): check_classes(root,expected)
            other.unlink(); path.write_bytes(original+b'# unexpected code change\n')
            with self.assertRaises(ValueError): check_classes(root,expected)
            path.write_bytes(original.replace(b'Camera;',b'Impostor;'))
            with self.assertRaises(ValueError): check_classes(root,expected)
            path.unlink()
            with self.assertRaises(ValueError): check_classes(root,expected)

    def test_physical_storage_module_preserves_pinned_boot_bytes(self):
        repo=Path(__file__).resolve().parents[2]
        def entry(name, data, mode=0o100644):
            name=name.encode()+b'\0'; fields=[1,mode,0,0,1,0,len(data),0,0,0,0,len(name),0]
            result=b'070701'+b''.join(f'{n:08x}'.encode() for n in fields)+name
            result+=b'\0'*((-len(result))%4); result+=data
            return result+b'\0'*((-len(result))%4)
        fstab=''.join(f'/dev/block/by-name/{p} /{p} ext4 ro wait,first_stage_mount\n' for p in BUDGET)
        fstab+='/dev/block/by-name/userdata /data f2fs noatime wait,check,quota\n'
        ramdisk=gzip.compress(entry('fstab.exynos9820',fstab.encode())+entry('TRAILER!!!',b''))
        header=bytearray(2048); header[:8]=b'ANDROID!'
        struct.pack_into('<9I',header,8,8,0, len(ramdisk),0,0,0,0,2048,1)
        boot=bytes(header)+b'kernel!!'+b'\0'*2040+ramdisk
        self.assertEqual(boot_fstab(boot),fstab)
        check_fstab(fstab,ramdisk=True)
        for text in (fstab.replace('ext4','erofs'),fstab.replace('wait,first_stage_mount','wait,logical'),
                     fstab.replace('f2fs','ext4'),fstab.replace('wait,check,quota','wait,fileencryption=ice')):
            with self.assertRaises(ValueError): check_fstab(text)
        with tempfile.TemporaryDirectory() as td:
            work=Path(td); (work/'kernel').mkdir(); (work/'vendor/etc').mkdir(parents=True)
            (work/'vendor/etc/fstab.exynos9820').write_text(fstab)
            images={'boot.img':boot,'dtb.img':bytes.fromhex('d7b7ab1e')+b'x'*4096,'dtbo.img':bytes.fromhex('d7b7ab1e')+b'y'*4096}
            for name,data in images.items(): (work/'kernel'/name).write_bytes(data)
            info={'device':'beyond2lte','revision':KERNEL_REV,'ext4':True,'kernelsu':False,
                  'sha256':{name:hashlib.sha256(data).hexdigest() for name,data in images.items()}}
            (work/'kernel/kernel.json').write_text(json.dumps(info))
            script='''set -e; SRC_DIR="$1"; WORK_DIR="$2"; TARGET_PLATFORM=exynos9820; TARGET_CODENAME=beyond2lte;
                EVAL() { eval "$1"; }; source "$SRC_DIR/unica/patches/fs/customize.sh"'''
            subprocess.run(['bash','-c',script,'--',str(repo),str(work)],check=True,capture_output=True,text=True)
            for name,data in images.items(): self.assertEqual((work/'kernel'/name).read_bytes(),data)
            self.assertEqual((work/'vendor/etc/fstab.exynos9820').read_text(),fstab)
            (work/'kernel/boot.img').write_bytes(boot+b'changed')
            result=subprocess.run(['bash','-c',script,'--',str(repo),str(work)],capture_output=True,text=True)
            self.assertNotEqual(result.returncode,0)

    def test_packaged_kernel_digest_detects_post_build_changes(self):
        with tempfile.TemporaryDirectory() as td:
            target=Path(td)/'rom.zip'; device='beyond2lte'
            images={n:b'x'*4096 for n in ('boot.img','dtb.img','dtbo.img')}
            sizes={p:4000000 for p in BUDGET}; sizes.update({n.removesuffix('.img'):len(b) for n,b in images.items()})
            shell,edify=generate(device,sizes)
            members=dict(images); members['META-INF/com/google/android/updater-script']=edify
            info={'device':device,'revision':KERNEL_REV,'ext4':True,'kernelsu':False,
                  'sha256':{n:hashlib.sha256(b).hexdigest() for n,b in images.items()}}
            members['kernel.json']=json.dumps(info)
            from camera_portrait import SOURCE, SINGLE, NEXUS, LIBRARY, RECORD
            members[RECORD] = json.dumps(dict(schema=1, device=device, source_firmware=SOURCE,
                files={name: '0'*64 for name in (SINGLE, NEXUS, LIBRARY)}))
            from legacy_features import manifest as legacy_manifest
            legacy = legacy_manifest(Path(__file__).resolve().parents[2])
            members['wifi-provenance.json'] = json.dumps(dict(legacy['migrations']['wifi'],
                device=device, source_firmware=legacy['source_firmware'], mode='wifi'))
            for part in BUDGET:
                for suffix in ('.transfer.list','.new.dat.br','.patch.dat'): members[part+suffix]=b''
            def write():
                with zipfile.ZipFile(target,'w') as z:
                    for name,data in members.items(): z.writestr(name,data)
            write(); verify_zip(target,device)
            members['dtbo.img']=b'y'*4096; write()
            with self.assertRaises(ValueError): verify_zip(target,device)
            members['dtbo.img'] = images['dtbo.img']
            wrong = json.loads(members['wifi-provenance.json'])
            wrong['device'] = 'beyond0lte'
            members['wifi-provenance.json'] = json.dumps(wrong)
            write()
            with self.assertRaisesRegex(ValueError, 'packaged S10 wifi'):
                verify_zip(target, device)
            members['wifi-provenance.json'] = json.dumps(dict(legacy['migrations']['wifi'],
                device=device, source_firmware=legacy['source_firmware'], mode='wifi'))
            portrait = json.loads(members[RECORD]); portrait['files'].pop(NEXUS)
            members[RECORD] = json.dumps(portrait); write()
            with self.assertRaisesRegex(ValueError, 'Incomplete S10 portrait'):
                verify_zip(target, device)

    def test_stock_policies_reach_all_four_sdhms_outputs(self):
        repo = Path(__file__).resolve().parents[2]
        for device, models in DEVICES.items():
            with self.subTest(device=device), tempfile.TemporaryDirectory() as td:
                work = Path(td); decoded = work/'apktool'/SDHMS
                (decoded/'assets').mkdir(parents=True)
                (decoded/'res/raw').mkdir(parents=True)
                for name in ('siop_default', 'siop_model', 'ssrm_default'):
                    (decoded/'assets'/name).write_bytes(b'encrypted source policy')
                subprocess.run(['bash', '-c', '''
                    set -e
                    SRC_DIR="$1"; WORK_DIR="$2"; APKTOOL_DIR="$WORK_DIR/apktool"
                    source "$SRC_DIR/target/$3/config.sh"
                    MODPATH="$SRC_DIR/unica/patches/dvfs"; DEBUG=false
                    SOURCE_PLATFORM_SDK_VERSION=36
                    SOURCE_DVFSAPP_CONFIG_DVFS_POLICY_FILENAME=dvfs_policy_default
                    SOURCE_DVFSAPP_CONFIG_SSRM_POLICY_FILENAME=siop_e2s_s5e9945
                    LOG() { :; }; LOGW() { :; }; ABORT() { echo "$1" >&2; exit 1; }
                    EVAL() { eval "$1"; }; SMALI_PATCH() { :; }; DECODE_APK() { :; }
                    SET_FLOATING_FEATURE_CONFIG() { printf '%s' "$2" > "$WORK_DIR/selector"; }
                    source "$MODPATH/customize.sh"
                    ''', '--', str(repo), str(work), device], check=True, capture_output=True, text=True)
                policy, files = policy_inputs(repo, device)
                self.assertEqual((work/'selector').read_text(), policy)
                self.assertEqual((decoded/'assets'/f'{policy}.xml').read_bytes(), files['siop_model.xml'].read_bytes())
                installed_apk = work/'system'/SDHMS
                installed_apk.parent.mkdir(parents=True)
                members = {str(p.relative_to(decoded)): p.read_bytes() for p in decoded.rglob('*') if p.is_file()}
                def write_apk():
                    with zipfile.ZipFile(installed_apk, 'w') as z:
                        for name, data in members.items(): z.writestr(name, data)
                write_apk()
                features = work/'system/system/etc/floating_feature.xml'
                features.parent.mkdir(parents=True, exist_ok=True)
                features.write_text('<SecFloatingFeatureSet><SEC_FLOATING_FEATURE_SYSTEM_CONFIG_SIOP_POLICY_FILENAME>'+policy+'</SEC_FLOATING_FEATURE_SYSTEM_CONFIG_SIOP_POLICY_FILENAME></SecFloatingFeatureSet>')
                source = work/'stock-matrix.xml'; source.write_text(self.stock_matrix())
                installed_matrix = work/'system'/MATRIX
                installed_matrix.parent.mkdir(parents=True, exist_ok=True)
                installed_matrix.write_bytes(source.read_bytes())
                record_matrix(source, work, device, models[0]+'/TEST')
                policy_output(repo, work, device)
                members['assets/'+policy+'.xml'] = b'<siop_document/>'
                write_apk()
                with self.assertRaises(ValueError): policy_output(repo, work, device)
                members['assets/'+policy+'.xml'] = files['siop_model.xml'].read_bytes()
                # A shortened path still contains identical XML bytes, but must
                # fail the named-resource contract that packaging enforces.
                raw_name = 'res/raw/dvfs_policy_makalu_xx.xml'
                members['res/bN.xml'] = members.pop(raw_name)
                write_apk()
                with self.assertRaises(KeyError): policy_output(repo, work, device)
                members[raw_name] = b'<DvfsHintList/>'
                write_apk()
                with self.assertRaises(ValueError): policy_output(repo, work, device)

    @staticmethod
    def stock_matrix():
        return '''<compatibility-matrix version="1.0" type="framework">
          <hal format="hidl" optional="true"><name>android.hardware.biometrics.fingerprint</name><version>2.1</version><interface><name>IBiometricsFingerprint</name><instance>default</instance></interface></hal>
          <hal format="hidl" optional="true"><name>vendor.samsung.hardware.radio</name><version>2.0</version><interface><name>ISehRadio</name><instance>slot1</instance></interface></hal>
          <hal format="hidl" optional="true"><name>vendor.samsung_slsi.hardware.ExynosHWCServiceTW</name><version>1.0</version><interface><name>IExynosHWCServiceTW</name><instance>default</instance></interface></hal>
        </compatibility-matrix>'''

    def test_vintf_import_keeps_target_firmware_requirements(self):
        repo = Path(__file__).resolve().parents[2]
        with tempfile.TemporaryDirectory() as td:
            root = Path(td); work = root/'work'; fw = root/'fw'
            source = fw/'SM-G975F_TEST/system'/MATRIX
            source.parent.mkdir(parents=True); source.write_text(self.stock_matrix())
            destination = work/'system'/MATRIX
            destination.parent.mkdir(parents=True)
            subprocess.run(['bash', '-c', '''
                set -e; SRC_DIR="$1"; WORK_DIR="$2"; FW_DIR="$3"; DEBUG=false
                TARGET_CODENAME=beyond2lte; TARGET_PLATFORM=exynos9820
                SOURCE_PLATFORM_SDK_VERSION=36; TARGET_PLATFORM_SDK_VERSION=31
                TARGET_FIRMWARE=SM-G975F/TEST
                LOG() { :; }; LOGW() { :; }; ABORT() { echo "$1" >&2; exit 1; }
                EVAL() { eval "$1"; }
                ADD_TO_WORK_DIR() { cp "$FW_DIR/SM-G975F_TEST/system/$3" "$WORK_DIR/system/$3"; }
                source "$SRC_DIR/unica/patches/vintf/customize.sh"
                ''', '--', str(repo), str(work), str(fw)], check=True, capture_output=True, text=True)
            self.assertEqual(source.read_bytes(), destination.read_bytes())
            self.assertEqual(json.loads((work/'vintf-provenance.json').read_text())['sha256'], hashlib.sha256(source.read_bytes()).hexdigest())
            with self.assertRaises(ValueError): record_matrix(source, work, 'beyond2lte', 'SM-G970F/TEST')
            destination.write_text('<compatibility-matrix/>')
            with self.assertRaises(ValueError): record_matrix(source, work, 'beyond2lte', 'SM-G975F/TEST')

    def test_import_preserves_modes_labels_and_merged_system_ext(self):
        repo=Path(__file__).resolve().parents[2]
        for part in ('system', 'system_ext'):
            with self.subTest(part=part), tempfile.TemporaryDirectory() as td:
                root=Path(td); donor=root/'donor'; work=root/'work'
                original=donor/part/'lib/old'; original.mkdir(parents=True)
                (original/'driver.so').write_bytes(b'archived-hardware-driver')
                (donor/('fs_config-'+part)).write_text(
                    f'{part}/lib/old 0 1000 750 capabilities=0x0\n'
                    f'{part}/lib/old/driver.so 0 2000 640 capabilities=0x0\n')
                (donor/('file_context-'+part)).write_text(
                    f'/{part}/lib/old u:object_r:system_file:s0\n'
                    f'/{part}/lib/old/driver\\.so u:object_r:system_lib_file:s0\n')
                (work/'configs').mkdir(parents=True)
                (work/'configs/fs_config-system').touch()
                (work/'configs/file_context-system').touch()
                source='system/lib/old' if part=='system' else 'lib/old'
                dest='system/lib/new' if part=='system' else 'lib/new'
                subprocess.run(['bash','-c',
                    'set -e; SRC_DIR="$1"; WORK_DIR="$2"; TARGET_OS_BUILD_SYSTEM_EXT_PARTITION=false; '
                    'source "$SRC_DIR/scripts/utils/common_utils.sh"; ADD_TO_WORK_DIR "$3" "$4" "$5" "$6"',
                    '--',str(repo),str(work),str(donor),part,source,dest],check=True,capture_output=True,text=True)
                relative='system/lib/new' if part=='system' else 'system/system_ext/lib/new'
                payload=work/'system'/relative/'driver.so'
                self.assertEqual(payload.read_bytes(),b'archived-hardware-driver')
                fs=(work/'configs/fs_config-system').read_text()
                self.assertIn(relative+' 0 1000 750',fs)
                self.assertIn(relative+'/driver.so 0 2000 640',fs)
                contexts=(work/'configs/file_context-system').read_text()
                self.assertIn('/'+relative+'/driver\\.so u:object_r:system_lib_file:s0',contexts)
                self.assertNotIn('system/system/system_ext/',fs+contexts)

    def test_capacity_and_device_guards(self):
        sizes = {p: min(m*1048576, 5000000) for p,m in BUDGET.items()}
        sizes.update(boot=16000000, dtb=800000, dtbo=800000)
        for device, models in DEVICES.items():
            shell, edify = generate(device, sizes)
            subprocess.run(['sh','-n'], input=shell, text=True, check=True)
            self.assertLess(edify.index('run_program('), edify.index('block_image_update('))
            self.assertNotIn('map_partition', edify)
            for model in models: self.assertIn(model, edify)
        with self.assertRaises(ValueError): generate('beyond2lte',dict(sizes,odm=5*1048576))
        with self.assertRaises(ValueError): generate('beyond2lte',dict(sizes,super=1))

    def test_midas_preserves_reviewed_model_selectors(self):
        with tempfile.TemporaryDirectory() as td:
            config, prop = Path(td)/'midas.json', Path(td)/'build.prop'
            config.write_text(json.dumps({'device_property':'ro.product.device',
                'midasSR_devices':['r9s','e2s','p3s']}))
            prop.write_text('ro.product.device=e2s\n')
            before=config.read_bytes()
            self.assertEqual(verify(config,prop),'e2s')
            self.assertEqual(config.read_bytes(),before)
            for text in ('ro.product.device=unsupported\n', 'ro.product.device=e2s\nro.product.device=e1s\n'):
                prop.write_text(text)
                with self.assertRaises(ValueError): verify(config,prop)

    def test_kernel_target_and_digest(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td); source=root/'input'; source.mkdir()
            hashes={}
            for name,magic in [('boot.img',b'ANDROID!'),('dtb.img',bytes.fromhex('d7b7ab1e')),('dtbo.img',bytes.fromhex('d7b7ab1e'))]:
                data=magic+b'x'*4096; (source/name).write_bytes(data); hashes[name]=hashlib.sha256(data).hexdigest()
            (source/'kernel.json').write_text(json.dumps({'device':'beyond2lte','revision':KERNEL_REV,'kernelsu':False,'ext4':True,'sha256':hashes}))
            install(source,root/'ok','beyond2lte')
            with self.assertRaises(ValueError): install(source,root/'wrong','beyond1lte')
            (source/'boot.img').write_bytes(b'ANDROID!'+b'y'*4096)
            with self.assertRaises(ValueError): install(source,root/'bad','beyond2lte')

    def test_instruction_patches_are_bounded(self):
        with tempfile.TemporaryDirectory() as td:
            path=Path(td)/'binary'
            for feature,(old,new) in PATCHES.items():
                path.write_bytes(b'head'+bytes.fromhex(old)+b'tail')
                self.assertEqual(patch(path,feature),'patched')
                self.assertEqual(path.read_bytes(),b'head'+bytes.fromhex(new)+b'tail')
                self.assertEqual(patch(path,feature),'already-patched')
                path.write_bytes(bytes.fromhex(old)*2)
                with self.assertRaises(ValueError): patch(path,feature)
                path.write_bytes(b'unknown-firmware'); self.assertEqual(patch(path,feature),'unsupported-donor')


if __name__ == '__main__': unittest.main()
