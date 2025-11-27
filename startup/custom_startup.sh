#!/usr/bin/env bash
set -xe

# KASM images runs any script named "custom_startup.sh" at startup if it is
# located in /dockerstartup dir. This serves as the entrypoint for our custom
# image.

sudo nginx &

# Set user password if supplied.
# NOTE: User has sudo permissions by default. Unprotected user is unprotected
# root access.
if [[ -n "$USER_PW" ]]; then
    echo -e "${USER_PW}\n${USER_PW}\n" | passwd
fi

ln -s $PERSISTENT_DIR $HOME/Desktop/workspace

code-server \
    --auth none \
    --port ${CODE_SERVER_PORT} \
    --disable-telemetry \
    --disable-update-check &

jupyter notebook &

wait