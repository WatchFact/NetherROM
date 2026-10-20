#!/usr/bin/env python3
"""Byte-preserving camera metadata reference patch for Samsung's ELF library."""
from pathlib import Path
import sys

OLD = b"system/cameradata/portrait_data/single_bokeh_feature.json"
NEW = b"system/cameradata/portrait_data/nexus_bokeh_feature.json\x00"

def apply(path: Path) -> str:
    if len(OLD) != len(NEW):
        raise ValueError("PortraitSolution replacement changes byte length")
    data = path.read_bytes()
    if not data.startswith(b"\x7fELF"):
        raise ValueError(f"Not an ELF camera library: {path}")
    old_count, new_count = data.count(OLD), data.count(NEW)
    if old_count == 1 and new_count == 0:
        path.write_bytes(data.replace(OLD, NEW, 1))
        return "patched"
    if old_count == 0 and new_count == 1:
        return "already-patched"
    if old_count == 0 and new_count == 0:
        return "unsupported-donor"
    raise ValueError(f"Ambiguous binary path count: old={old_count}, new={new_count}")

if __name__ == "__main__":
    status = apply(Path(sys.argv[1]))
    print(f"PortraitSolution path patch: {status}")
    if status == "unsupported-donor":
        print("WARNING: Photo Editor path bypass not applicable to this One UI donor")
