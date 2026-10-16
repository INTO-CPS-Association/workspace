#!/usr/bin/env bash
set -e

echo "Installing Admin Service"

# Installed like Jupyter: a venv under /opt, with the entry point linked into
# /usr/local/bin, which is on the PATH of every user at runtime. pip builds
# the wheel itself through the poetry-core backend in pyproject.toml, so
# neither Poetry nor pipx is needed in the image. As before, the wheel's
# dependency ranges decide the versions; poetry.lock is not consulted.
DEBIAN_FRONTEND=noninteractive apt-get update && apt-get install -y --no-install-recommends \
    python3-venv \
    python-is-python3

if [[ ! -f "${ADMIN_DIR}/pyproject.toml" ]]; then
    echo "Error: pyproject.toml not found in ${ADMIN_DIR}"
    ls -la "${ADMIN_DIR}"
    exit 1
fi

python3 -m venv /opt/workspace-admin
/opt/workspace-admin/bin/pip install --no-cache-dir "${ADMIN_DIR}"
ln -s /opt/workspace-admin/bin/workspace-admin /usr/local/bin/workspace-admin

# Verify installation
if ! command -v workspace-admin &> /dev/null; then
    echo "Error: workspace-admin command not found after installation"
    exit 1
fi

workspace-admin --version

# Cleanup: the sources were only needed for the build.
rm -rf "${ADMIN_DIR}" /var/lib/apt/lists/*

echo "Admin Service installation complete"
