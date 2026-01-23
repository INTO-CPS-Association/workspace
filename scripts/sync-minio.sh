#!/bin/bash
# MinIO Synchronization Script
# Syncs local workspace files with MinIO buckets using authorization

set -e

# Configuration from environment variables
KEYCLOAK_URL="${KEYCLOAK_URL:-http://keycloak:8080}"
KEYCLOAK_REALM="${KEYCLOAK_REALM:-workspace}"
KEYCLOAK_CLIENT_ID="${KEYCLOAK_CLIENT_ID:-workspace-frontend}"
KEYCLOAK_CLIENT_SECRET="${KEYCLOAK_CLIENT_SECRET:-}"
KEYCLOAK_USERNAME="${KEYCLOAK_USERNAME:-$MAIN_USER}"
KEYCLOAK_PASSWORD="${KEYCLOAK_PASSWORD:-${MAIN_USER}password}"
AUTHZ_PROXY_URL="${AUTHZ_PROXY_URL:-http://authz-proxy:8081}"
MINIO_ENDPOINT="${MINIO_ENDPOINT:-http://minio:9000}"
MINIO_BUCKET="${MINIO_BUCKET:-user1}"
MINIO_COMMON_BUCKET="${MINIO_COMMON_BUCKET:-common}"
MAIN_USER="${MAIN_USER:-user1}"
WORKSPACE_DIR="${PERSISTENT_DIR:-/workspace}"
MINIO_ACCESS_KEY="${MINIO_ACCESS_KEY:-minioadmin}"
MINIO_SECRET_KEY="${MINIO_SECRET_KEY:-minioadmin123}"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Get authentication token (in real implementation, this would use OAuth2 flow)
get_auth_token() {
    if [ -n "$AUTH_TOKEN" ]; then
        echo "$AUTH_TOKEN"
        return 0
    fi

    if [ -z "$KEYCLOAK_USERNAME" ] || [ -z "$KEYCLOAK_PASSWORD" ]; then
        log_warn "Missing KEYCLOAK_USERNAME/KEYCLOAK_PASSWORD and AUTH_TOKEN"
        return 1
    fi

    token_url="$KEYCLOAK_URL/realms/$KEYCLOAK_REALM/protocol/openid-connect/token"

    if [ -n "$KEYCLOAK_CLIENT_SECRET" ]; then
        response=$(curl -s -X POST "$token_url" \
            -d "grant_type=password" \
            -d "client_id=$KEYCLOAK_CLIENT_ID" \
            -d "client_secret=$KEYCLOAK_CLIENT_SECRET" \
            -d "username=$KEYCLOAK_USERNAME" \
            -d "password=$KEYCLOAK_PASSWORD" \
            -d "scope=openid profile email")
    else
        response=$(curl -s -X POST "$token_url" \
            -d "grant_type=password" \
            -d "client_id=$KEYCLOAK_CLIENT_ID" \
            -d "username=$KEYCLOAK_USERNAME" \
            -d "password=$KEYCLOAK_PASSWORD" \
            -d "scope=openid profile email")
    fi

    token=$(python - <<'PY'
import json, sys
try:
    data = json.load(sys.stdin)
    print(data.get("access_token", ""))
except Exception:
    print("")
PY
    <<< "$response")

    if [ -z "$token" ]; then
        log_error "Failed to obtain access token from Keycloak"
        return 1
    fi

    echo "$token"
}

# Check authorization for a resource
check_authorization() {
    local resource_path="$1"
    local action="$2"
    local token="$3"
    
    response=$(curl -s -w "\n%{http_code}" -X POST "$AUTHZ_PROXY_URL/authorize" \
        -H "Authorization: Bearer $token" \
        -H "Content-Type: application/json" \
        -d "{\"resource_path\":\"$resource_path\",\"action\":\"$action\"}")
    
    http_code=$(echo "$response" | tail -n1)
    
    if [ "$http_code" -eq 200 ]; then
        return 0
    else
        return 1
    fi
}

# Sync user's private files to MinIO
sync_user_files() {
    log_info "Syncing user files to MinIO bucket: $MINIO_BUCKET"
    
    token=$(get_auth_token)
    if [ $? -ne 0 ]; then
        log_error "Authentication required"
        return 1
    fi
    
    # Configure mc (MinIO client)
    mc alias set myminio "$MINIO_ENDPOINT" "$MINIO_ACCESS_KEY" "$MINIO_SECRET_KEY"
    
    # Sync local workspace to MinIO
    if [ -d "$WORKSPACE_DIR" ]; then
        mc mirror --overwrite "$WORKSPACE_DIR/" "myminio/$MINIO_BUCKET/"
        log_info "User files synced successfully"
    else
        log_warn "Workspace directory not found: $WORKSPACE_DIR"
    fi
}

# Sync common shared files from MinIO
sync_common_files() {
    log_info "Syncing common shared files from MinIO"
    
    token=$(get_auth_token)
    if [ $? -ne 0 ]; then
        log_error "Authentication required"
        return 1
    fi
    
    # Check read authorization for common bucket
    if check_authorization "/common" "read" "$token"; then
        mc alias set myminio "$MINIO_ENDPOINT" "$MINIO_ACCESS_KEY" "$MINIO_SECRET_KEY"
        
        # Create common directory if it doesn't exist
        mkdir -p "$WORKSPACE_DIR/common"
        
        # Download from MinIO to local
        mc mirror --overwrite "myminio/$MINIO_COMMON_BUCKET/" "$WORKSPACE_DIR/common/"
        log_info "Common files synced successfully"
    else
        log_error "Access denied to common resources"
        return 1
    fi
}

# Upload file to common bucket (requires write permission)
upload_to_common() {
    local file_path="$1"
    
    if [ ! -f "$file_path" ]; then
        log_error "File not found: $file_path"
        return 1
    fi
    
    token=$(get_auth_token)
    if [ $? -ne 0 ]; then
        log_error "Authentication required"
        return 1
    fi
    
    filename=$(basename "$file_path")
    
    # Check write authorization
    if check_authorization "/common/$filename" "write" "$token"; then
        mc alias set myminio "$MINIO_ENDPOINT" "$MINIO_ACCESS_KEY" "$MINIO_SECRET_KEY"
        mc cp "$file_path" "myminio/$MINIO_COMMON_BUCKET/$filename"
        log_info "File uploaded to common bucket: $filename"
    else
        log_error "Access denied to write to common resources"
        return 1
    fi
}

# Watch for file changes and auto-sync
watch_and_sync() {
    log_info "Starting file watch and auto-sync..."
    
    while true; do
        # Sync every 5 minutes
        sleep 300
        
        log_info "Auto-syncing files..."
        sync_user_files
        sync_common_files
    done
}

# Main command handler
case "${1:-}" in
    sync-user)
        sync_user_files
        ;;
    sync-common)
        sync_common_files
        ;;
    upload-common)
        upload_to_common "$2"
        ;;
    watch)
        watch_and_sync
        ;;
    *)
        echo "Usage: $0 {sync-user|sync-common|upload-common <file>|watch}"
        echo ""
        echo "Commands:"
        echo "  sync-user        - Sync user's private files to MinIO"
        echo "  sync-common      - Sync common shared files from MinIO"
        echo "  upload-common    - Upload a file to common shared space"
        echo "  watch            - Continuously watch and sync files"
        exit 1
        ;;
esac
