"""Spike S1/S2: SeaweedFS and rclone behaviour for workspace backups.

Runs inside the test compose on the ``users`` network with the network
alias ``login-relay``, so the committed ``seaweedfs/iam.json`` trusts it
unchanged. It plays login-relay's storage-pass role (ES256 JWTs and a
JWKS), then checks SeaweedFS and rclone against the design in
``docs/design/storage``. Prints one line per check and a JSON summary.

Usage: ``python spike_s1.py [main|after-restart]``.
"""

# boto3, botocore and jwt are installed only in the spike image.
# pylint: disable=import-error

from __future__ import annotations

import base64
import functools
import hashlib
import http.server
import json
import os
import shutil
import subprocess
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

import boto3
import jwt
from botocore import UNSIGNED
from botocore.config import Config
from botocore.exceptions import ClientError
from cryptography.hazmat.primitives.asymmetric import ec

ENDPOINT = os.environ.get("S3_ENDPOINT", "http://seaweedfs:8333")
BUCKET = os.environ.get("S3_BUCKET", "dtaas-backup")
ISSUER = "http://login-relay:8080"
AUDIENCE = "workspace-backup"
ROLE_ARN = "arn:aws:iam::role/WorkspaceBackup"
ADMIN_KEY = os.environ["S3_ADMIN_ACCESS_KEY"]
ADMIN_SECRET = os.environ["S3_ADMIN_SECRET_KEY"]
OUT = Path(os.environ.get("SPIKE_OUT", "/spike-out"))

RESULTS: list[dict[str, Any]] = []


def record(name: str, ok: bool, detail: str = "") -> None:
    """Print and keep one check result."""
    RESULTS.append({"check": name, "ok": ok, "detail": detail})
    print(f"{'PASS' if ok else 'FAIL'}  {name}  {detail}", flush=True)


def error_code(exc: Exception) -> str:
    """Return the S3 error code of a botocore error, else its class name."""
    if isinstance(exc, ClientError):
        return exc.response.get("Error", {}).get("Code", "ClientError")
    return type(exc).__name__


def expect(name: str, call: Callable[[], Any], allowed: bool) -> Any:
    """Run an S3 call and record whether it was allowed as expected."""
    try:
        result = call()
    except Exception as exc:  # pylint: disable=broad-except
        record(name, not allowed, f"denied: {error_code(exc)}")
        return None
    record(name, allowed, "allowed")
    return result


# --- Fake login-relay: keys, JWKS, storage passes ---------------------------


def new_key() -> ec.EllipticCurvePrivateKey:
    """Generate a P-256 key, as login-relay's signing key."""
    return ec.generate_private_key(ec.SECP256R1())


def public_jwk(key: ec.EllipticCurvePrivateKey, kid: str) -> dict[str, str]:
    """Return the public half of ``key`` as a JWK."""
    numbers = key.public_key().public_numbers()

    def b64(value: int) -> str:
        raw = value.to_bytes(32, "big")
        return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()

    return {"kty": "EC", "crv": "P-256", "alg": "ES256", "use": "sig",
            "kid": kid, "x": b64(numbers.x), "y": b64(numbers.y)}


class Issuer:
    """Serves the JWKS and counts how often SeaweedFS fetches it."""

    def __init__(self) -> None:
        self.keys: dict[str, ec.EllipticCurvePrivateKey] = {}
        self.published: list[str] = []
        self.fetches = 0

    def publish(self, *kids: str) -> None:
        """Publish exactly these key ids in the JWKS."""
        self.published = list(kids)

    def jwks(self) -> dict[str, Any]:
        """Return the current JWKS document."""
        return {"keys": [public_jwk(self.keys[k], k) for k in self.published]}

    def mint(self, user: str, *,  # pylint: disable=too-many-arguments
             kid: str = "2026-10", aud: Any = AUDIENCE,
             iss: str = ISSUER, lifetime: int = 300,
             extra: dict[str, Any] | None = None) -> str:
        """Return a storage pass for ``user`` as login-relay will issue it."""
        now = int(time.time())
        claims = {"iss": iss, "aud": aud, "sub": user,
                  "preferred_username": user, "iat": now,
                  "exp": now + lifetime}
        claims.update(extra or {})
        return jwt.encode(claims, self.keys[kid], algorithm="ES256",
                          headers={"kid": kid})


