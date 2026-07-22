# Workspace member package dirs (mirrors PKG_SET in the Makefile).
pkg_set := "tools/c7n_gcp tools/c7n_kube tools/c7n_openstack tools/c7n_mailer tools/c7n_policystream tools/c7n_org tools/c7n_sphinxext tools/c7n_awscc tools/c7n_tencentcloud tools/c7n_azure tools/c7n_oci tools/c7n_left"

# Append (or replace) a +HASH local version segment on every workspace
# pyproject.toml, preserving each package's own base version, then regenerate
# c7n/version.py from the root pyproject. Usage: just append-hash 0d90f7a6f
append-hash hash:
    #!/usr/bin/env bash
    set -euo pipefail
    for d in . {{pkg_set}}; do
        sed -i -E 's|^(version = "[^"+]*)(\+[^"]*)?"|\1+{{hash}}"|' "$d/pyproject.toml"
    done
    uv run tools/dev/devpkg.py gen-version-file -p . -f c7n/version.py
    uv lock
