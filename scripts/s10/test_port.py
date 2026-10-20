#!/usr/bin/env python3
"""Regressions for physical installation, kernel integrity and model migration."""
import hashlib
import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from installer import BUDGET, DEVICES, generate
from kernel_artifacts import KERNEL_REV, install
from midas_config import adapt
from optional_binary_patch import PATCHES, patch


class PortTests(unittest.TestCase):
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

    def test_midas_preserves_legacy_capabilities(self):
        with tempfile.TemporaryDirectory() as td:
            config, prop = Path(td)/'midas.json', Path(td)/'build.prop'
            config.write_text(json.dumps({'device_property':'ro.soc.model',
                'midasSR_devices':['r9s','e2s','p3s'], 'new_feature_devices':['e2s']}))
            prop.write_text('ro.product.device=e2s\n')
            self.assertEqual(adapt(config, prop),'e2s')
            data=json.loads(config.read_text())
            self.assertEqual(data['device_property'],'ro.product.device')
            self.assertEqual(data['midasSR_devices'],['e2s','p3s'])
            self.assertEqual(data['new_feature_devices'],[])
            before=config.read_bytes(); adapt(config,prop); self.assertEqual(config.read_bytes(),before)
            prop.write_text('ro.product.device=e2s\nro.product.device=e1s\n')
            with self.assertRaises(ValueError): adapt(config,prop)

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
