# Keycloak + MinIO Integration with Dynamic Policy Enforcement

This document consolidates all Keycloak–MinIO integration guidance, including policy mapping, AuthZ‑proxy enforcement, s3fs-fuse filesystem mounting, and optional Traefik routing.

## 1) Architecture (High Level)

### Authentication & Policy Flow
```
User → Keycloak (auth) → JWT Token (with policy claim)
          ↓
     ┌────────────────────┴────────────────────┐
     ↓                                         ↓
   AuthZ‑Proxy (PEP/PDP)                    MinIO (S3)
   Path-based enforcement                  Policy enforcement
     ↓                                         ↓
   HTTP API Access                         S3 API Access
```

### Filesystem Integration (New!)
```
Workspace Container Startup
     ↓
   mount_minio.sh script
     ↓
   s3fs-fuse mounts MinIO buckets → /workspace/common (common bucket)
              → /workspace/{username} (user bucket)
     ↓
   User accesses files in /workspace/common
     ↓
   s3fs makes S3 API call to MinIO with credentials
     ↓
   MinIO validates JWT token and applies Keycloak policies
     ↓
   Access granted/denied based on policy claim

### Policy Enforcement Model (PEP + PDP)
**PEP (Policy Enforcement Point)**
- Implemented by the **AuthZ‑Proxy** for HTTP requests.
- Intercepts requests and enforces decisions before reaching protected resources.
- Uses token claims from Keycloak to authorize path-based access (e.g., `/common/**`, `/userX/**`).

**PDP (Policy Decision Point)**
- Implemented inside **AuthZ‑Proxy** logic and delegated to MinIO policy evaluation for S3 operations.
- For HTTP access, the proxy evaluates the policy claim and roles against the requested path and action.
- For S3 access, MinIO evaluates the JWT policy claim and applies bucket policies at request time.

**Key outcome:** PEP blocks/permits HTTP API access, while MinIO enforces S3 policy decisions even when access occurs through s3fs.
```

### Components
- **Keycloak**: IAM, user roles, JWT issuance, policy claim injection.
- **AuthZ‑Proxy**: Policy Enforcement Point (PEP) + Policy Decision Point (PDP) for HTTP/path‑based access.
- **MinIO**: S3 object storage with OIDC integration and dynamic policy mapping.
- **s3fs-fuse**: FUSE filesystem that mounts MinIO buckets and enforces policies at file system level.
- **PostgreSQL**: Keycloak database.
- **Workspace Containers**: User environments with mounted MinIO buckets for seamless file access.

## 2) Deployment Options

### Option A — Direct Ports (compose.minio.keycloak.yml)
- Keycloak: http://localhost:8180
- MinIO Console: http://localhost:9001
- MinIO S3: http://localhost:9000
- AuthZ‑Proxy: http://localhost:8300

### Option B — Traefik Routing (compose.minio.keycloak.traefik.yml)
All services behind http://localhost with path routing:
- /keycloak → Keycloak Admin
- /minio → MinIO Console
- /minio-api → MinIO S3 API
- /authz → AuthZ‑Proxy
- /user1, /user2 → Workspaces

## 3) Policy Mapping Model

```
Keycloak Role → policy claim → MinIO policy → Bucket access
```

**Role → Policy mapping (recommended):**
- admin → consoleAdmin + readwrite
- common-writer → common-write + user-full-access
- common-reader → common-read + user-full-access
- (no role) → readonly + user-full-access

**Policy claim example:**
```json
{
  "preferred_username": "user2",
  "roles": ["user", "common-writer"],
  "policy": "common-write,user-full-access"
}
```

## 4) MinIO Policies

The default policies are created on startup by `minio-init`:
- **common-read**: read‑only for `common` bucket
- **common-write**: read/write for `common` bucket
- **user-full-access**: full access to bucket named `${jwt:preferred_username}`
- **consoleAdmin**: MinIO console admin
- **readwrite**: full access to all buckets

## 5) Keycloak Configuration

### Client (minio)
- **Client ID:** `minio`
- **Secret:** `minio-client-secret`
- **Redirect URIs:**
  - http://localhost:9001/*
  - http://localhost:9001/oauth_callback

### Protocol Mapper (policy claim)
Add **User Attribute** mapper to the `minio` client:
- Name: `policy-mapper`
- User Attribute: `policy`
- Token Claim Name: `policy`
- JSON Type: String
- Add to access token / ID token / userinfo: ON

### User Attributes
Set `policy` attribute for each user:
- user1 → `common-read,user-full-access`
- user2 → `common-write,user-full-access`
- admin → `consoleAdmin,readwrite`

> If realm import already ran, update users and mapper manually in Keycloak UI.

## 6) MinIO OIDC Configuration

In `compose.minio.keycloak.yml`:
```yaml
MINIO_IDENTITY_OPENID_CONFIG_URL: "http://keycloak:8080/realms/workspace/.well-known/openid-configuration"
MINIO_IDENTITY_OPENID_CLIENT_ID: "minio"
MINIO_IDENTITY_OPENID_CLIENT_SECRET: "minio-client-secret"
MINIO_IDENTITY_OPENID_CLAIM_NAME: "policy"
MINIO_IDENTITY_OPENID_CLAIM_USERINFO: "policy"
MINIO_IDENTITY_OPENID_SCOPES: "openid,profile,email"
MINIO_IDENTITY_OPENID_REDIRECT_URI: "http://localhost:9001/oauth_callback"
```

In Traefik mode, the Keycloak URL is `http://localhost/keycloak/realms/workspace/.well-known/openid-configuration`.

## 7) AuthZ‑Proxy Policy Rules (Path‑Based)

- **/userX/** → user can access own resources
- **/common/** →
  - read: `common-reader` or `common-writer`
  - write/delete: `common-writer`
- **admin** role bypasses all restrictions

## 7.1) Implementation Details (Keycloak, MinIO, s3fs)
### Keycloak (Identity + Token Claims)
- Authenticates users and issues JWTs.
- Injects the `policy` claim via protocol mapper (`minio-policy-mapper`).
- Adds `roles` and `preferred_username` claims for both AuthZ‑Proxy and MinIO.
- Users and groups define effective roles; user attributes define MinIO policy mapping.

### AuthZ‑Proxy (PEP/PDP for HTTP)
- Acts as the **PEP** by sitting in front of HTTP resources and enforcing access rules.
- Acts as the **PDP** for HTTP by evaluating:
  - `roles` and `policy` claims
  - path/action rules (read/write/delete)
- When denied, requests never reach protected HTTP resources.

### MinIO (PDP for S3)
- Validates OIDC tokens issued by Keycloak.
- Reads the `policy` claim from the JWT and maps it to MinIO policies.
- Enforces bucket access dynamically on every S3 request.

### s3fs‑fuse (Filesystem Bridge)
- Mounts buckets in the workspace container as directories.
- Uses MinIO STS credentials derived from the Keycloak token.
- All file operations translate to S3 calls, so MinIO enforces policies at the storage layer.

**Result:**
- HTTP access is enforced by AuthZ‑Proxy (PEP/PDP).
- S3 and filesystem access are enforced by MinIO (PDP), even when accessed via s3fs.

## 8) Filesystem Integration (s3fs-fuse)

### How It Works
MinIO buckets are mounted as FUSE filesystems inside workspace containers, providing seamless file access with dynamic policy enforcement:

1. **Container starts** with privileged mode and SYS_ADMIN capability
2. **mount_minio.sh** runs during startup:
   - Waits for Keycloak and MinIO services to be ready
   - Creates mount points: `/workspace/{username}` and `/workspace/common`
   - Mounts buckets using s3fs-fuse with MinIO credentials
   - Creates desktop shortcuts for easy access
3. **User accesses files** in `/workspace/common` through file browser/terminal
4. 10) Verification

### A) Verify Filesystem Mounts
```bash
# Check user1's workspace
docker exec -it workspace-user1 bash

# Inside container
$ ls -la /workspace/
drwxr-xr-x  2 user1 user1    0 Jan 21 12:00 common/
drwxr-xr-x  2 user1 user1    0 Jan 21 12:00 user1/

# Test read access to common
$ ls /workspace/common/
data/  digital_twins/  functions/  models/  tools/

# Test write access (should fail for user1)
$ touch /workspace/common/test.txt
touch: cannot touch '/workspace/common/test.txt': Permission denied

# Desktop shortcuts should exist
$ ls -la ~/Desktop/
lrwxrwxrwx 1 user1 user1 17 Jan 21 12:00 common -> /workspace/common
lrwxrwxrwx 1 user1 user1 17 Jan 21 12:00 user1 -> /workspace/user1
```

### B) Test Policy Enforcement via VNC
1. Open http://localhost:8100 (user1's workspace VNC)
2. Navigate to Desktop → `common` folder
3. Try creating a file → **Should fail** (Access Denied)
4. Open http://localhost:8200 (user2's workspace VNC)
5. Navigate to Desktop → `common` folder
6. Try creating a file → **Should succeed** (write access)

### CPolicy enforcement** happens dynamically based on JWT token claims

### Key Benefits
✅ **No hardcoded permissions** - no `:ro` or `:rw` in docker-compose.yml  
✅ **Dynamic enforcement** - changes to Keycloak policies take effect immediately  
✅ **Single source of truth** - MinIO controls all access based on Keycloak  
✅ **Seamless UX** - users see buckets as regular directories  
✅ **Multi-layer security** - both filesystem and S3 API protected

### Configuration Required

**Dockerfile additions:**
```dockerfile
# Install s3fs-fuse for mounting MinIO buckets
RUN apt-get update && \
    apt-get install -y s3fs curl jq && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Make mount script executable
RUN chmod +x ${STARTUPDIR}/mount_minio.sh
```

**Compose.yml additions:**
```yaml
workspace-user1:
  privileged: true
  cap_add:
    - SYS_ADMIN
  devices:
    - /dev/fuse
  security_opt:
    - apparmor:unconfined
  environment:
    - MINIO_ENDPOINT=http://minio:9000
    - MINIO_ACCESS_KEY=${MINIO_ROOT_USER}
    - MINIO_SECRET_KEY=${MINIO_ROOT_PASSWORD}
    - MINIO_BUCKET=user1
    - MINIO_COMMON_BUCKET=common
```

**Mount script (startup/mount_minio.sh):**
```bash
# Create credentials file for s3fs
echo "${MINIO_ACCESS_KEY}:${MINIO_SECRET_KEY}" > /tmp/.passwd-s3fs
chmod 600 /tmp/.passwd-s3fs

# Mount user's own bucket
s3fs "${MINIO_BUCKET}" "/workspace/${MAIN_USER}" \
    -o passwd_file=/tmp/.passwd-s3fs \
    -o url="${MINIO_ENDPOINT}" \
    -o use_path_request_style \
    -o allow_other

# Mount common bucket (policy-enforced)
s3fs "${MINIO_COMMON_BUCKET}" "/workspace/common" \
    -o passwd_file=/tmp/.passwd-s3fs \
    -o url="${MINIO_ENDPOINT}" \
    -o use_path_request_style \
    -o allow_other
```

### Examples

**user1 (read-only access to common):**
```bash
# Inside user1's workspace container
$ ls /workspace/common
data/  digital_twins/  functions/  models/  tools/

$ cat /workspace/common/data/file.txt
This works! (read-only)

$ echo "test" > /workspace/common/data/new.txt
s3fs: put error: response code 403 (Access Denied)
```

**user2 (read-write access to common):**
```bash
# Inside user2's workspace container
$ echo "new content" > /workspace/common/data/file.txt
$ cat /workspace/common/data/file.txt
new content

$ rm /workspace/common/data/old.txt
# Success - file deleted
```

## 9) Start the Stack

### Initial Build (Required for s3fs-fuse)
```bash
# Build the workspace image with s3fs-fuse
docker compose -f compose.minio.keycloak.yml build

# Start all services
docker compose -f compose.minio.keycloak.yml up -d

# Wait for services to start (about 30-60 seconds)
docker compose -f compose.minio.keycloak.yml logs -f keycloak minio
```

### Verify MinIO is Working
```bash
# Run the verification script
bash scripts/verify-minio-setup.sh

# Or manually check MinIO health
curl http://localhost:9000/minio/health/ready

# Check MinIO buckets
docker exec workspace-minio mc alias set local http://localhost:9000 minioadmin minioadmin123
docker exec workspace-minio mc ls local

# Should show:
# [2026-01-22 09:00:00 UTC]     0B common/
# [2026-01-22 09:00:00 UTC]     0B user1/
# [2026-01-22 09:00:00 UTC]     0B user2/
```

### Check Container Mounts
```bash
# Check if s3fs mounts are active in workspace containers
docker exec workspace-user1 mount | grep s3fs

# Expected output:
# s3fs on /workspace/user1 type fuse.s3fs (rw,nosuid,nodev,relatime,user_id=1000,group_id=1000,allow_other)
# s3fs on /workspace/common type fuse.s3fs (rw,nosuid,nodev,relatime,user_id=1000,group_id=1000,allow_other)

# Check desktop shortcuts
docker exec workspace-user1 ls -la /home/user1/Desktop/
# Should show symlinks: common -> /workspace/common, user1 -> /workspace/user1
```

### Direct Ports
```bash
docker compose -f compose.minio.keycloak.yml up -d
```

### Traefik
```bDsh
docker compose -f compose.minio.keycloak.traefik.yml up -d
```

### Verify Mounts
```bash
# Check if buckets are mounted in user1's container
docker logs workspace-user1 2>&1 | grep -i "mount"

# Expected output:
# [INFO] Successfully mounted user1 at /workspace/user1
# [INFO] Successfully mounted common at /workspace/common

# Inspect mounted filesystems
docker exec workspace-user1 df -h | grep s3fs
```

## 9) Verification

### A) Check policy claim in token
```powershell
$response = Invoke-RestMethod -Method Post -Uri "http://localhost:8180/realms/workspace/protocol/openid-connect/token" -Body @{
  username="user1"
  password="user1password"
  grant_type="password"
  client_id="minio"
  client_secret="minio-client-secret"
  scope="openid profile email"
}
python -c "import jwt, sys; token='$($response.access_token)'; print(jwt.decode(token, options={'verify_signature': False}))"
```

### B) MinIO Console SSO
1. Open http://localhost:9001
2. Click **Login with SSO**
3. Login as user1 / user1password
4. Verify access to `common` and own bucket only

### E) AuthZ‑Proxy flow
```bash
python scripts/test-authz.py --user user1 --password user1password --resource "/common/data/file.txt" --action read
```

### F) Full test script
```powershell
python scripts/test-keycloak-minio.py
```

## 11) Changing User Access Policies

To change access for user1 or user2 to the common bucket, you have two options:

### Option A: Update via Keycloak Admin UI (Immediate Effect After Re-login)

**Recommended for production use - changes persist and can be applied dynamically**

1. Open http://localhost:8180/admin (login: admin / admin)
2. Select **workspace** realm
3. Navigate to **Users** → Find the user (e.g., user1)
4. Go to **Attributes** tab
5. Modify the `policy` attribute value:
   - `common-read,user-full-access` → `common-write,user-full-access`
6. Go to **Role Mapping** tab → **Assign role** → Add `common-writer`
7. Go to **Groups** tab → **Leave** current group → **Join** `/workspace-contributors`

**To apply changes:**
- User must **re-login** to get a new JWT token with updated claims
- Or wait for token expiration (default: 1 hour)
- Workspace containers must be **restarted** to remount s3fs with new credentials:
  ```bash
  docker compose -f compose.minio.keycloak.yml restart workspace-user1
  ```

### Option B: Update realm-export.json (Requires Full Reset)

**Use for development/testing - requires database wipe**

Modify 3 things in [keycloak/realm-export.json](keycloak/realm-export.json):

**1. Change realmRoles (line 70):**
```json
"realmRoles": ["user", "common-writer"]  // was: ["user", "common-reader"]
```

**2. Change groups (line 71):**
```json
"groups": ["/workspace-contributors"]  // was: ["/workspace-users"]
```

**3. Change policy attribute (line 75):**
```json
"policy": ["common-write,user-full-access"]  // was: ["common-read,user-full-access"]
```

### Apply Changes (Option B)
```bash
# IMPORTANT: Must reset database volumes to reimport realm configuration
docker compose -f compose.minio.keycloak.yml down -v
docker compose -f compose.minio.keycloak.yml build
docker compose -f compose.minio.keycloak.yml up -d
```

## 11.1) Why Policy Changes Don't Take Effect Immediately

### 1. **PostgreSQL Persistence (Primary Reason)**
- Keycloak imports [realm-export.json](keycloak/realm-export.json) **only once** during initial startup
- After first import, all configuration is stored in PostgreSQL volumes (`postgres_data`, `keycloak_data`)
- Subsequent changes to the JSON file are **ignored** unless volumes are deleted
- This is by design - Keycloak treats the import file as initial seed data, not live configuration

### 2. **JWT Token Lifetime**
- When users authenticate, Keycloak issues a JWT token containing the `policy` claim
- Token lifespan: **3600 seconds (1 hour)** (configurable in client settings)
- MinIO and AuthZ-Proxy read the policy from the token, not from Keycloak's database
- **Old tokens remain valid** until expiration, even after updating user attributes
- Solution: Force re-login or wait for token expiration

### 3. **s3fs Mount Credentials**
- [startup/mount_minio.sh](startup/mount_minio.sh) runs **only at container startup**
- It exchanges the Keycloak token for MinIO STS (Security Token Service) credentials
- These STS credentials are used for the **entire container lifetime**
- The mounted filesystem (`/workspace/common`) uses these cached credentials
- Solution: **Restart workspace containers** to remount with new credentials:
  ```bash
  docker compose -f compose.minio.keycloak.yml restart workspace-user1
  ```

### 4. **AuthZ-Proxy Policy Cache**
- AuthZ-Proxy caches policy decisions for performance
- Cache TTL: **300 seconds (5 minutes)** (see `POLICY_DECISION_CACHE_TTL` in compose file)
- HTTP requests may use cached decisions until TTL expires
- Solution: Wait 5 minutes or restart authz-proxy service

### 5. **MinIO Policy Evaluation**
- MinIO evaluates policies **on every S3 request** (no caching)
- However, it reads the `policy` claim from the JWT token
- If the token is old, MinIO sees old policy values
- Solution: Ensure users have fresh tokens

---

## 11.2) Complete Policy Update Workflow

To ensure policy changes take effect across all layers:

```bash
# Option 1: Update via Keycloak UI (recommended)
# 1. Update user attributes/roles in Keycloak Admin UI
# 2. Force user re-authentication (logout + login)
# 3. Restart workspace containers
docker compose -f compose.minio.keycloak.yml restart workspace-user1 workspace-user2

# Option 2: Update realm-export.json (development)
# 1. Edit keycloak/realm-export.json
# 2. Wipe all data and reimport
docker compose -f compose.minio.keycloak.yml down -v
docker compose -f compose.minio.keycloak.yml up -d

# 3. Wait for services to be ready (check logs)
docker compose -f compose.minio.keycloak.yml logs -f keycloak minio

# Keycloak/MinIO not ready during mount

**Symptoms:**
- mount_minio.sh times out waiting for services
- Logs show "Keycloak not available after 30 attempts"

**Solutions4) Policy Files Reference
### Configuration Files
- [keycloak/realm-export.json](keycloak/realm-export.json) - Keycloak realm, users, roles, and policy mappings
- [compose.minio.keycloak.yml](compose.minio.keycloak.yml) - Docker Compose with direct port access
- [compose.minio.keycloak.traefik.yml](compose.minio.keycloak.traefik.yml) - Docker Compose with Traefik routing
- [minio/policies/*.json](minio/policies/) - MinIO S3 policy definitions

### Application Code
- [authz-proxy/app/main.py](authz-proxy/app/main.py) - Policy Enforcement Point (PEP) / Policy Decision Point (PDP)
- [startup/mount_minio.sh](startup/mount_minio.sh) - s3fs-fuse mounting script
- [startup/custom_startup.sh](startup/custom_startup.sh) - Workspace startup orchestration
- [Dockerfile](Dockerfile) - Workspace image with s3fs-fuse

### Test Scripts
- [scripts/test-authz.py](scripts/test-authz.py) - AuthZ-Proxy path-based policy tests
- [scripts/test-keycloak-minio.py](scripts/test-keycloak-minio.py) - Keycloak-MinIO policy claim tests
  "Version": "2012-10-17",
  "Statement": [{
    "Effect": "Allow",
    "Action": [
      "s3:GetBucketLocation",
      "s3:GetObject",
      "s3:ListBucket"
    ],
    "Resource": [
      "arn:aws:s3:::common",
      "arn:aws:s3:::common/*"
    ]
  }]
}
```

### common-write-policy.json (Full access)
```json
{
  "Version": "2012-10-17",
  "Statement": [{
    "Effect": "Allow",
    "Action": [
      "s3:GetBucketLocation",
      "s3:GetObject",
      "s3:PutObject",
      "s3:DeleteObject",
      "s3:ListBucket"
    ],
    "Resource": [
      "arn:aws:s3:::common",
      "arn:aws:s3:::common/*"
    ]
  }]
}
```

### user-full-access.json (User's own bucket)
```json
{
  "Version": "2012-10-17",
  "Statement": [{
    "Effect": "Allow",
    "Action": ["s3:*"],
    "Resource": [
      "arn:aws:s3:::${jwt:preferred_username}",
      "arn:aws:s3:::${jwt:preferred_username}/*"
    ]
  }]
}
```

**Note:** These files are **required** and mounted to minio-init container. Do not delete them.

## 15utions:**
```bash
# Increase wait timeout in startup/mount_minio.sh
max_attempts=60  # was: 30

# Check service health
docker compose -f compose.minio.keycloak.yml ps

# Ensure proper depends_on configuration
# workspace-user1 should depend on: minio, authz-proxy, keycloak (indirect)

# Restart with verbose logging
docker compose -f compose.minio.keycloak.yml logs -f workspace-user1
```

### Windows Docker Desktop specific issues

**Symptoms:**
- `/dev/fuse` device not found
- FUSE mounts fail on Windows

**Solutions:**
```bash
# Ensure Docker Desktop is running with WSL2 backend (not Hyper-V)
# Settings → General → Use the WSL 2 based engine

# Verify WSL2 kernel has FUSE support
wsl -l -v  # Should show version 2

# If using older Docker Desktop, upgrade to latest version
# FUSE support improved significantly in newer releases

# Alternative: Use Docker Desktop with Linux containers
```

## 13r compose -f compose.minio.keycloak.yml build
docker compose -f compose.minio.keycloak.yml up -d
```

### Verify Changes
```bash
# Test user1 can now write to common
docker exec -it workspace-user1 bash
$ echo "test" > /workspace/common/test.txt
$ cat /workspace/common/test.txt
test

# Run test script
python scripts/test-authz.py --test
python scripts/test-keycloak-minio.py
```

## 12) Troubleshooting

### s3fs mount failures

**Symptoms:**
- Directories `/workspace/common` or `/workspace/{user}` are empty
- Logs show "Failed to mount" errors

**Solutions:**
```bash
# Check container logs for mount errors
docker logs workspace-user1 2>&1 | grep -i "mount\|error"

# Verify FUSE device is available
docker exec workspace-user1 ls -l /dev/fuse

# Ensure privileged mode is enabled
docker inspect workspace-user1 | grep -i privileged

# Check MinIO is reachable from container
docker exec workspace-user1 curl -I http://minio:9000/minio/health/ready

# Manually test mount
docker exec -it workspace-user1 bash
$ s3fs common /mnt/test -o passwd_file=/tmp/.passwd-s3fs -o url=http://minio:9000 -o use_path_request_style -o dbglevel=debug
```

### Permission denied on file operations

**Symptoms:**
- user1 cannot create files in `/workspace/common` (expected for read-only)
- user2 cannot create files in `/workspace/common` (unexpected)

**Solutions:**
```bash
# Verify user's policy claim
docker exec workspace-user2 bash -c "curl -s -X POST http://keycloak:8080/realms/workspace/protocol/openid-connect/token \
  -d 'username=user2' -d 'password=user2password' \
  -d 'grant_type=password' -d 'client_id=minio' -d 'client_secret=minio-client-secret' \
  | jq -r '.access_token' | cut -d. -f2 | base64 -d"

# Should show "policy": "common-write,user-full-access"

# Check MinIO policy
docker exec workspace-minio mc admin policy info local common-write

# Enable s3fs debug logging
# Edit startup/mount_minio.sh, add: -o dbglevel=debug
docker compose -f compose.minio.keycloak.yml up -d --force-recreate workspace-user2
docker logs -f workspace-user2
```

### Mounts not visible in VNC/Desktop

**Symptoms:**
- Desktop shortcuts missing
- Workspace directory empty in file browser

**Solutions:**
```bash
# Check if symbolic links exist
docker exec workspace-user1 ls -la /home/kasm-default-profile/Desktop/

# Verify mount points exist
docker exec workspace-user1 mount | grep s3fs

# Check mount_minio.sh execution
docker logs workspace-user1 | grep "Desktop"

# Manually create links if missing
docker exec workspace-user1 bash -c "ln -s /workspace/common /home/kasm-default-profile/Desktop/common"
```

### Policy claim missing in JWT
- Ensure mapper is added to `minio` client.
- Ensure user has `policy` attribute.
- Re-login to refresh tokens.

### MinIO policy not applied
- Policy names must match exactly: `common-read`, `common-write`, `user-full-access`.
- Verify with:
  ```bash
  docker exec workspace-minio mc admin policy list local
  ```
- Confirm MinIO OIDC env vars with:
  ```bash
  docker exec workspace-minio printenv | grep MINIO_IDENTITY
  ```

### AuthZ‑Proxy denies valid access
- Ensure Keycloak token contains `roles` and user is in correct roles.
- Inspect with:
  ```bash
  curl -H "Authorization: Bearer <token>" http://localhost:8300/test/debug
  ```

## 11) Security Notes
- Use HTTPS/TLS in production.
- Replace default passwords.
- Use Docker secrets for credentials.
- Restrict Keycloak admin access.

## 12) References
- keycloak/realm-export.json
- compose.minio.keycloak.yml
- compose.minio.keycloak.traefik.yml
- authz-proxy/app/main.py
- scripts/test-authz.py
- scripts/test-keycloak-minio.py
