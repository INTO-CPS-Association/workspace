#!/usr/bin/env bash
set -euo pipefail
source "$(dirname "$0")/../arch.sh"

NODE_VERSION=22.12.0   # pin; update deliberately
NODE_DIST="node-v${NODE_VERSION}-linux-${NODE_ARCH}"
NODE_URL="https://nodejs.org/dist/v${NODE_VERSION}/${NODE_DIST}.tar.xz"

curl -fsSL "${NODE_URL}" -o /tmp/node.tar.xz
# TODO: verify against SHASUMS256.txt for the pinned version
tar -xJf /tmp/node.tar.xz -C /usr/local --strip-components=1
rm /tmp/node.tar.xz

npm install -g typescript ts-node @types/node

node --version && npm --version && tsc --version