#!/usr/bin/env bash
# Health-check: verify both users see new files in /workspace/common

set -euo pipefail

USER1_CONTAINER="${USER1_CONTAINER:-workspace-user1}"
USER2_CONTAINER="${USER2_CONTAINER:-workspace-user2}"
COMMON_DIR="${COMMON_DIR:-/workspace/common}"
TEST_BASENAME="${TEST_BASENAME:-healthcheck-common-sync}"

log_info() {
    echo "[INFO] $*"
}

log_error() {
    echo "[ERROR] $*" >&2
}

require_container() {
    local name="$1"
    if ! docker inspect "$name" >/dev/null 2>&1; then
        log_error "Container not found: $name"
        exit 1
    fi
}

cleanup() {
    local user1_file="$1"
    local user2_file="$2"
    docker exec "$USER1_CONTAINER" bash -c "rm -f '$user1_file'" >/dev/null 2>&1 || true
    docker exec "$USER2_CONTAINER" bash -c "rm -f '$user2_file'" >/dev/null 2>&1 || true
}

require_container "$USER1_CONTAINER"
require_container "$USER2_CONTAINER"

stamp="$(date +%s)"
user1_file="$COMMON_DIR/${TEST_BASENAME}-u1-$stamp.txt"
user2_file="$COMMON_DIR/${TEST_BASENAME}-u2-$stamp.txt"

log_info "Creating test file in user1: $user1_file"
docker exec "$USER1_CONTAINER" bash -c "printf '%s\n' 'from user1 $stamp' > '$user1_file'"

log_info "Waiting for user2 to see user1 file"
for _ in $(seq 1 20); do
    if docker exec "$USER2_CONTAINER" bash -c "test -f '$user1_file'" >/dev/null 2>&1; then
        log_info "User2 can see user1 file"
        break
    fi
    sleep 1
    if [ "$SECONDS" -ge 20 ]; then
        log_error "User2 did not see user1 file within timeout"
        cleanup "$user1_file" "$user2_file"
        exit 1
    fi
done

log_info "Creating test file in user2: $user2_file"
docker exec "$USER2_CONTAINER" bash -c "printf '%s\n' 'from user2 $stamp' > '$user2_file'"

log_info "Waiting for user1 to see user2 file"
for _ in $(seq 1 20); do
    if docker exec "$USER1_CONTAINER" bash -c "test -f '$user2_file'" >/dev/null 2>&1; then
        log_info "User1 can see user2 file"
        break
    fi
    sleep 1
    if [ "$SECONDS" -ge 40 ]; then
        log_error "User1 did not see user2 file within timeout"
        cleanup "$user1_file" "$user2_file"
        exit 1
    fi
done

cleanup "$user1_file" "$user2_file"
log_info "Common sync health-check passed"
