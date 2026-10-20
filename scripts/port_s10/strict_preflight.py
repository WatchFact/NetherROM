#!/usr/bin/env python3
"""Fail-fast Exynos9820 source dependency audit. Never executes ROM modules.

Stages:
  index    Verify the pinned camera donor blobs exist in the current Git tree
           (works with a sparse checkout; no binary downloads).
  donors   Inspect actual donor files imported by all Exynos9820 module scripts.
  firmware Check target stock and source firmware inputs before make_rom.

The scanner checks static imports and the conventional BLOBS_LIST shell loops.
Future dynamic imports must have an explicit inspection rule; do not treat
unrecognised dynamic paths as silently verified.
"""
import argparse
import hashlib
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PLATFORM = ROOT / "platform/exynos9820/patches"
# Immutable git blob IDs verified against the ArtisanROM v3.1.0 tree.
PINNED = {
    "prebuilts/samsung/p3sxxx/system/lib64/libeden_wrapper_system.so": "92598bf230a706b656e2406902636c78cfd9ee8b",
    "prebuilts/samsung/p3sxxx/system/lib64/libsnap_aidl.snap.samsung.so": "e8f83db037074f8315b071b9525f787babf504b7",
    "prebuilts/samsung/p3sxxx/system/lib64/libSwIsp_core.camera.samsung.so": "a26ce6802c5c5c226b62e18b4f69cde5311c2249",
    "prebuilts/samsung/p3sxxx/system/lib64/libSwIsp_wrapper_v1.camera.samsung.so": "6fc0d09b4b41ef58f9f63e393834929b18e0b826",
    "prebuilts/samsung/p3sxxx/system/lib64/libmidas_core.camera.samsung.so": "0d041be0f5a46f0e4d6b253f15400ce4a9705866",
    "prebuilts/samsung/p3sxxx/system/lib64/libmidas_DNNInterface.camera.samsung.so": "17056a01c9a58334d9e650fbd1801b3014d2e21d",
    "prebuilts/samsung/p3sxxx/system/priv-app/SingleTakeService/SingleTakeService.apk": "d0d244a1c145e9cc50196235b94aaa0626e0c7f6",
    "prebuilts/samsung/p3sxxx/system/priv-app/PhotoRemasterService/PhotoRemasterService.apk.00": "1abf97268aa6b7fb7aed9b1ce7bb450759e2a7bb",
    "prebuilts/samsung/p3sxxx/system/priv-app/PhotoRemasterService/PhotoRemasterService.apk.01": "64f61695044c0d5f049d611cbb03991be6bdd4dd",
    "prebuilts/samsung/p3sxxx/system/priv-app/PhotoRemasterService/PhotoRemasterService.apk.02": "4b8d24d21bc02558d49aa18bb659f1f20b4aabb9",
    "prebuilts/samsung/p3sxxx/system/cameradata/singletake/service-feature.xml": "435644f28f631c3c702847a66ec5f3218128d07e",
    "prebuilts/samsung/a73xqxx/system/lib64/libBestComposition.polarr.so": "e36deee087bd650f35e06af1dc4136c71663d3ba",
    "prebuilts/samsung/a73xqxx/system/lib64/libFeature.polarr.so": "d436d1e0b7927c20e1acf94d4f0f17cd581eb087",
    "prebuilts/samsung/a73xqxx/system/lib64/libTracking.polarr.so": "7c5e2509c2ad69d2dd1a26bb8d73e16bc2b0d181",
}
DIRECT = re.compile(r'ADD_TO_WORK_DIR\s+"([^"]+)"\s+"([^"]+)"\s+"([^"]+)"')
LOOPS = re.compile(
    r'BLOBS_LIST="(.*?)"\s*for\s+blob\s+in\s+\$BLOBS_LIST\s*do\s*(.*?)\s*done',
    re.S
)
LIST = re.compile(r'(?m)^([A-Z][A-Z_]+)="\s*\n(.*?)\n"', re.S)
VALID_PARTS = {"system", "system_ext", "product", "vendor", "odm"}
CAMERA_CRITICAL = (
    "system/lib64/libeden_wrapper_system.so",
    "system/lib64/libsnap_aidl.snap.samsung.so",
    "system/lib64/libSwIsp_core.camera.samsung.so",
    "system/lib64/libSwIsp_wrapper_v1.camera.samsung.so",
)
SOURCE_CAMERA_EXTRA = (
    "system/system/lib64/libstagefright.so",
    "system/system/lib64/libPortraitSolution.camera.samsung.so",
    "system/system/cameradata/portrait_data/single_bokeh_feature.json",
)
TARGET_EXTRA = (

    "system/system/priv-app/HotwordEnrollmentOKGoogleExCORTEXM4/HotwordEnrollmentOKGoogleExCORTEXM4.apk",
    "system/system/priv-app/HotwordEnrollmentXGoogleExCORTEXM4/HotwordEnrollmentXGoogleExCORTEXM4.apk",
    "vendor/etc/fstab.exynos9820",
    "vendor/etc/selinux/vendor_sepolicy.cil",
    "vendor/ueventd.rc",
    "vendor/etc/permissions/handheld_core_hardware.xml",
)

