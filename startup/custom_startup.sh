#!/usr/bin/env bash
set -xe

# KASM images runs any script named "custom_startup.sh" at startup if it is
# located in /dockerstartup dir. This serves as the entrypoint for our custom
# image.

code-server --auth none --bind-addr 0.0.0.0:8080