#!/usr/bin/env bash
set -xe

# Installs Jupyter and Python3

DEBIAN_FRONTEND=noninteractive apt-get update && apt-get install -y --no-install-recommends\
    python3 \
    python3-pip

# --break-system-packages is required on systems that enforce PEP 668
# (Ubuntu 24.04+). Older Ubuntu/pip versions do not recognise the flag,
# so fall back to a plain install when it is rejected.
pip install --break-system-packages --no-cache-dir \
    jupyterlab \
    notebook || \
pip install --no-cache-dir \
    jupyterlab \
    notebook