ISSUER_STATE = Issuer()


class Handler(http.server.BaseHTTPRequestHandler):
    """Answers the two discovery documents SeaweedFS may read."""

    def do_GET(self) -> None:  # pylint: disable=invalid-name
        """Serve JWKS and OpenID configuration."""
        if self.path == "/.well-known/jwks.json":
            ISSUER_STATE.fetches += 1
            body = ISSUER_STATE.jwks()
        elif self.path == "/.well-known/openid-configuration":
            body = {"issuer": ISSUER,
                    "jwks_uri": f"{ISSUER}/.well-known/jwks.json"}
        elif self.path == "/health":
            body = {"status": "ok"}
        else:
            self.send_error(404)
            return
        data = json.dumps(body).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *args: Any) -> None:  # pylint: disable=arguments-differ
        """Keep the output to check results."""


def start_issuer() -> None:
    """Serve the fake login-relay on port 8080 in a daemon thread."""
    server = http.server.ThreadingHTTPServer(("0.0.0.0", 8080), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()


# --- S3 and STS clients ------------------------------------------------------


def s3_client(key: str, secret: str, token: str | None = None) -> Any:
    """Return a path-style S3 client for SeaweedFS."""
    return boto3.client(
        "s3", endpoint_url=ENDPOINT, region_name="us-east-1",
        aws_access_key_id=key, aws_secret_access_key=secret,
        aws_session_token=token,
        config=Config(s3={"addressing_style": "path"},
                      retries={"max_attempts": 1}))


def admin() -> Any:
    """Return the operator's S3 client."""
    return s3_client(ADMIN_KEY, ADMIN_SECRET)


def sts_client() -> Any:
    """Return an unsigned STS client; AssumeRoleWithWebIdentity is unsigned."""
    return boto3.client("sts", endpoint_url=ENDPOINT, region_name="us-east-1",
                        config=Config(signature_version=UNSIGNED,
                                      retries={"max_attempts": 1}))


def assume(token: str, role_arn: str = ROLE_ARN,
           duration: int = 3600) -> dict[str, Any]:
    """Exchange a storage pass for temporary S3 keys."""
    return sts_client().assume_role_with_web_identity(
        RoleArn=role_arn, RoleSessionName="workspace-backup",
        WebIdentityToken=token, DurationSeconds=duration)


def user_s3(user: str) -> tuple[Any, dict[str, str]]:
    """Return an S3 client with ``user``'s STS keys, and the keys."""
    creds = assume(ISSUER_STATE.mint(user))["Credentials"]
    client = s3_client(creds["AccessKeyId"], creds["SecretAccessKey"],
                       creds["SessionToken"])
    return client, creds


# --- Checks -----------------------------------------------------------------


def check_bucket_setup() -> None:
    """Operator setup: bucket, versioning, noncurrent-version lifecycle."""
    client = admin()
    try:
        client.create_bucket(Bucket=BUCKET)
    except ClientError as exc:
        if error_code(exc) not in ("BucketAlreadyOwnedByYou",
                                   "BucketAlreadyExists"):
            raise
    client.put_bucket_versioning(
        Bucket=BUCKET, VersioningConfiguration={"Status": "Enabled"})
    status = client.get_bucket_versioning(Bucket=BUCKET).get("Status")
    record("versioning enabled by admin", status == "Enabled", str(status))

    rule = {"ID": "noncurrent-365", "Status": "Enabled",
            "Filter": {"Prefix": ""},
            "NoncurrentVersionExpiration": {"NoncurrentDays": 365}}
    try:
        client.put_bucket_lifecycle_configuration(
            Bucket=BUCKET, LifecycleConfiguration={"Rules": [rule]})
        got = client.get_bucket_lifecycle_configuration(Bucket=BUCKET)
        rules = got.get("Rules", [])
        days = [r.get("NoncurrentVersionExpiration", {}).get("NoncurrentDays")
                for r in rules]
        record("NoncurrentVersionExpiration on versioned bucket",
               days == [365], json.dumps(rules, default=str))
    except ClientError as exc:
        record("NoncurrentVersionExpiration on versioned bucket", False,
               f"{error_code(exc)}: {exc}")
    # A second bucket, to see whether ListBuckets leaks bucket names.
    try:
        client.create_bucket(Bucket="operator-only")
    except ClientError:
        pass
    # Another user's object, written by the operator, for the deny checks.
    client.put_object(Bucket=BUCKET, Key="user2/models/secret.txt",
                      Body=b"user2 data")


def check_sts_trust() -> dict[str, str]:
    """AssumeRoleWithWebIdentity accepts login-relay's pass; ARN forms."""
    creds: dict[str, str] = {}
    try:
        creds = assume(ISSUER_STATE.mint("user1"))["Credentials"]
        record("STS accepts ES256 pass from external issuer", True,
               f"expires {creds['Expiration']}")
    except Exception as exc:  # pylint: disable=broad-except
        record("STS accepts ES256 pass from external issuer", False,
               f"{error_code(exc)}: {exc}")

    for arn in ("arn:seaweed:iam::role/WorkspaceBackup",
                "arn:aws:iam::123456789012:role/WorkspaceBackup",
                "arn:aws:iam:::role/WorkspaceBackup",
                "WorkspaceBackup"):
        try:
            assume(ISSUER_STATE.mint("user1"), role_arn=arn)
            record(f"role ARN form accepted: {arn}", True, "informational")
        except Exception as exc:  # pylint: disable=broad-except
            record(f"role ARN form accepted: {arn}", True,
                   f"informational, refused: {error_code(exc)}")
    return creds


def unsigned_pass(algorithm: str, secret: str | None) -> str:
    """Return a pass signed without login-relay's key."""
    claims = {"iss": ISSUER, "aud": AUDIENCE, "sub": "user1",
              "preferred_username": "user1", "exp": int(time.time()) + 300}
    return jwt.encode(claims, secret, algorithm=algorithm,
                      headers={"kid": "2026-10"})


def check_sts_refusals() -> None:
    """STS refuses every pass login-relay did not issue as specified."""
    ISSUER_STATE.keys["rogue"] = new_key()
    good = ISSUER_STATE.mint("user1")
    bad_cases = {
        "wrong audience": ISSUER_STATE.mint("user1", aud="dtaas-workspace"),
        "wrong issuer": ISSUER_STATE.mint("user1", iss="http://evil:8080"),
        "expired pass": ISSUER_STATE.mint("user1", lifetime=-60),
        "key not in JWKS": ISSUER_STATE.mint("user1", kid="rogue"),
        "tampered signature": good[:-4] + ("BBBB" if good.endswith("AAAA")
                                           else "AAAA"),
        "alg none": unsigned_pass("none", None),
        "HS256": unsigned_pass("HS256", "x" * 32),
    }
    for label, token in bad_cases.items():
        try:
            assume(token)
            record(f"STS refuses {label}", False, "accepted")
        except Exception as exc:  # pylint: disable=broad-except
            record(f"STS refuses {label}", True, f"refused: {error_code(exc)}")

    try:
        assume(ISSUER_STATE.mint("user1", aud="other",
                                 extra={"azp": AUDIENCE}))
        record("azp counts as audience", True, "informational: accepted")
    except Exception as exc:  # pylint: disable=broad-except
        record("azp counts as audience", True,
               f"informational: refused {error_code(exc)}")


def check_session_length() -> None:
    """maxSessionLength 1h: a stolen 5-minute pass buys at most an hour."""
    for duration in (900, 3600, 3601, 43200):
        name = f"DurationSeconds {duration} capped at 3600"
        try:
            got = assume(ISSUER_STATE.mint("user1"), duration=duration)
            exp = got["Credentials"]["Expiration"]
            left = (exp - datetime.now(timezone.utc)).total_seconds()
            record(name, left <= 3600, f"granted ~{int(left)} s")
        except Exception as exc:  # pylint: disable=broad-except
            record(name, duration > 3600, f"refused {error_code(exc)}")


def check_own_prefix(s3: Any) -> None:
    """The role reads, writes and lists its own prefix."""
    key = "user1/models/a.txt"
    expect("put own prefix", lambda: s3.put_object(
        Bucket=BUCKET, Key=key, Body=b"one"), True)
    expect("get own prefix",
           functools.partial(s3.get_object, Bucket=BUCKET, Key=key), True)
    expect("list own prefix user1/", lambda: s3.list_objects_v2(
        Bucket=BUCKET, Prefix="user1/"), True)
    expect("list own asset user1/models/ with delimiter",
           lambda: s3.list_objects_v2(Bucket=BUCKET, Prefix="user1/models/",
                                      Delimiter="/"), True)
    expect("GetBucketVersioning", lambda: s3.get_bucket_versioning(
        Bucket=BUCKET), True)


def check_other_prefixes(s3: Any) -> None:
    """The role reaches no other prefix, look-alike or bucket listing."""
    for label, prefix in (("bucket without prefix", None),
                          ("other prefix user2/", "user2/"),
                          ("look-alike prefix user10/", "user10/"),
                          ("prefix user1 (no slash)", "user1")):
        kwargs = {"Bucket": BUCKET}
        if prefix is not None:
            kwargs["Prefix"] = prefix
        expect(f"list {label}",
               lambda kw=kwargs: s3.list_objects_v2(**kw), False)
    expect("put other prefix", lambda: s3.put_object(
        Bucket=BUCKET, Key="user2/models/x.txt", Body=b"x"), False)
    expect("get other prefix", lambda: s3.get_object(
        Bucket=BUCKET, Key="user2/models/secret.txt"), False)
    expect("put look-alike prefix user10/", lambda: s3.put_object(
        Bucket=BUCKET, Key="user10/x.txt", Body=b"x"), False)
    try:
        names = [b["Name"] for b in s3.list_buckets().get("Buckets", [])]
        record("ListBuckets shows no more than the backup bucket",
               set(names) <= {BUCKET}, f"allowed, returns {names}")
    except ClientError as exc:
        record("ListBuckets shows no more than the backup bucket", True,
               f"denied: {error_code(exc)}")


def absent_for_admin(name: str, key: str) -> None:
    """Record whether ``key`` does not exist, seen by the operator."""
    try:
        admin().head_object(Bucket=BUCKET, Key=key)
        record(name, False, f"{key} exists")
    except ClientError:
        record(name, True, "absent")


def check_traversal(s3: Any) -> None:
    """'..' in a key never reaches another user's prefix."""
    expect("put user1/../user2/escape.txt", lambda: s3.put_object(
        Bucket=BUCKET, Key="user1/../user2/escape.txt", Body=b"x"), False)
    absent_for_admin("traversal key did not land in user2/",
                     "user2/escape.txt")
    expect("put user1/%2e%2e/user2/escape2.txt", lambda: s3.put_object(
        Bucket=BUCKET, Key="user1/%2e%2e/user2/escape2.txt", Body=b"x"),
        True)
    absent_for_admin("encoded traversal did not land in user2/",
                     "user2/escape2.txt")


def check_history(s3: Any) -> None:
    """Overwrites and deletes keep versions the role cannot remove."""
    key = "user1/models/a.txt"
    s3.put_object(Bucket=BUCKET, Key=key, Body=b"two")
    versions = admin().list_object_versions(Bucket=BUCKET, Prefix=key)
    ids = [v["VersionId"] for v in versions.get("Versions", [])]
    record("overwrite keeps the old version", len(ids) >= 2,
           f"{len(ids)} versions")
    expect("DeleteObject (delete marker)", lambda: s3.delete_object(
        Bucket=BUCKET, Key=key), True)
    after = admin().list_object_versions(Bucket=BUCKET, Prefix=key)
    kept, markers = (len(after.get("Versions", [])),
                     len(after.get("DeleteMarkers", [])))
    record("delete leaves versions and a marker", kept >= 2 and markers >= 1,
           f"{kept} versions, {markers} markers")
    if ids:
        expect("DeleteObjectVersion", lambda: s3.delete_object(
            Bucket=BUCKET, Key=key, VersionId=ids[-1]), False)
    expect("ListObjectVersions own prefix", lambda: s3.list_object_versions(
        Bucket=BUCKET, Prefix="user1/"), False)


def check_bucket_denies(s3: Any) -> None:
    """The role cannot change versioning, lifecycle, policy or buckets."""
    lifecycle = {"Rules": [{
        "ID": "x", "Status": "Enabled", "Filter": {"Prefix": ""},
        "NoncurrentVersionExpiration": {"NoncurrentDays": 1}}]}
    policy = json.dumps({"Version": "2012-10-17", "Statement": [{
        "Effect": "Allow", "Principal": "*", "Action": "s3:*",
        "Resource": f"arn:aws:s3:::{BUCKET}/*"}]})
    expect("PutBucketVersioning Suspended", lambda: s3.put_bucket_versioning(
        Bucket=BUCKET, VersioningConfiguration={"Status": "Suspended"}),
        False)
    expect("PutBucketLifecycleConfiguration",
           lambda: s3.put_bucket_lifecycle_configuration(
               Bucket=BUCKET, LifecycleConfiguration=lifecycle), False)
    expect("DeleteBucketLifecycle", lambda: s3.delete_bucket_lifecycle(
        Bucket=BUCKET), False)
    expect("PutBucketPolicy", lambda: s3.put_bucket_policy(
        Bucket=BUCKET, Policy=policy), False)
    expect("CreateBucket", lambda: s3.create_bucket(Bucket="user1-own"),
           False)
    expect("DeleteBucket", lambda: s3.delete_bucket(Bucket=BUCKET), False)
    status = admin().get_bucket_versioning(Bucket=BUCKET).get("Status")
    record("versioning still Enabled after user attempts",
           status == "Enabled", str(status))


def check_multipart(s3: Any) -> None:
    """rclone's multipart uploads work on the own prefix only."""
    key = "user1/models/big.bin"
    upload = expect("CreateMultipartUpload own prefix",
                    lambda: s3.create_multipart_upload(Bucket=BUCKET,
                                                       Key=key), True)
    if upload:
        uid = upload["UploadId"]
        expect("UploadPart", lambda: s3.upload_part(
            Bucket=BUCKET, Key=key, UploadId=uid, PartNumber=1,
            Body=os.urandom(5 * 1024 * 1024)), True)
        expect("ListParts", lambda: s3.list_parts(
            Bucket=BUCKET, Key=key, UploadId=uid), True)
        expect("AbortMultipartUpload", lambda: s3.abort_multipart_upload(
            Bucket=BUCKET, Key=key, UploadId=uid), True)
    expect("CreateMultipartUpload other prefix",
           lambda: s3.create_multipart_upload(Bucket=BUCKET,
                                              Key="user2/big.bin"), False)


def check_prefix_policy() -> None:
    """The role reaches only the caller's own prefix and keeps history."""
    s3, _ = user_s3("user1")
    check_own_prefix(s3)
    check_other_prefixes(s3)
    check_traversal(s3)
    check_history(s3)
    check_bucket_denies(s3)
    check_multipart(s3)


def check_rotation() -> None:
    """JWKS cache: a new key id triggers a refetch; a removed key lingers."""
    ISSUER_STATE.keys["2026-11"] = new_key()
    ISSUER_STATE.publish("2026-10", "2026-11")
    before = ISSUER_STATE.fetches
    try:
        assume(ISSUER_STATE.mint("user1", kid="2026-11"))
        record("new kid accepted at once (refetch on miss)", True,
               f"JWKS fetches {before} -> {ISSUER_STATE.fetches}")
    except Exception as exc:  # pylint: disable=broad-except
        record("new kid accepted at once (refetch on miss)", False,
               error_code(exc))
    ISSUER_STATE.publish("2026-11")
    try:
        assume(ISSUER_STATE.mint("user1", kid="2026-10"))
        record("removed kid still accepted until cache TTL", True,
               "informational: old key trusted up to jwksCacheTTLSeconds")
    except Exception as exc:  # pylint: disable=broad-except
        record("removed kid still accepted until cache TTL", True,
               f"informational: refused at once {error_code(exc)}")
    ISSUER_STATE.publish("2026-10", "2026-11")


def rclone(args: list[str], creds: dict[str, str] | None = None,
           remote: str = "sw") -> subprocess.CompletedProcess[str]:
    """Run rclone with an env-only remote; keys never on the command line."""
    env = dict(os.environ)
    prefix = f"RCLONE_CONFIG_{remote.upper()}_"
    env.update({
        prefix + "TYPE": "s3",
        prefix + "PROVIDER": "SeaweedFS",
        prefix + "ENDPOINT": ENDPOINT,
        prefix + "REGION": "us-east-1",
        prefix + "ACCESS_KEY_ID": (creds or {}).get("AccessKeyId",
                                                    ADMIN_KEY),
        prefix + "SECRET_ACCESS_KEY": (creds or {}).get("SecretAccessKey",
                                                        ADMIN_SECRET),
    })
    if creds and creds.get("SessionToken"):
        env[prefix + "SESSION_TOKEN"] = creds["SessionToken"]
    return subprocess.run(["rclone", *args], env=env, capture_output=True,
                          text=True, timeout=120, check=False)


def tail(done: subprocess.CompletedProcess[str], size: int = 200) -> str:
    """Return the end of rclone's stderr for a check's detail."""
    return done.stderr.strip()[-size:]


def tree_digest(root: Path) -> dict[str, str]:
    """Map relative file paths under ``root`` to their SHA-256."""
    return {str(p.relative_to(root)): hashlib.sha256(p.read_bytes())
            .hexdigest() for p in sorted(root.rglob("*")) if p.is_file()}


ASSET = Path("/tmp/asset")
DEST = f"sw:{BUCKET}/user1/models"
SYNC_FLAGS = ["--s3-no-check-bucket", "--skip-links", "--delete-before",
              "--max-delete", "1000", "--contimeout", "10s",
              "--timeout", "60s"]


def check_rclone_sync(creds: dict[str, str]) -> None:
    """rclone sync with STS keys skips links; bucket check is optional."""
    shutil.rmtree(ASSET, ignore_errors=True)
    (ASSET / "sub").mkdir(parents=True)
    (ASSET / "a.txt").write_text("version 1\n")
    (ASSET / "b.bin").write_bytes(os.urandom(64 * 1024))
    (ASSET / "sub" / "c.txt").write_text("to be deleted\n")
    (ASSET / "link").symlink_to("/etc/passwd")
    done = rclone(["sync", str(ASSET), DEST, *SYNC_FLAGS], creds)
    record("rclone sync with session token", done.returncode == 0,
           tail(done))
    names = rclone(["lsf", "-R", DEST], creds).stdout.split()
    record("--skip-links left the symlink out", "link" not in names,
           " ".join(names))
    nocheck = rclone(["sync", str(ASSET), DEST, "--skip-links"], creds)
    record("sync without --s3-no-check-bucket", True,
           f"informational: exit {nocheck.returncode} {tail(nocheck)}")


def check_restore(creds: dict[str, str]) -> None:
    """The operator restores a prefix as it was with --s3-version-at."""
    time.sleep(2)
    moment = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    snapshot = tree_digest(ASSET)
    del snapshot["link"]
    time.sleep(2)
    (ASSET / "a.txt").write_text("version 2\n")
    (ASSET / "sub" / "c.txt").unlink()
    again = rclone(["sync", str(ASSET), DEST, *SYNC_FLAGS], creds)
    record("second sync (modify + delete)", again.returncode == 0,
           tail(again))

    restore = Path("/tmp/restore")
    shutil.rmtree(restore, ignore_errors=True)
    back = rclone(["copy", DEST.replace("sw:", "admin:"), str(restore),
                   "--s3-version-at", moment], remote="admin")
    got = tree_digest(restore) if restore.exists() else {}
    record("operator restore with --s3-version-at",
           back.returncode == 0 and got == snapshot,
           f"at {moment}: {sorted(got)} {tail(back)}")
    user_back = rclone(["copy", DEST, "/tmp/restore-user",
                        "--s3-version-at", moment], creds)
    record("user role cannot restore versions", user_back.returncode != 0,
           f"exit {user_back.returncode} {tail(user_back)}")


def check_delete_brake(creds: dict[str, str]) -> None:
    """--max-delete with --delete-before stops before any upload."""
    for name in ("d1", "d2", "d3"):
        (ASSET / name).write_text(name)
    rclone(["sync", str(ASSET), DEST, *SYNC_FLAGS], creds)
    for name in ("d1", "d2", "d3"):
        (ASSET / name).unlink()
    (ASSET / "new.txt").write_text("arrives only after the brake\n")
    brake = rclone(["sync", str(ASSET), DEST, "--s3-no-check-bucket",
                    "--skip-links", "--delete-before", "--max-delete", "1"],
                   creds)
    left = rclone(["lsf", DEST], creds).stdout.split()
    record("--max-delete brake exits 7 with its message",
           brake.returncode == 7
           and "--max-delete threshold reached" in brake.stderr,
           f"exit {brake.returncode}")
    record("--delete-before: brake trips before any upload",
           "new.txt" not in left,
           f"remaining d*: {[n for n in left if n.startswith('d')]}")
    (ASSET / "new.txt").unlink()

    empty = Path("/tmp/empty")
    empty.mkdir(exist_ok=True)
    wipe = rclone(["sync", str(empty), DEST, "--s3-no-check-bucket",
                   "--max-delete", "1000", "--dry-run"], creds)
    record("empty source would delete everything (admin must refuse)", True,
           f"informational: dry-run exit {wipe.returncode}, "
           f"{wipe.stderr.count('Skipped delete')} deletes planned")


def check_rclone() -> None:
    """rclone with STS keys: sync, restore and the deletion brake."""
    _, creds = user_s3("user1")
    check_rclone_sync(creds)
    check_restore(creds)
    check_delete_brake(creds)


def check_after_restart() -> None:
    """Data, settings and an earlier STS session survive a restart."""
    creds = json.loads((OUT / "creds.json").read_text())
    s3 = s3_client(creds["AccessKeyId"], creds["SecretAccessKey"],
                   creds["SessionToken"])
    expect("STS session from before restart still works",
           lambda: s3.list_objects_v2(Bucket=BUCKET, Prefix="user1/"), True)
    body = admin().get_object(Bucket=BUCKET, Key="user1/models/persist.txt")
    record("objects survive restart",
           body["Body"].read() == b"survives restart")
    status = admin().get_bucket_versioning(Bucket=BUCKET).get("Status")
    record("versioning survives restart", status == "Enabled", str(status))
    rules = admin().get_bucket_lifecycle_configuration(
        Bucket=BUCKET).get("Rules", [])
    record("lifecycle survives restart", len(rules) == 1,
           json.dumps(rules, default=str))


def main() -> int:
    """Run every check, write the summary, return non-zero on a failure."""
    phase = sys.argv[1] if len(sys.argv) > 1 else "main"
    ISSUER_STATE.keys["2026-10"] = new_key()
    ISSUER_STATE.publish("2026-10")
    start_issuer()
    OUT.mkdir(parents=True, exist_ok=True)
    if phase == "main":
        check_bucket_setup()
        creds = check_sts_trust()
        check_sts_refusals()
        check_session_length()
        check_prefix_policy()
        check_rotation()
        check_rclone()
        (OUT / "creds.json").write_text(json.dumps(creds, default=str))
        admin().put_object(Bucket=BUCKET, Key="user1/models/persist.txt",
                           Body=b"survives restart")
    else:
        check_after_restart()
    (OUT / f"results-{phase}.json").write_text(json.dumps(RESULTS, indent=1))
    failed = [r for r in RESULTS if not r["ok"]]
    print(f"\n{len(RESULTS) - len(failed)}/{len(RESULTS)} checks passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
