#!/bin/bash
# Spike S2: confirm the pinned rclone has every flag and provider the S3
# backend relies on. Prints one line per check; exits non-zero on a miss.
set -e

failed=0

check() {
  local label="$1"
  shift
  if "$@" >/dev/null 2>&1; then
    echo "PASS  ${label}"
  else
    echo "FAIL  ${label}"
    failed=1
  fi
}

version="$(rclone version)"
echo "${version%%$'\n'*}"
flags="$(rclone help flags s3)"
global="$(rclone help flags)"
providers="$(rclone help backend s3)"

check "--s3-version-at" grep -q -- "--s3-version-at" <<<"${flags}"
check "--s3-no-check-bucket" grep -q -- "--s3-no-check-bucket" <<<"${flags}"
check "--s3-session-token" grep -q -- "--s3-session-token" <<<"${flags}"
check "--skip-links" grep -q -- "--skip-links" <<<"${global}"
check "--max-delete" grep -q -- "--max-delete" <<<"${global}"
check "provider SeaweedFS" grep -q "SeaweedFS" <<<"${providers}"
check "env remote RCLONE_CONFIG_X_SESSION_TOKEN documented" \
  grep -q "RCLONE_S3_SESSION_TOKEN" <<<"${providers}"

exit "${failed}"
