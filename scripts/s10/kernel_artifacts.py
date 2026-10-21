#!/usr/bin/env python3
"""Import only checksummed images produced for this device by this Actions run."""
import hashlib
import json
import shutil
import sys
from pathlib import Path

KERNEL_REV = "9a0a792d227c8ae6cddac0c9d68a8bb9782c44cb"
DEVICES = ("beyond0lte", "beyond1lte", "beyond2lte", "beyondx")


def validate(source, device):
    if device not in DEVICES:
        raise ValueError("Unsupported S10 target")
    info = json.loads((source / "kernel.json").read_text())
    if info["device"] != device or info["revision"] != KERNEL_REV:
        raise ValueError("Wrong kernel target or revision")
    if info["kernelsu"] is not False or info["ext4"] is not True:
        raise ValueError("Kernel configuration does not match this port")
    for name, magic in (("boot.img", b"ANDROID!"), ("dtb.img", bytes.fromhex("d7b7ab1e")),
                        ("dtbo.img", bytes.fromhex("d7b7ab1e"))):
        file = source / name
        data = file.read_bytes()
        if not data.startswith(magic) or len(data) < 2048:
            raise ValueError(f"Invalid {name} image")
        if hashlib.sha256(data).hexdigest() != info["sha256"][name]:
            raise ValueError(f"Corrupted kernel artifact: {name}")
    return info


def install(source, destination, device):
    validate(source, device)
    destination.mkdir(parents=True, exist_ok=True)
    for name in ("boot.img", "dtb.img", "dtbo.img"):
        shutil.copy2(source / name, destination / name)
    shutil.copy2(source / "kernel.json", destination / "kernel.json")


if __name__ == "__main__":
    install(Path(sys.argv[1]), Path(sys.argv[2]), sys.argv[3])
