"""Spike S1: does NoncurrentVersionExpiration delete old versions?

Mirrors SeaweedFS's own TestLifecycleNoncurrentVersionExpiration: write
two versions of one key, age both filer entries, run one lifecycle pass
(``weed shell s3.lifecycle.run-shard``, driven from outside), then check
that the noncurrent version is gone and the current one is kept.

Usage: ``python lifecycle_probe.py prepare|verify``.
"""

# boto3, grpc and the generated filer_pb2 modules exist only in the
# spike image.
# pylint: disable=import-error

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

import boto3
import grpc
from botocore.config import Config

import filer_pb2
import filer_pb2_grpc

ENDPOINT = os.environ.get("S3_ENDPOINT", "http://seaweedfs:8333")
FILER = os.environ.get("FILER_GRPC", "seaweedfs:18888")
BUCKET = os.environ.get("S3_BUCKET", "dtaas-backup")
KEY = "user1/lifecycle/probe.txt"
STATE = Path(os.environ.get("SPIKE_OUT", "/spike-out")) / "lifecycle.json"
NONCURRENT_SINCE = "Seaweed-X-Amz-Noncurrent-Since-Ns"


def admin():
    """Return the operator's S3 client."""
    return boto3.client(
        "s3", endpoint_url=ENDPOINT, region_name="us-east-1",
        aws_access_key_id=os.environ["S3_ADMIN_ACCESS_KEY"],
        aws_secret_access_key=os.environ["S3_ADMIN_SECRET_KEY"],
        config=Config(s3={"addressing_style": "path"}))


def backdate(stub, version_id: str, days: int) -> None:
    """Age one version's filer entry by ``days``, as SeaweedFS's test does."""
    directory = f"/buckets/{BUCKET}/{KEY}.versions"
    name = f"v_{version_id}"
    entry = stub.LookupDirectoryEntry(filer_pb2.LookupDirectoryEntryRequest(
        directory=directory, name=name)).entry
    entry.attributes.mtime = int(time.time()) - days * 86400
    entry.attributes.mtime_ns = 0
    if NONCURRENT_SINCE in entry.extended:
        del entry.extended[NONCURRENT_SINCE]
    stub.UpdateEntry(filer_pb2.UpdateEntryRequest(directory=directory,
                                                  entry=entry))


def prepare() -> None:
    """Write v1 and v2, then make v1 noncurrent for 30 days."""
    s3 = admin()
    v1 = s3.put_object(Bucket=BUCKET, Key=KEY, Body=b"v1")["VersionId"]
    v2 = s3.put_object(Bucket=BUCKET, Key=KEY, Body=b"v2")["VersionId"]
    stub = filer_pb2_grpc.SeaweedFilerStub(grpc.insecure_channel(FILER))
    backdate(stub, v1, 400)
    backdate(stub, v2, 399)
    STATE.parent.mkdir(parents=True, exist_ok=True)
    STATE.write_text(json.dumps({"v1": v1, "v2": v2}))
    print(f"prepared {KEY}: v1={v1} (noncurrent), v2={v2} (current)")


def verify() -> int:
    """Pass when v1 expired and v2 is still the current version."""
    state = json.loads(STATE.read_text())
    listed = admin().list_object_versions(Bucket=BUCKET, Prefix=KEY)
    ids = {v["VersionId"]: v["IsLatest"] for v in listed.get("Versions", [])}
    v1_gone = state["v1"] not in ids
    v2_kept = ids.get(state["v2"]) is True
    print(f"{'PASS' if v1_gone else 'FAIL'}  noncurrent version expired")
    print(f"{'PASS' if v2_kept else 'FAIL'}  current version kept  {ids}")
    return 0 if v1_gone and v2_kept else 1


if __name__ == "__main__":
    if sys.argv[1:] == ["prepare"]:
        prepare()
        sys.exit(0)
    sys.exit(verify())
