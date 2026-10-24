#!/usr/bin/env python3
"""Fast, firmware-free regressions for the new recovery installer generator."""
import json
import subprocess
import tempfile
import unittest
from pathlib import Path

from installer import BUDGET, DEVICE, GUARD, PARTS, RAW, UPDATER, generate


class FlashableTests(unittest.TestCase):
    def setUp(self):
        self.sizes = {p: 4 * 1048576 for p in PARTS}
        self.sizes.update(boot=16 * 1048576, dtb=1048576, dtbo=1048576)

    def test_only_s10plus_supported(self):
        with self.assertRaisesRegex(ValueError, 'only supports'):
            generate('beyond1lte', self.sizes)
        for size in (0, -1, '4194304', 1.5):
            with self.subTest(size=size), self.assertRaises(ValueError):
                generate(DEVICE, dict(self.sizes, system=size))
        with self.assertRaises(ValueError):
            generate(DEVICE, dict(self.sizes, super=4194304))
        with self.assertRaises(ValueError):
            generate(DEVICE, dict(self.sizes, odm=5 * 1048576))
        with self.assertRaises(ValueError):
            generate(DEVICE, dict(self.sizes, system=4194305))

    def test_cpu_only_gate_and_correct_order(self):
        shell, updater = generate(DEVICE, self.sizes)
        subprocess.run(['sh', '-n'], input=shell, text=True, check=True)
        self.assertIn('Unsupported CPU: Exynos9820 required', updater)
        self.assertIn('ro.hardware.chipname', updater)
        self.assertNotIn('s10-preflight.sh', shell + updater)
        self.assertLess(updater.index('Exynos9820 required'), updater.index('Wrong S10+ model/codename'))
        self.assertLess(updater.index('Wrong S10+ model/codename'), updater.index(GUARD))
        self.assertLess(updater.index('run_program('), updater.index('block_image_update('))
        for previous, current in zip(PARTS + RAW, (PARTS + RAW)[1:]):
            self.assertLess(updater.index(f'/dev/block/by-name/{previous}'),
                            updater.index(f'/dev/block/by-name/{current}'))
        self.assertIn('SM-G975F/DS', updater)
        self.assertNotIn('SM-G975N', updater)

    def test_write_guard_is_separate_and_compact(self):
        shell, _ = generate(DEVICE, self.sizes)
        self.assertIn('Aliased partitions:', shell)
        self.assertIn('Partition is mounted:', shell)
        self.assertIn('capacity=$(blockdev --getsize64 "$device")', shell)
        self.assertEqual(shell.count('capacity=$(blockdev --getsize64 "$device")'), 1)
        self.assertEqual(shell.count(' /dev/block/by-name/'), 0)
        for part in PARTS + RAW:
            self.assertIn(f'{part} {self.sizes[part]}\n', shell)
        self.assertLess(len(shell.splitlines()), 40)

    def test_generator_cli_writes_only_expected_paths(self):
        with tempfile.TemporaryDirectory() as td:
            folder = Path(td)
            (folder / 'META-INF/com/google/android').mkdir(parents=True)
            (folder / 'sizes.json').write_text(json.dumps(self.sizes))
            subprocess.run(['python3', str(Path(__file__).with_name('installer.py')),
                            str(folder), DEVICE], check=True)
            shell, updater = generate(DEVICE, self.sizes)
            self.assertEqual((folder / GUARD).read_text(), shell)
            self.assertEqual((folder / UPDATER).read_text(), updater)
            self.assertFalse((folder / 's10-preflight.sh').exists())


if __name__ == '__main__':
    unittest.main()
