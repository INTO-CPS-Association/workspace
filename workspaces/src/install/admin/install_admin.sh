#!/usr/bin/env bash
set -e

echo "Installing Admin Service"

# Install Poetry
# shellcheck disable=SC2312
curl -sSL https://install.python-poetry.org | python3 - --version 1.8.5
export PATH="/root/.local/bin:${PATH}"

# Copy admin service to /opt/admin
# INST_DIR is /dockerstartup/install, so we need ../admin from there
mkdir -p /opt/admin
cp -r "${INST_DIR}/../admin" /opt/

# Install dependencies using Poetry
cd /opt/admin
poetry config virtualenvs.in-project true
poetry install --only main --no-root

echo "Admin Service installation complete"
