#!/usr/bin/env bash
set -xe

# Modified version of the base code-server install script.
# Trimmed down to only what is needed for our usecase.

echo_latest_version() {
  # https://gist.github.com/lukechilds/a83e1d7127b78fef38c2914c4ececc3c#gistcomment-2758860
  version="$(curl -fsSLI -o /dev/null -w "%{url_effective}" https://github.com/coder/code-server/releases/latest)"
  version="${version#https://github.com/coder/code-server/releases/tag/}"
  version="${version#v}"
  echo "${version}"
}

fetch() {
  URL="$1"
  FILE="$2"

  if [[ -e "${FILE}" ]]; then
    echoh "+ Reusing ${FILE}"
    return
  fi

  mkdir -p "${CACHE_DIR}"
  curl \
    -#fL \
    -o "${FILE}.incomplete" \
    -C - \
    "${URL}"
  mv "${FILE}.incomplete" "${FILE}"
}

CACHE_DIR=/tmp/code-server-cache
VERSION=${VERSION:-$(set -e; echo_latest_version)}

# Use TARGETARCH if available (set by Docker Buildx), otherwise detect architecture
# TARGETARCH will be 'amd64' or 'arm64' from Docker Buildx
ARCH="${TARGETARCH:-amd64}"

# code-server uses the same architecture naming as Docker (amd64/arm64)
# so we can use TARGETARCH directly

fetch "https://github.com/coder/code-server/releases/download/v${VERSION}/code-server_${VERSION}_${ARCH}.deb" \
    "${CACHE_DIR}/code-server_${VERSION}_${ARCH}.deb"
dpkg -i "${CACHE_DIR}/code-server_${VERSION}_${ARCH}.deb"

rm -rf /tmp/code-server-cache