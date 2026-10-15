#!/usr/bin/env bash
set -euo pipefail
source "$(dirname "$0")/../arch.sh"

export DEBIAN_FRONTEND=noninteractive
apt-get update
apt-get install -y --no-install-recommends \
  python3 python3-venv python3-pip python3-dev build-essential
rm -rf /var/lib/apt/lists/*

# Fast, arch-aware installer/resolver for per-user environments.
# uv publishes native amd64 and arm64 builds; its installer auto-detects.
curl -LsSf https://astral.sh/uv/install.sh | \
  UV_INSTALL_DIR=/usr/local/bin sh

python3 --version && pip3 --version && uv --version