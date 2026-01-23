#!/usr/bin/env bash
# Mount MinIO buckets using s3fs-fuse with Keycloak authentication

# Note: Don't use 'set -e' to allow graceful fallback if mounting fails
if [[ ${DTAAS_DEBUG:-0} == 1 ]]; then
    set -x
fi

echo "[INFO] Mounting MinIO buckets with Keycloak policy enforcement"

# Get Keycloak token for this user
get_keycloak_token() {
    local response
    response=$(curl -s -X POST "${KEYCLOAK_URL}/realms/${KEYCLOAK_REALM}/protocol/openid-connect/token" \
        -d "client_id=${KEYCLOAK_CLIENT_ID}" \
        -d "username=${KEYCLOAK_USERNAME}" \
        -d "password=${KEYCLOAK_PASSWORD}" \
        -d "grant_type=password")
    
    if [ $? -ne 0 ]; then
        echo "[ERROR] Failed to get Keycloak token"
        return 1
    fi
    
    echo "$response" | jq -r '.access_token'
}

# Wait for Keycloak and MinIO to be ready
echo "[INFO] Waiting for Keycloak and MinIO services..."
max_attempts=30
attempt=0

while [ $attempt -lt $max_attempts ]; do
    if curl -sf "${KEYCLOAK_URL}/realms/${KEYCLOAK_REALM}" > /dev/null 2>&1; then
        echo "[INFO] Keycloak is ready"
        break
    fi
    attempt=$((attempt + 1))
    echo "[INFO] Waiting for Keycloak... (attempt $attempt/$max_attempts)"
    sleep 2
done

if [ $attempt -eq $max_attempts ]; then
    echo "[ERROR] Keycloak not available after $max_attempts attempts"
    echo "[WARNING] Skipping MinIO bucket mounting - services not ready"
    exit 0  # Exit gracefully to allow container to continue starting
fi

attempt=0
while [ $attempt -lt $max_attempts ]; do
    if curl -sf "${MINIO_ENDPOINT}/minio/health/ready" > /dev/null 2>&1; then
        echo "[INFO] MinIO is ready"
        break
    fi
    attempt=$((attempt + 1))
    echo "[INFO] Waiting for MinIO... (attempt $attempt/$max_attempts)"
    sleep 2
done

if [ $attempt -eq $max_attempts ]; then
    echo "[ERROR] MinIO not available after $max_attempts attempts"
    echo "[WARNING] Skipping MinIO bucket mounting - services not ready"
    exit 0  # Exit gracefully to allow container to continue starting
fi

# Get Keycloak token and exchange for MinIO STS credentials
echo "[INFO] Getting MinIO temporary credentials via STS"
KEYCLOAK_TOKEN=$(curl -s -X POST "${KEYCLOAK_URL}/realms/${KEYCLOAK_REALM}/protocol/openid-connect/token" \
    -d "client_id=${KEYCLOAK_CLIENT_ID}" \
    -d "client_secret=${KEYCLOAK_CLIENT_SECRET}" \
    -d "username=${KEYCLOAK_USERNAME}" \
    -d "password=${KEYCLOAK_PASSWORD}" \
    -d "grant_type=password" | jq -r '.access_token')

if [ -z "$KEYCLOAK_TOKEN" ] || [ "$KEYCLOAK_TOKEN" = "null" ]; then
    echo "[ERROR] Failed to get Keycloak token for ${KEYCLOAK_USERNAME}"
    echo "[WARNING] Skipping MinIO bucket mounting - authentication failed"
    exit 0  # Exit gracefully to allow container to continue starting
fi

echo "[INFO] Successfully obtained Keycloak token"

# Use MinIO STS AssumeRoleWithWebIdentity to get temporary credentials
STS_RESPONSE=$(curl -s -X POST "${MINIO_ENDPOINT}/?Action=AssumeRoleWithWebIdentity&WebIdentityToken=${KEYCLOAK_TOKEN}&Version=2011-06-15")

# Extract credentials from STS response
MINIO_STS_ACCESS_KEY=$(echo "$STS_RESPONSE" | grep -oP '(?<=<AccessKeyId>)[^<]+')
MINIO_STS_SECRET_KEY=$(echo "$STS_RESPONSE" | grep -oP '(?<=<SecretAccessKey>)[^<]+')
MINIO_STS_SESSION_TOKEN=$(echo "$STS_RESPONSE" | grep -oP '(?<=<SessionToken>)[^<]+')

if [ -z "$MINIO_STS_ACCESS_KEY" ] || [ "$MINIO_STS_ACCESS_KEY" = "" ]; then
    echo "[ERROR] Failed to get STS credentials from MinIO"
    echo "[DEBUG] STS Response: $STS_RESPONSE"
    echo "[WARNING] Falling back to admin credentials (policies will not be enforced)"
    MINIO_STS_ACCESS_KEY="${MINIO_ACCESS_KEY}"
    MINIO_STS_SECRET_KEY="${MINIO_SECRET_KEY}"
    MINIO_STS_SESSION_TOKEN=""
