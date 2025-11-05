#!/usr/bin/env bash
set -xe

# Installs Jupyter and Python3

apt-get update && apt-get install -y \
    python3 \
    python3-pip
apt-get clean
rm -rf /var/lib/apt/lists/*

pip install --break-system-packages \
    jupyterlab \
    notebook