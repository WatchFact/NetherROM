#!/usr/bin/env python3
"""Read-only validation of assembled Exynos9820 camera runtime files.

Does not imply working camera HAL/preview/recording until hardware-tested.
"""
import re
import struct
import sys
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

ELF64_AARCH64 = (2, 183)
LIBS = (
    "libeden_wrapper_system.so",
    "libsnap_aidl.snap.samsung.so",
    "libSwIsp_core.camera.samsung.so",
    "libSwIsp_wrapper_v1.camera.samsung.so",
    "libmidas_core.camera.samsung.so",
    "libmidas_DNNInterface.camera.samsung.so",
    "libBestComposition.polarr.so",
    "libFeature.polarr.so",
    "libTracking.polarr.so",
    "libstagefright.so",
    "libPortraitSolution.camera.samsung.so",
)
APK = (
    "system/system/priv-app/SamsungCamera/SamsungCamera.apk",
    "system/system/priv-app/SingleTakeService/SingleTakeService.apk",
    "system/system/priv-app/PhotoRemasterService/PhotoRemasterService.apk",
)
DIRS = (
    "vendor/saiv/swisp_1.0",
    "vendor/etc/singletake",
    "vendor/etc/midas",
    "vendor/etc/VslMesDetector",
)
REQUIRED_POLARR = {
    "libBestComposition.polarr.so",
    "libFeature.polarr.so",
    "libTracking.polarr.so",
}

def check(root: Path) -> None:
    if not root.is_dir():
        raise ValueError(f"Missing assembled work directory: {root}")
    for name in LIBS:
        p = root / "system/system/lib64" / name
        if not p.is_file():
            raise ValueError(f"Missing assembled camera library: {p}")
        with p.open("rb") as f:
            header = f.read(20)
        if len(header) < 20 or header[:4] != b"\x7fELF" or header[4] != ELF64_AARCH64[0] or struct.unpack("<H", header[18:20])[0] != ELF64_AARCH64[1]:
            raise ValueError(f"Wrong ELF architecture or invalid camera library: {p}")
        print(f"ELF64 AArch64: {name} ({p.stat().st_size} bytes)")
    for path in APK:
        p = root / path
        if not p.is_file() or not zipfile.is_zipfile(p):
            raise ValueError(f"Invalid/missing camera APK: {p}")
        print(f"Valid APK archive: {path}")
    for path in DIRS:
        p = root / path
        if not p.is_dir() or not any(f.is_file() and f.stat().st_size for f in p.rglob("*")):
            raise ValueError(f"Missing/empty camera model directory: {p}")
        print(f"Camera model directory: {path}")
    # Verify actual changed camera bytes, not just names or ELF signatures.
    import hashlib
    for donor, name in (
        ("p3sxxx", "libeden_wrapper_system.so"),
        ("p3sxxx", "libSwIsp_core.camera.samsung.so"),
        ("p3sxxx", "libmidas_core.camera.samsung.so"),
        ("a73xqxx", "libBestComposition.polarr.so"),
    ):
        source = Path(__file__).resolve().parents[2] / "prebuilts/samsung" / donor / "system/lib64" / name
        assembled = root / "system/system/lib64" / name
        if not source.is_file() or not assembled.is_file():
            raise ValueError(f"Missing original or assembled S10 camera file: {name}")
        if hashlib.sha256(source.read_bytes()).digest() != hashlib.sha256(assembled.read_bytes()).digest():
            raise ValueError(f"Camera donor blob NOT present in assembled ROM: {name}")
        print(f"Verified modified ROM uses {donor} camera blob: {name}")
    libs = root / "system/system/etc/public.libraries-polarr.txt"
    if not libs.is_file():
        raise ValueError("Camera Polarr allowlist missing")
    names = set(libs.read_text().split())
    if names != REQUIRED_POLARR:
        raise ValueError(f"Unexpected public Polarr libraries: {sorted(names)}")
    feature = root / "system/system/cameradata/camera-feature.xml"
    if not feature.is_file():
        raise ValueError(f"Camera features XML missing: {feature}")
    ET.parse(feature)
    portrait = root / "system/system/cameradata/portrait_data/nexus_bokeh_feature.json"
    if not portrait.is_file() or not portrait.stat().st_size:
        raise ValueError(f"Portrait feature model missing: {portrait}")
    print("Complete assembled camera file checks passed (NOT a boot or camera test)")

if __name__ == "__main__":
    check(Path(sys.argv[1]))
