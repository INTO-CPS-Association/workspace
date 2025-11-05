#!/usr/bin/env bash
set -xe

# KASM images runs any script named "custom_startup.sh" at startup if it is
# located in /dockerstartup dir. This serves as the entrypoint for our custom
# image.

# Set user password if supplied.
# NOTE: User has sudo permissions by default. Unprotected user is unprotected
# root access.
if [[ -n "$USER_PW" ]]; then
    echo -e "${USER_PW}\n${USER_PW}\n" | passwd
fi

code-server \
    --auth none \
    --bind-addr 0.0.0.0:${CODE_SERVER_PORT} \
    --disable-telemetry \
    --disable-update-check &

jupyter notebook \
    --port=${JUPYTER_NOTEBOOK_PORT} \
    --ip=0.0.0.0 \
    --no-browser \
    --ServerApp.token='' \
    --ServerApp.password='' &

jupyter lab \
    --port=${JUPYTER_LAB_PORT} \
    --ip=0.0.0.0 \
    --no-browser \
    --ServerApp.token='' \
    --ServerApp.password='' &

wait