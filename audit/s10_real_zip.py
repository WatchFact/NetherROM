#!/usr/bin/env python3
"""Replay the ACTUAL signed S10 OTA payload into throwaway ext4 image files.
Never writes to /dev, and cannot establish real-device bootability.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import zipfile

import brotli

BLOCK = 4096
PARTS = ("system", "vendor", "product", "odm")
KERNEL = ("boot", "dtb", "dtbo")
EXPECTED = set(PARTS + KERNEL)

report = {
    "scope": "actual published signed ZIP; OTA payload replay to disposable image files, not a hardware boot test",
    "checks": [],
    "warnings": [],
    "failures": [],
    "parts": {}
}


def check(name, predicate, detail=""):
    passed = bool(predicate)
    report["checks"].append({"name": name, "passed": passed, "detail": str(detail)[:300]})
    if not passed:
        report["failures"].append(name + (": " + str(detail) if detail else ""))
    print(("PASS" if passed else "FAIL") + " " + name + (" — " + str(detail) if detail else ""), flush=True)
    return passed


def file_hash(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for piece in iter(lambda: f.read(8 * 1024 * 1024), b""):
            h.update(piece)
    return h.hexdigest()


def from_ranges(spec):
    values = [int(x) for x in spec.split(",")]
    if not values or values[0] != len(values) - 1 or values[0] % 2:
        raise ValueError("Malformed transfer-list range set: " + spec[:140])
    pairs = list(zip(values[1::2], values[2::2]))
    if any(a < 0 or b <= a for a, b in pairs):
        raise ValueError("Illegal transfer-list range: " + spec[:140])
    return pairs


def transfer_plan(text, capacity_bytes, part):
    lines = [x.strip() for x in text.splitlines() if x.strip()]
    if len(lines) < 3:
        raise ValueError("Truncated transfer list")
    version = int(lines[0])
    total = int(lines[1])
    if version not in (1, 2, 3, 4) or total <= 0 or total * BLOCK > capacity_bytes:
        raise ValueError(f"Transfer header invalid (version={version}, blocks={total}, capacity={capacity_bytes})")
    commands = lines[4:] if version >= 2 else lines[2:]
    operations = []
    seen = set()
    new_blocks = 0
    for line in commands:
        words = line.split()
        op = words[0]
        if op not in ("new", "zero", "erase") or len(words) != 2:
            raise ValueError(f"Unsupported OTA operation ({op}); do not simulate potentially unsafe source-dependent updates")
        for start, end in from_ranges(words[1]):
            if end * BLOCK > capacity_bytes:
                raise ValueError(f"Transfer reaches past {part} image size: {end * BLOCK} > {capacity_bytes}")
            for n in range(start, end):
                if n in seen:
                    raise ValueError(f"Overlapping OTA ranges in {part}: block {n}")
                seen.add(n)
            operations.append((op, start * BLOCK, (end - start) * BLOCK))
            if op == "new":
                new_blocks += end - start
    if not operations or not new_blocks:
        raise ValueError("Empty transfer plan")
    # A full-image replacement should not require any source-block operations.
    return operations, new_blocks * BLOCK, {"version": version, "declared_blocks": total,
                                           "operations": len(operations), "new_blocks": new_blocks}


def unpack_partition(z, part, expanded_bytes, tmpdir):
    print(f"Replaying signed OTA payload: {part} ({expanded_bytes:,} bytes)", flush=True)
    transfer = z.read(part + ".transfer.list").decode("ascii")
    operations, expected_data, info = transfer_plan(transfer, expanded_bytes, part)
    dest = Path(tmpdir) / (part + ".img")
    # Sparse backing file: no real disk or block device is accessed.
    with open(dest, "w+b") as disk:
        disk.truncate(expanded_bytes)
        targets = [(offset, size) for op, offset, size in operations if op == "new"]
        current = 0
        filled = 0
        total = 0
        decoder = brotli.Decompressor()
        with z.open(part + ".new.dat.br") as compressed:
            for chunk in iter(lambda: compressed.read(512 * 1024), b""):
                decoded = memoryview(decoder.process(chunk))
                pos = 0
                while pos < len(decoded):
                    if current >= len(targets):
                        raise ValueError(f"Excess uncompressed new.dat bytes in {part}")
                    start, size = targets[current]
                    count = min(size - filled, len(decoded) - pos)
                    disk.seek(start + filled)
                    disk.write(decoded[pos:pos + count])
                    pos += count
                    filled += count
                    total += count
                    if filled == size:
                        current += 1
                        filled = 0
        if not decoder.is_finished() or total != expected_data or current != len(targets) or filled:
            raise ValueError(f"Truncated/mismatched OTA stream: expected {expected_data:,}, decoded {total:,}")
        disk.flush()
        os.fsync(disk.fileno())
    e2 = subprocess.run(["e2fsck", "-fn", str(dest)], text=True, capture_output=True)
    check(part + " reconstructed ext4 filesystem", e2.returncode == 0,
          ("fsck_exit=" + str(e2.returncode) + " " + (e2.stdout + e2.stderr)[-600:]).replace("\n", " "))
    info["decoded_new_dat_bytes"] = total
    info["ext4_fsck_exit"] = e2.returncode
    report["parts"][part] = info
    dest.unlink()


def audit(path):
    check("actual ROM archive exists", path.is_file() and path.stat().st_size > 1024**3, path.name)
    with zipfile.ZipFile(path) as z:
        names = z.namelist()
        members = set(names)
        check("no duplicate ZIP entries", len(names) == len(members))
        check("no unsafe ZIP paths", all(not p.startswith("/") and ".." not in Path(p).parts for p in names))
        check("no dynamic/super partition assets", not any("dynamic_partitions" in p or "super.img" in p for p in names))
        for p in PARTS:
            for ext in (".transfer.list", ".new.dat.br", ".patch.dat"):
                check(p + ext + " exists", p + ext in members)
        for k in KERNEL:
            check(k + ".img exists", k + ".img" in members)
        for name in ("sizes.json", "kernel.json", "META-INF/com/google/android/updater-script",
                     "META-INF/com/google/android/update-binary"):
            check(name + " exists", name in members)

        if report["failures"]:
            return

        sizes = json.loads(z.read("sizes.json"))
        check("exact seven partition-size entries", set(sizes) == EXPECTED)
        check("filesystem sizes aligned; kernel sizes positive", all(type(sizes[k]) is int and sizes[k] >= BLOCK and sizes[k] % BLOCK == 0 for k in PARTS) and all(type(sizes[k]) is int and sizes[k] >= 2048 for k in KERNEL))
        kernel = json.loads(z.read("kernel.json"))
        check("kernel target is S10+ beyond2lte", kernel.get("device") == "beyond2lte")
        for k in KERNEL:
            data = z.read(k + ".img")
            check(k + " image matches kernel manifest SHA-256",
                  hashlib.sha256(data).hexdigest() == kernel.get("sha256", {}).get(k + ".img"))
            check(k + " image fits declared size", len(data) == sizes[k])
        updater = z.read("META-INF/com/google/android/updater-script").decode()
        check("S10+ codename assertion", 'getprop("ro.product.device") == "beyond2lte"' in updater)
        check("SM-G975F model assertion", 'SM-G975F' in updater and 'SM-G975N' not in updater)
        actual_installs = re.findall(r'block_image_update\("/dev/block/by-name/([a-z0-9_]+)"', updater)
        check("four ordered physical-partition OTA writes", actual_installs == list(PARTS), actual_installs)
        raw_writes = re.findall(r'package_extract_file\("([a-z0-9_]+)\.img", "/dev/block/by-name/([a-z0-9_]+)"\)', updater)
        check("boot/dtb/dtbo direct writes target themselves", raw_writes == [(k, k) for k in KERNEL], raw_writes)
        check("update-binary is substantial", z.getinfo("META-INF/com/google/android/update-binary").file_size > 1024)
        cpu_gate = 'Unsupported CPU: Exynos9820 required' in updater
        guard_name = ("s10-install-guard.sh" if "s10-install-guard.sh" in members else
                      "s10-preflight.sh" if "s10-preflight.sh" in members else "")
        check("installer guard included", bool(guard_name))
        if guard_name:
            guard = z.read(guard_name).decode()
            check("partition guard executes before first block write",
                  updater.index('run_program("/tmp/' + guard_name + '")') < updater.index("block_image_update("))
            check("guard verifies physical device capacity", guard.count('capacity=$(blockdev --getsize64 "$device")') == 7)
            check("guard refuses aliasing", "Aliased partitions" in guard)
            check("guard refuses mounted partitions", "Partition is mounted" in guard)
        if not cpu_gate:
            report["warnings"].append("This old published ZIP has no CPU-only Exynos9820 assertion; the latest source version adds one. This package predates the fix.")
            print("WARN Existing release predates the CPU-only fix", flush=True)
        if guard_name == "s10-preflight.sh":
            report["warnings"].append("Old release still embeds s10-preflight.sh, unlike the latest generator's s10-install-guard.sh.")
        if report["failures"]:
            return

        with tempfile.TemporaryDirectory(prefix="s10-real-ota-") as td:
            for p in PARTS:
                try:
                    unpack_partition(z, p, sizes[p], td)
                except Exception as exc:
                    check(p + " signed OTA replay", False, repr(exc))
        print("Checking ZIP CRC for every signed archive member...", flush=True)
        bad = z.testzip()
        check("full signed ZIP CRC", bad is None, bad if bad else "all entries readable")


if __name__ == "__main__":
    archive = Path(sys.argv[1])
    out = Path(sys.argv[2])
    try:
        audit(archive)
    except Exception as exc:
        check("unhandled package audit exception", False, repr(exc))
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2) + "\n")
    print("SUMMARY:", len([c for c in report["checks"] if c["passed"]]),
          "passed /", len(report["failures"]), "failed /", len(report["warnings"]), "warnings")
    sys.exit(1 if report["failures"] else 0)