def fail(message):
    raise ValueError(message)

def camera_feature_check():
    import xml.etree.ElementTree as ET
    for device in ("beyond0lte", "beyond1lte", "beyond2lte", "beyondx"):
        path = ROOT / "target" / device / "patches/camera/system/cameradata/camera-feature.xml"
        root = ET.parse(path).getroot()
        if root.tag != "resources":
            fail(f"{device}: bad camera XML root")
        names = [node.get("name") for node in root if node.get("name", "").startswith("SHOOTING_MODE_")]
        if any(names.count(name) != 1 for name in ("SHOOTING_MODE_PHOTO", "SHOOTING_MODE_VIDEO")):
            fail(f"{device}: missing or duplicated base camera mode")
        if len(names) != len(set(names)):
            fail(f"{device}: duplicate camera mode")
        print(f"Camera XML valid: {device} ({len(names)} modes)")

def validate_source_camera(source_fw):
    if not source_fw or not source_fw.is_dir():
        fail("Missing source One UI firmware directory")
    for relative in SOURCE_CAMERA_EXTRA:
        path = source_fw / relative
        if not exists_or_split(path):
            fail(f"Missing source camera framework file: {path}")
    print(f"Source camera framework OK ({len(SOURCE_CAMERA_EXTRA)} files)")

def git_index_check(root=ROOT):
    for path, sha in PINNED.items():
        result = subprocess.run(
            ["git", "-C", str(root), "ls-tree", "HEAD", "--", path],
            check=True, capture_output=True, text=True,
        ).stdout.strip()
        match = re.fullmatch(r"100644 blob ([0-9a-f]{40})\t.+", result)
        if not match or match.group(1) != sha:
            fail(f"Missing or changed pinned Exynos9820 donor: {path}; {result!r}")
        print(f"PINNED {path}: {sha}")

def known_source(source, partition, pathname, target_fw):
    if not pathname or pathname.startswith("/") or ".." in Path(pathname).parts:
        fail(f"Invalid donor path: {source}:{partition}:{pathname}")
    if partition not in VALID_PARTS:
        fail(f"Invalid partition: {partition}")
    if source == "$TARGET_FIRMWARE":
        if not target_fw:
            return None
        base = target_fw
    elif source == "$SOURCE_FIRMWARE":
        if not target_fw:
            return None
        base = target_fw  # source inputs are checked separately by the caller
    elif re.fullmatch(r"[a-z][a-z0-9]*", source):
        base = ROOT / "prebuilts/samsung" / source
    else:
        fail(f"Unrecognised donor expression {source!r}; add an explicit audit rule")

    if partition == "system":
        rel = pathname.removeprefix("system/")
        # Original firmware extraction has system/system while prebuilts have system/.
        if (base / "system/system").is_dir():
            return base / "system/system" / rel
        return base / "system" / rel
    if partition == "system_ext":
        for prefix in ("system_ext", "system/system/system_ext", "system/system_ext"):
            if (base / prefix).is_dir():
                return base / prefix / pathname
        return base / "system_ext" / pathname
    return base / partition / pathname

def exists_or_split(path):
    if path.is_file() and path.stat().st_size:
        return True
    if path.is_dir():
        return any(p.is_file() and p.stat().st_size for p in path.rglob("*"))
    pieces = sorted(path.parent.glob(path.name + ".[0-9][0-9]"))
    if not pieces:
        return False
    return all(
        p.name == f"{path.name}.{i:02d}" and p.stat().st_size
        for i, p in enumerate(pieces)
    )

def dependencies(source):
    """Yield module imports, including the checked BLOBS_LIST loop expansions."""
    clean = source.replace("\\\n", " ")
    for donor, partition, file in DIRECT.findall(clean):
        if "$" not in file:
            yield donor, partition, file
    for bloblist, body in LOOPS.findall(clean):
        for donor, partition, file in DIRECT.findall(body):
            if file == "$blob":
                for file in bloblist.split():
                    yield donor, partition, file

