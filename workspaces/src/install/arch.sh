#!/bin/bash
set -euo pipefail

# Docker buildx sets TARGETARCH (amd64|arm64); fall back to dpkg for
# non-buildx local builds.
ARCH="${TARGETARCH:-$(dpkg --print-architecture)}"

case "${ARCH}" in
  amd64|x86_64)  NODE_ARCH="x64";   JAVA_ARCH="x64";     GO_STYLE_ARCH="amd64"; FIREFOX_ARCH="x86_64";  VSCODE_ARCH="amd64" ;;
  arm64|aarch64) NODE_ARCH="arm64"; JAVA_ARCH="aarch64"; GO_STYLE_ARCH="arm64"; FIREFOX_ARCH="aarch64"; VSCODE_ARCH="arm64" ;;
  *) echo "ERROR: unsupported architecture: ${ARCH}" >&2; exit 1 ;;
esac
export ARCH NODE_ARCH JAVA_ARCH GO_STYLE_ARCH FIREFOX_ARCH VSCODE_ARCH