"""Fail when a production Python dependency's license isn't one the AGPL-3.0 can include.

    cd backend && uv run --no-dev python ../scripts/check-python-licenses.py

Each package's license is read from its metadata: the SPDX expression, else its license classifiers,
else the first line of its License field. One with none of these fails until it's listed in
REVIEWED, with what its repository says.
"""

from __future__ import annotations

import importlib.metadata
import re
import sys

# Licenses the AGPL-3.0 may include, as they appear in expressions and classifiers.
ALLOWED = re.compile(
    r"\b(MIT|MIT-0|Apache|BSD|0BSD|ISC|PSF|Python Software Foundation|CNRI-Python|MPL|Mozilla Public License 2\.0"
    r"|LGPL|GNU Lesser General Public License v3|CC0|Zlib|Unlicense|AGPL-3\.0)",
    re.IGNORECASE,
)
# Checked by hand: packages whose metadata names no license.
REVIEWED: dict[str, str] = {}
# This project itself.
OWN = {"inskect-api"}


def licenses(dist: importlib.metadata.Distribution) -> list[str]:
    meta = dist.metadata
    if expression := meta.get("License-Expression"):
        return [expression]
    classifiers = [c.split("::")[-1].strip() for c in meta.get_all("Classifier") or [] if c.startswith("License ::")]
    if classifiers:
        return classifiers
    text = (meta.get("License") or "").strip().splitlines()
    return [text[0]] if text and text[0] != "UNKNOWN" else []


def main() -> int:
    problems = []
    for dist in sorted(importlib.metadata.distributions(), key=lambda d: d.metadata["Name"].lower()):
        name = dist.metadata["Name"]
        if name in OWN or name in REVIEWED:
            continue
        found = licenses(dist)
        # Every part of an AND must be allowed; for an OR, one is enough.
        ok = bool(found) and all(
            any(ALLOWED.search(choice) for choice in re.split(r"\s+OR\s+|;", part)) for license in found for part in re.split(r"\s+AND\s+", license)
        )
        if not ok:
            problems.append(f"{name} {dist.version}: {', '.join(found) or 'no license in its metadata'}")
    for problem in problems:
        print(f"::error::{problem}")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
