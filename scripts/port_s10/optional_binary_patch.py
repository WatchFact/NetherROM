#!/usr/bin/env python3
"""Exact, bounded, non-destructive-to-other-bytes legacy firmware patcher.

Legacy camera/Bluetooth patches were written for a specific Android 16 donor.
A missing pattern on a different donor must not accidentally mutate unrelated
instructions. An exact match may be patched once; an unknown version is logged
as incompatible and left untouched, not misrepresented as functional.
"""
from __future__ import annotations

import argparse
from pathlib import Path

PATCHES = {
    "stagefright-video-svc": (
        "da4a0594e0031a2a22feff17",
        "da4a0594e0031a2a19000014",
    ),
    "stagefright-hdr10": (
        "010140f90a4d0594604d0034",
        "010140f90a4d05941f2003d5",
    ),
    "bluetooth-jni-legacy": (
        "1ff828ab5e39480500352800805228ab",
        "1ff828ab5e392a0000142800805228ab",
    ),
}


def patch(path: Path, feature: str) -> str:
    if feature not in PATCHES:
        raise ValueError(f"Unknown patch: {feature}")
    source_hex, target_hex = PATCHES[feature]
    old, new = bytes.fromhex(source_hex), bytes.fromhex(target_hex)
    if len(old) != len(new):
        raise ValueError(f"{feature}: byte lengths differ")
    if not path.is_file() or not path.stat().st_size:
        raise FileNotFoundError(f"{feature}: binary missing: {path}")
    data = path.read_bytes()
    count_old, count_new = data.count(old), data.count(new)
    if count_old == 1 and count_new == 0:
        path.write_bytes(data.replace(old, new, 1))
        return "patched"
    if count_old == 0 and count_new == 1:
        return "already-patched"
    if count_old == 0 and count_new == 0:
        # Do not crash a whole ROM build because of an outdated cosmetic/feature
        # bypass; also never claim that its affected functionality works.
        return "unsupported-donor"
    raise ValueError(
        f"{feature}: ambiguous pattern count (old={count_old}, new={count_new}); "
        "refusing to patch"
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("feature", choices=sorted(PATCHES))
    parser.add_argument("file", type=Path)
    args = parser.parse_args()
    result = patch(args.file, args.feature)
    if result == "unsupported-donor":
        print(
            f"WARNING: {args.feature}: expected instruction sequence absent in "
            f"{args.file}. Leaving donor binary intact; associated camera or "
            "Bluetooth functionality is NOT validated."
        )
    else:
        print(f"{args.feature}: {result}: {args.file}")


if __name__ == "__main__":
    main()
