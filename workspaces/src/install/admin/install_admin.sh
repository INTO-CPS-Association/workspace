#!/usr/bin/env bash
set -euo pipefail

echo "Installing Admin Service"

# The admin service gets its own venv under /opt, like the pip-venv packages
# in dependencies.lock, with its entry point linked into /usr/local/bin, which
# is on the PATH of every user at runtime. pip builds the wheel through the
# poetry-core backend declared in pyproject.toml; the dependency ranges in
# pyproject.toml decide the versions. python3-venv comes from
# packages/install_python.sh.
VENV_DIR=/opt/workspace-admin

if [[ ! -f "${ADMIN_DIR}/pyproject.toml" ]]; then
    echo "Error: pyproject.toml not found in ${ADMIN_DIR}" >&2
    ls -la "${ADMIN_DIR}" >&2
    exit 1
fi

python3 -m venv "${VENV_DIR}"
"${VENV_DIR}/bin/pip" install --no-cache-dir "${ADMIN_DIR}"
ln -sf "${VENV_DIR}/bin/workspace-admin" /usr/local/bin/workspace-admin

if ! command -v workspace-admin &> /dev/null; then
    echo "Error: workspace-admin command not found after installation" >&2
    exit 1
fi

workspace-admin --version

# The sources are only needed for the build.
rm -rf "${ADMIN_DIR}"

echo "Admin Service installation complete"
