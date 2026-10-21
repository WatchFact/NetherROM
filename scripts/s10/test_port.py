#!/usr/bin/env python3
"""Regressions for physical installation, kernel integrity and model migration."""
import hashlib
import json
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


class PortTests(unittest.TestCase):
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