def validate_32bit_runtime(stage, target_fw=None):
    """Check dynamically expanded ARM32 APEX/HIDL library lists too."""
    script = (ROOT / "platform/exynos9820/patches/zzz_runtime32_compat/customize.sh")
    if not script.is_file() and stage == "index":
        # Actions' lightweight preflight intentionally does not check out
        # Exynos990 modules. Inspect the tracked source from the Git tree.
        data = subprocess.run(
            ["git", "-C", str(ROOT), "show",
             "HEAD:platform/exynos990/patches/zzz_runtime32_compat/customize.sh"],
            check=True, capture_output=True, text=True,
        ).stdout
    elif script.is_file():
        data = script.read_text()
    else:
        fail("Missing the required ARM32 runtime compatibility module")
    for variable, donor in (("RUNTIME_LIBS", "r11sxxx"), ("LEGACY_AUDIO_LIBS", "$TARGET_FIRMWARE")):
        matched = re.search(r'(?m)^' + variable + r'="\s*\n(.*?)\n"', data, re.S)
        if not matched:
            fail(f"Runtime module's {variable} layout changed: review required")
        values = matched.group(1).split()
        if len(values) < (55 if variable == "RUNTIME_LIBS" else 6):
            fail(f"Runtime list truncated: {variable}")
        for name in values:
            if not re.fullmatch(r'[A-Za-z0-9_.@+-]+\.so', name):
                fail(f"Unexpected runtime library name: {variable}: {name}")
            path = f"system/lib/{name}"
            if stage == "index":
                if donor == "$TARGET_FIRMWARE":
                    continue
                found = subprocess.run(
                    ["git", "-C", str(ROOT), "ls-tree", "HEAD", "--",
                     f"prebuilts/samsung/{donor}/{path}"],
                    check=True, text=True, capture_output=True,
                ).stdout
                if not found:
                    fail(f"Missing indexed 32-bit runtime {donor}/{path}")
            elif stage == "donors" and donor != "$TARGET_FIRMWARE":
                if not exists_or_split(known_source(donor, "system", path, None)):
                    fail(f"Missing 32-bit runtime {donor}/{path}")
            elif stage == "firmware" and donor == "$TARGET_FIRMWARE":
                if not exists_or_split(known_source(donor, "system", path, target_fw)):
                    fail(f"Missing target HIDL/ARM32 library {path}")
        print(f"Runtime {variable}: {len(values)} libraries audited ({stage})")

def audit_sources(stage, target_fw=None, source_fw=None):
    if not PLATFORM.is_dir():
        fail("Exynos9820 patches are absent. Run compat.sh before donor audit.")
    paths = sorted(PLATFORM.glob("*/customize.sh"))
    if len(paths) < 8:
        fail(f"Unexpected Exynos9820 module inventory: {len(paths)} scripts")
    count, deferred = 0, 0
    used = set()
    for file in paths:
        script = file.read_text()
        for source, part, pathname in dependencies(script):
            if source in ("$TARGET_FIRMWARE", "$SOURCE_FIRMWARE"):
                if stage == "donors":
                    deferred += 1
                    continue
            else:
                if stage == "firmware":
                    continue
            full = known_source(source, part, pathname, target_fw)
            if full is None:
                fail(f"Cannot resolve dependency {file}:{source}:{part}:{pathname}")
            if not exists_or_split(full):
                fail(f"MISSING {file.relative_to(ROOT)}: {source}/{part}/{pathname} (looked for {full})")
            used.add((source, part, pathname))
            count += 1
    if stage == "donors":
        for filename in CAMERA_CRITICAL:
            if ("p3sxxx", "system", filename) not in used:
                fail(f"Critical S10 camera module does not import vetted p3 donor: {filename}")
        # Validate that the real checked-out bytes still match verified upstream.
        for path, sha in PINNED.items():
            p = ROOT / path
            if not p.is_file():
                fail(f"Missing pinned binary {path}")
            # Git blob IDs include a header; do not compare a raw SHA-1.
            found = subprocess.run(
                ["git", "hash-object", str(p)],
                check=True, capture_output=True, text=True,
            ).stdout.strip()
            if found != sha:
                fail(f"Donor hash changed: {path}: {found} != {sha}")
    if stage == "firmware":
        validate_source_camera(source_fw)
        if not target_fw or not target_fw.is_dir():
            fail("Target firmware must be extracted before firmware preflight")
        for relative in TARGET_EXTRA:
            required = target_fw / relative
            if not exists_or_split(required):
                fail(f"Missing target firmware source: {required}")
    print(f"S10 {stage} audit OK: {count} resolved imports, {deferred} firmware imports deferred")

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--stage", required=True, choices=("index", "donors", "firmware"))
    p.add_argument("--target-fw", type=Path)
    p.add_argument("--source-fw", type=Path)
    args = p.parse_args()
    try:
        if args.stage == "index":
            git_index_check()
            camera_feature_check()
        else:
            audit_sources(args.stage, args.target_fw, args.source_fw)
        validate_32bit_runtime(args.stage, args.target_fw)
    except (ValueError, OSError, subprocess.CalledProcessError) as exc:
        print(f"S10 STRICT PREFLIGHT FAILED: {exc}", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()
