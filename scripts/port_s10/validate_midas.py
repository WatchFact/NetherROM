#!/usr/bin/env python3
"""Verify Exynos9820 MIDAS uses an actually supported One UI donor identity.

ArtisanROM's inherited sed s/$SOURCE_CODENAME/dummy fails when that
nonexistent variable is empty. Worse, globally swapping r9s with e2s in the
model table changes unrelated hardware-specific compatibility entries.

The S24+ One UI 8.5 source sets ro.product.device=e2s in the assembled
system build.prop. The p3sxxx MIDAS JSON already lists e2s as supported.
Validate both without rewriting/claiming support for unmatched devices.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

PROP = "ro.product.device"
CODENAME = re.compile(r"^[a-z][a-z0-9_]{1,31}$")

def verify(config_path: Path, build_prop_path: Path) -> str:
    if not config_path.is_file() or not build_prop_path.is_file():
        raise FileNotFoundError("MIDAS JSON or assembled system build.prop missing")
    config = json.loads(config_path.read_text(encoding="utf-8"))
    if config.get("device_property") != PROP:
        raise ValueError("MIDAS config checks an unexpected device property")
    found = [
        line.split("=", 1)[1].strip()
        for line in build_prop_path.read_text(encoding="utf-8").splitlines()
        if line.startswith(PROP + "=")
    ]
    if len(found) != 1 or not CODENAME.fullmatch(found[0]):
        raise ValueError(f"Malformed/ambiguous {PROP}: {found!r}")
    codename = found[0]
    devices = config.get("midasSR_devices")
    if not isinstance(devices, list) or not all(isinstance(x, str) for x in devices):
        raise ValueError("MIDAS supported device array invalid")
    if codename not in devices:
        raise ValueError(
            f"MIDAS donor device {codename!r} is not supported by its model table; "
            "do not fake compatibility with arbitrary string substitutions"
        )
    return codename

if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit("Usage: validate_midas.py <midas_config.json> <system/build.prop>")
    name = verify(Path(sys.argv[1]), Path(sys.argv[2]))
    print(f"MIDAS donor model valid: {name}; configuration left unchanged")
