#!/usr/bin/env python3
"""Migrate the 3.1.0 Extra Dim gates without depending on dex file numbers."""
import re
import sys
from pathlib import Path


def rewrite(text):
    # Remove only the original Exynos9820/9825 exclusion entries. Registers
    # remain allocated; no other device entries or feature checks are changed.
    text, excluded = re.subn(
        r'(?m)^\s*const-string(?:/jumbo)? (v\d+), "(?:beyond|d1|d2)"\s*\n'
        r'\s*invoke-virtual \{v\d+, \1\}, Ljava/util/HashSet;->add\(Ljava/lang/Object;\)Z\s*\n',
        '\n', text)
    # Replace the result, preserving the surrounding method's register uses.
    text, protected = re.subn(
        r'(?m)^\s*const-string(?:/jumbo)? (v\d+), "ro\.surface_flinger\.protected_contents"\s*\n'
        r'(?:\s*const/4 v\d+, 0x0\s*\n)?'
        r'\s*invoke-static \{\1, v\d+\}, Landroid/os/SystemProperties;->getBoolean\(Ljava/lang/String;Z\)Z\s*\n'
        r'\s*move-result (v\d+)\s*\n',
        lambda m: '\n    const/4 '+m[2]+', 0x1\n\n', text)
    if '"ro.surface_flinger.protected_contents"' in text:
        raise ValueError('Unrecognized Extra Dim protected-content gate')
    return text, excluded, protected


if __name__ == '__main__':
    for directory, name in ((Path(sys.argv[1]), 'SecAccessibilityUtils.smali'),
                            (Path(sys.argv[2]), 'ReduceBrightColorsTile.smali')):
        matches = list(directory.rglob(name))
        if len(matches) != 1:
            raise ValueError('Missing or ambiguous Extra Dim class: '+name)
        path = matches[0]
        text, excluded, protected = rewrite(path.read_text())
        path.write_text(text)
        print(f'{name}: {excluded} legacy exclusions and {protected} content gates migrated')
