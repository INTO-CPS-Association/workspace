#!/usr/bin/env bash
set -xe

echo_latest_version() {
  # https://gist.github.com/lukechilds/a83e1d7127b78fef38c2914c4ececc3c#gistcomment-2758860
  version="$(curl -fsSLI -o /dev/null -w "%{url_effective}" https://github.com/coder/code-server/releases/latest)"
  version="${version#https://github.com/coder/code-server/releases/tag/}"
  version="${version#v}"
  echo "$version"
}

fetch() {
  URL="$1"
  FILE="$2"

  if [ -e "$FILE" ]; then
    echoh "+ Reusing $FILE"
    return
  fi

  mkdir -p "$CACHE_DIR"
  curl \
    -#fL \
    -o "$FILE.incomplete" \
    -C - \
    "$URL"
  mv "$FILE.incomplete" "$FILE"
}

CACHE_DIR=/tmp/code-server-cache
VERSION=${VERSION:-$(echo_latest_version)}
ARCH=amd64


fetch "https://github.com/coder/code-server/releases/download/v$VERSION/code-server_${VERSION}_$ARCH.deb" \
    "$CACHE_DIR/code-server_${VERSION}_$ARCH.deb"
dpkg -i "$CACHE_DIR/code-server_${VERSION}_$ARCH.deb"