else
    echo "[INFO] Successfully obtained MinIO STS credentials for ${KEYCLOAK_USERNAME}"
fi

# Provide credentials to s3fs via environment variables
S3FS_SESSION_OPTS=""
export AWS_ACCESS_KEY_ID="$MINIO_STS_ACCESS_KEY"
export AWS_SECRET_ACCESS_KEY="$MINIO_STS_SECRET_KEY"
if [ -n "$MINIO_STS_SESSION_TOKEN" ]; then
    export AWSSESSIONTOKEN="$MINIO_STS_SESSION_TOKEN"
    export AWS_SESSION_TOKEN="$MINIO_STS_SESSION_TOKEN"
    S3FS_SESSION_OPTS="-o use_session_token"
else
    unset AWSSESSIONTOKEN
    unset AWS_SESSION_TOKEN
fi

# Extract hostname and port from MINIO_ENDPOINT
MINIO_HOST=$(echo "${MINIO_ENDPOINT}" | sed 's|http://||' | sed 's|https://||')

# Mount user's own bucket with full access
echo "[INFO] Mounting user bucket: ${MINIO_BUCKET}"

# Build s3fs command with F credentials
S3FS_CMD="s3fs ${MINIO_BUCKET} /workspace/${MAIN_USER} \
    -o url=${MINIO_ENDPOINT} \
    -o use_path_request_style \
    -o endpoint=${MINIO_HOST} \
    -o allow_other \
    ${S3FS_SESSION_OPTS} \
    -o nonempty \
    -o umask=0002 \
    -o uid=$(id -u ${MAIN_USER}) \
    -o gid=$(id -g ${MAIN_USER}) \
    -o stat_cache_expire=1 \
    -o use_cache=/tmp/s3fs_cache_${MAIN_USER} \
    -o max_stat_cache_size=1000 \
    -o dbglevel=info"

# Note: s3fs doesn't support MinIO STS session tokens directly
# But MinIO will still enforce policies based on the temporary credentials
eval $S3FS_CMD || USER_MOUNT_STATUS=$?
USER_MOUNT_STATUS=${USER_MOUNT_STATUS:-0}

# Build s3fs command for common bucket
S3FS_COMMON_CMD="s3fs ${MINIO_COMMON_BUCKET} /workspace/common \
    -o url=${MINIO_ENDPOINT} \
    -o use_path_request_style \
    -o endpoint=${MINIO_HOST} \
    -o allow_other \
    ${S3FS_SESSION_OPTS} \
    -o nonempty \
    -o umask=0002 \
    -o uid=$(id -u ${MAIN_USER}) \
    -o gid=$(id -g ${MAIN_USER}) \
    -o stat_cache_expire=1 \
    -o use_cache=/tmp/s3fs_cache_common \
    -o max_stat_cache_size=1000 \
    -o dbglevel=info"

# Note: s3fs doesn't support MinIO STS session tokens directly
# But MinIO will still enforce policies based on the temporary credentials
eval $S3FS_COMMON_CMD || COMMON_MOUNT_STATUS=$?
COMMON_MOUNT_STATUS=${COMMON_MOUNT_STATUS:-0}
if [ $USER_MOUNT_STATUS -eq 0 ]; then
    echo "[INFO] Successfully mounted ${MINIO_BUCKET} at /workspace/${MAIN_USER}"
else
    echo "[ERROR] Failed to mount ${MINIO_BUCKET} at /workspace/${MAIN_USER}"
fi

if [ $COMMON_MOUNT_STATUS -eq 0 ]; then
    echo "[INFO] Successfully mounted ${MINIO_COMMON_BUCKET} at /workspace/common"
    echo "[INFO] Access to common bucket is controlled by MinIO policies based on Keycloak authentication"
else
    echo "[ERROR] Failed to mount ${MINIO_COMMON_BUCKET}"
fi

# Create symbolic links in user's home directory for easy access
if [[ ! -L "${HOME}/Desktop/common" ]] && [[ -d "/workspace/common" ]]; then
    ln -s /workspace/common "${HOME}/Desktop/common" 2>/dev/null || true
    echo "[INFO] Created desktop shortcut to common directory"
fi

if [[ ! -L "${HOME}/Desktop/${MAIN_USER}" ]] && [[ -d "/workspace/${MAIN_USER}" ]]; then
    ln -s "/workspace/${MAIN_USER}" "${HOME}/Desktop/${MAIN_USER}" 2>/dev/null || true
    echo "[INFO] Created desktop shortcut to user directory"
fi

echo "[INFO] MinIO bucket mounting completed"
exit 0  # Always exit successfully to allow container to start