#!/usr/bin/env bash
set -xe

export HOME=/home/${MAIN_USER}

sudo usermod --login ${MAIN_USER} --move-home --home ${HOME} kasm-user
sudo groupmod --new-name ${MAIN_USER} kasm-user

cd ${HOME}

bash $1 $2 $3