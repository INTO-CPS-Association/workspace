#!/usr/bin/env bash
set -e

rm -Rf ${STARTUPDIR}/audio_input
rm -Rf ${STARTUPDIR}/gamepad
rm -Rf ${STARTUPDIR}/jsmpeg
rm -Rf ${STARTUPDIR}/printer
rm -Rf ${STARTUPDIR}/recorder
rm -Rf ${STARTUPDIR}/smartcard
rm -Rf ${STARTUPDIR}/upload_server
rm -Rf ${STARTUPDIR}/webcam

apt-get clean
rm -rf /var/lib/apt/lists/*
rm -Rf /root/.cache/pip
rm -rf /tmp/*

# Remove Noto fonts to save space. These are very large and we don't use them.
rm -rf /usr/share/fonts/opentype/noto
rm -rf /usr/share/fonts/truetype/noto

# Remove unneeded locale files to save space. We only need English.
shopt -s extglob
rm -rf /usr/share/locale-langpack/!(en)
rm -rf /usr/share/locale/!(en)
rm /usr/lib/locale/locale-archive
localedef -i en_US -f UTF-8 en_US.UTF-8
