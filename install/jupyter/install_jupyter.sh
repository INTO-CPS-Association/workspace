#!/usr/bin/env bash
set -xe

# Installs Jupyter and Python3

apt-get update && apt-get install -y \
    python3 \
    python3-pip \
    python3-venv \
    python3-dev \
    python3-setuptools \
    python3-wheel \
    && rm -rf /var/lib/apt/lists/*

pip install --break-system-packages \
    jupyter \
    jupyterlab \
    notebook \
    ipywidgets \
    jupyter-contrib-nbextensions \
    jupyter-nbextensions-configurator \
    jupyterlab-git \
    jupyterlab-lsp \
    python-lsp-server[all]