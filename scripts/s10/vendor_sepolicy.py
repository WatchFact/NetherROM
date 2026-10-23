#!/usr/bin/env python3
"""Apply the S10 SNAP SELinux service rule only to a verified donor policy."""
from pathlib import Path
import sys

OLD = b'(allow snap_hidl hal_snap_service (service_manager (find)))'
NEW = b'(allow snap_hidl hal_snap_service (service_manager (add find)))'


def patch(path: Path) -> str:
    original = path.read_bytes()
    before, after = original.count(OLD), original.count(NEW)
    if before == 0 and after == 1:
        return 'already-patched'
    if before != 1 or after != 0:
        raise ValueError(f'Unknown or ambiguous S10 SNAP SELinux policy: old={before} new={after}')
    path.write_bytes(original.replace(OLD, NEW, 1))
    if path.read_bytes().count(NEW) != 1:
        raise ValueError('Failed to persist SNAP policy rule')
    return 'patched'


if __name__ == '__main__':
    print('S10 vendor SELinux SNAP service:', patch(Path(sys.argv[1])))
