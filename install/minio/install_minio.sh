#!/usr/bin/env bash
set -xe

# Installs MinIO

curl -L https://dl.min.io/aistor/mc/release/linux-amd64/mc \
  --create-dirs \
  -o /bin/mc

chmod +x /bin/mc