FROM python:3.12.9-slim

ARG RCLONE_VERSION=1.75.2
ARG RCLONE_SHA256=349ac8fba6ff65d6247043f1750cdcb518ec5d500ef91463a10d37c0ccdf3702
ARG SEAWEEDFS_VERSION=4.48
ARG FILER_PROTO_SHA256=bec48f9b5f84b2dafcb882382933dbe5584c2bccb011fe6f8dd18f0b8b1fd2a9

SHELL ["/bin/bash", "-o", "pipefail", "-c"]

# rclone is installed the way the workspace image will install it: the
# release zip, checked against its published SHA-256.
RUN python -c "import urllib.request; urllib.request.urlretrieve('https://github.com/rclone/rclone/releases/download/v${RCLONE_VERSION}/rclone-v${RCLONE_VERSION}-linux-amd64.zip', '/tmp/rclone.zip')" \
    && echo "${RCLONE_SHA256}  /tmp/rclone.zip" | sha256sum -c - \
    && python -m zipfile -e /tmp/rclone.zip /tmp \
    && install -m 0755 "/tmp/rclone-v${RCLONE_VERSION}-linux-amd64/rclone" /usr/local/bin/rclone \
    && rm -rf /tmp/rclone*

RUN pip install --no-cache-dir boto3==1.43.114 "pyjwt[crypto]==2.15.1" \
    grpcio==1.76.0 grpcio-tools==1.76.0

WORKDIR /spike
# The lifecycle probe talks to the filer over gRPC: generate its client
# from the release's weed/pb/filer.proto, checked against its SHA-256.
RUN python -c "import urllib.request; urllib.request.urlretrieve('https://raw.githubusercontent.com/seaweedfs/seaweedfs/${SEAWEEDFS_VERSION}/weed/pb/filer.proto', 'filer.proto')" \
    && echo "${FILER_PROTO_SHA256}  filer.proto" | sha256sum -c - \
    && python -m grpc_tools.protoc -I. --python_out=. --grpc_python_out=. filer.proto \
    && rm filer.proto
COPY spike_s1.py lifecycle_probe.py s2_rclone_flags.sh ./

ENTRYPOINT ["python", "spike_s1.py"]
CMD ["main"]
