#!/usr/bin/env bash
set -xe

# KASM images runs any script named "custom_startup.sh" at startup if it is
# located in /dockerstartup dir. This serves as the entrypoint for our custom
# image.

code-server \
    --auth none \
    --bind-addr 0.0.0.0:8080 \
    --disable-telemetry \
    --disable-update-check &

jupyter notebook \
    --port=8888 \
    --ip=0.0.0.0 \
    --no-browser \
    --NotebookApp.token='' \
    --NotebookApp.password='' &

jupyter lab \
    --port=8899 \
    --ip=0.0.0.0 \
    --no-browser \
    --NotebookApp.token='' \
    --NotebookApp.password='' &

wait