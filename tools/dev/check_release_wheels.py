# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
"""
Pre-publish sanity checks for built wheels.

Run before pushing wheels to a release repository. Refuses to proceed if:

  * any wheel's PEP 440 version is not a pre-release (guards against
    publishing a release-shaped version to the pre-release channel)
  * the c7n wheel's embedded c7n/version.py disagrees with the wheel's
    own version (consumed at runtime by user-agent strings and
    `custodian version`; a common drift point when pyproject.toml is
    bumped without re-running `make pkg-increment`)
"""

import argparse
import re
import sys
import zipfile
from pathlib import Path

from packaging.version import InvalidVersion, Version


VERSION_RE = re.compile(r'^version\s*=\s*"([^"]+)"', re.M)


def wheel_version(wheel: Path) -> str:
    # PEP 427: {distribution}-{version}(-{build})?-{python}-{abi}-{platform}.whl
    return wheel.name.split("-")[1]


def check_prerelease(wheel: Path) -> str | None:
    version_str = wheel_version(wheel)
    try:
        v = Version(version_str)
    except InvalidVersion:
        return f"unparseable version {version_str!r}"
    if not v.is_prerelease:
        return f"{v} is not a PEP 440 pre-release"
    return None


def check_c7n_embedded_version(wheel: Path) -> str | None:
    with zipfile.ZipFile(wheel) as zf:
        embedded = zf.read("c7n/version.py").decode()
    match = VERSION_RE.search(embedded)
    if not match:
        return "c7n/version.py has no version assignment"
    if match.group(1) != wheel_version(wheel):
        return (
            f"c7n/version.py says {match.group(1)!r} but wheel is "
            f"{wheel_version(wheel)!r} — run `make pkg-increment` or "
            f"`uv run tools/dev/devpkg.py gen-version-file -p . -f c7n/version.py`"
        )
    return None


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("dist_dir", help="Directory containing .whl files")
    args = parser.parse_args()

    wheels = sorted(Path(args.dist_dir).glob("*.whl"))
    if not wheels:
        sys.stderr.write(f"No wheels found in {args.dist_dir}/.\n")
        sys.exit(1)

    bad: list[tuple[str, str]] = []
    for whl in wheels:
        reason = check_prerelease(whl)
        if reason:
            bad.append((whl.name, reason))

    for whl in wheels:
        if whl.name.startswith("c7n-"):
            reason = check_c7n_embedded_version(whl)
            if reason:
                bad.append((whl.name, reason))

    if bad:
        sys.stderr.write("Refusing to publish:\n")
        for name, reason in bad:
            sys.stderr.write(f"  {name}: {reason}\n")
        sys.exit(1)

    print(f"All {len(wheels)} wheel(s) are pre-release and version-consistent.")


if __name__ == "__main__":
    main()
