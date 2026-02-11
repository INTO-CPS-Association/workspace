#!/usr/bin/env bash
set -e

echo "Installing Admin Service"

# Install Poetry and pipx
DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
    python3-poetry \
    pipx

poetry --version
pipx --version

# Copy admin service to /opt/admin
# INST_DIR is /dockerstartup/install, admin source is at src/admin
mkdir -p /opt/admin
cp -r "${INST_DIR}/../admin/"* /opt/admin/

# Verify pyproject.toml exists
if [ ! -f /opt/admin/pyproject.toml ]; then
    echo "Error: pyproject.toml not found in /opt/admin"
    ls -la /opt/admin/
    exit 1
fi

# Build the wheel package
cd /opt/admin
poetry build

# Install the wheel package using pipx
# Find the built wheel file
WHEEL_FILE=$(find /opt/admin/dist -name "*.whl" -type f | head -n 1)
if [ -z "$WHEEL_FILE" ]; then
    echo "Error: No wheel file found in /opt/admin/dist"
    exit 1
fi

echo "Installing wheel: $WHEEL_FILE"
pipx install "$WHEEL_FILE"

# Verify installation
if ! command -v workspace-admin &> /dev/null; then
    echo "Error: workspace-admin command not found after installation"
    exit 1
fi

workspace-admin --version

echo "Admin Service installation complete"
