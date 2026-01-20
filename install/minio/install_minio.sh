#!/usr/bin/env bash
set -xe

# Installs MinIO

curl -L https://dl.min.io/aistor/mc/release/linux-amd64/mc \
  --create-dirs \
  -o /bin/mc

chmod +x /bin/mc

mc alias set \
  dtaas-commons \
  {STORE_ENDPOINT} \
  {KEY_ID} \
  {SECRET_KEY} \
  --api S3v4