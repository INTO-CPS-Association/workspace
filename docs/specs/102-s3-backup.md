# Spec: S3 object storage backup for workspace files

| | |
| :--- | :--- |
| Issue | [workspace#102](https://github.com/INTO-CPS-Association/workspace/issues/102) |
| Status | Draft |
| Plan | [plan](../plans/102-s3-backup.md) |
| Tasks | [tasks](../tasks/102-s3-backup.md) |

## Problem

Workspace files are bind-mounted from host directories
(`./files/<user>` and `./files/common`). Nothing protects them beyond
the host filesystem. The git backup added in #93 needs a git remote
per user and suits small text files. Large or binary assets (FMUs,
datasets, models) bloat a git history and are slow to push.

MinIO is no longer a viable default for a self-hosted S3 store, so
this feature adopts SeaweedFS.

## Goals

1. Back up the private and common assets of every workspace to an
   S3-compatible store, with no git remote involved.
2. Keep previous versions of every file, so a deleted or overwritten
   file can be restored from a point in time.
3. Centralise access control in Keycloak: no per-user S3 keys, and
   one place to grant or revoke a user's backup.
4. Ask the user for one login inside the workspace, then nothing more.
5. Run against SeaweedFS in Docker Compose now, and against Kubernetes
   or a cloud S3 service later, by configuration only.
6. Leave existing git-backup users entirely unaffected.

## Non-goals

- A restore user interface or a restore HTTP route. Restore is a
  documented operator procedure.
- Mounting S3 as a filesystem (S3 FUSE).
- Kubernetes manifests. The design must not block them.
- Running git and S3 backup on the same asset at the same time.
- Encrypting data at rest inside SeaweedFS.
- Replicating SeaweedFS itself to a second site.

## Users and scenarios

- **Workspace user**: edits files in `/workspace/assets/<name>`.
  Logs in once; afterwards every change is in the backup within one
  sync interval.
- **Operator**: deploys DTaaS with the secure-server compose file,
  turns on S3 backup, restores a user's files after an accident,
  checks backup health and revokes access in Keycloak.

Scenarios:

1. The operator runs provisioning once. It creates the bucket, the
   SeaweedFS IAM configuration and the Keycloak client. No per-user
   step exists.
2. A user opens a terminal in the workspace and runs
   `workspace-admin login`. The workspace browser opens Keycloak; the
   user approves. Backups start at the next round.
3. A user deletes a folder by mistake. The operator restores it as it
   was an hour ago.
4. The S3 store is down. Workspaces keep working, `/storage/status`
   reports `s3_unreachable`, and backups resume when it returns.
5. An administrator revokes a user's offline session in Keycloak. The
   next round reports `login_expired` and uploads nothing.
6. The operator moves the store to AWS S3. They change the endpoint
   and role settings; the workspace image is unchanged.
7. A workspace has no S3 configuration. Nothing changes from today.

## Functional requirements

### Backup

- **FR-1** Each asset selects one backup backend: `git` (today's
  behaviour, the default) or `s3`. See *Decisions* for why not both.
- **FR-2** The S3 backend mirrors `<root>/assets/<name>`, including
  deletions, to `s3://<bucket>/<owner>/<name>/` on every sync
  interval. The common asset goes to `s3://<bucket>/common/`.
- **FR-3** The bucket has versioning enabled. A file overwritten or
  deleted locally stays retrievable as a noncurrent version.
- **FR-4** A lifecycle rule expires noncurrent versions after a
  configurable number of days (default 30).
- **FR-5** The backend refuses to sync when bucket versioning is not
  enabled, or when the work tree is missing or empty, because either
  case can destroy the only copy.
- **FR-6** An operator can restore an asset, or one path in it, to
  its state at a given time by following a documented procedure.

### Authentication

- **FR-7** `workspace-admin login` runs the OAuth 2.0 device
  authorization flow against Keycloak with scope `offline_access`. It
  shows a link and a code and opens the link in the workspace browser.
- **FR-8** On success it stores the offline refresh token in
  `$PERSISTENT_DIR/.config/workspace-admin/token.json` with mode
  `0600`. The running service picks it up at the next round; no
  restart is needed.
- **FR-9** The login is refused, and nothing is stored, unless the
  token's `preferred_username` equals the workspace owner
  (`MAIN_USER`).
- **FR-10** Each round, the service refreshes the access token, saves
  a rotated refresh token atomically, exchanges the access token for
  temporary S3 credentials with STS `AssumeRoleWithWebIdentity`, and
  passes those to the sync.
- **FR-11** `workspace-admin logout` deletes the stored token and
  revokes it in Keycloak.
- **FR-12** A static-key mode (`S3_AUTH = "keys"`) exists for S3
  providers without STS web-identity support. `oidc` is the default.

### Configuration and status

- **FR-13** Deployment-wide settings (endpoint, bucket, region,
  `rclone` provider, issuer, client id, role, STS endpoint) come from
  the container environment, set once in compose. Nothing in the
  admin is specific to SeaweedFS.
- **FR-14** `BACKUP_BACKEND_DEFAULT=s3` in the environment makes
  `private` and `common` S3-backed with no user `config.toml`. A
  section in `config.toml` overrides it per asset.
- **FR-15** `/storage/status` reports each S3 asset's last attempt,
  success and error kind. New kinds: `not_logged_in`,
  `login_expired`, `s3_auth_failed`, `s3_unreachable`,
  `s3_bucket_missing`, `s3_versioning_disabled`, `s3_empty_source`,
  `s3_timeout`, `s3_failed`.
- **FR-16** S3 backup is off unless configured. A missing or broken
  S3 setting never stops the workspace or its other assets.

### Provisioning

- **FR-17** One idempotent provisioning step creates the bucket with
  versioning and the lifecycle rule; writes the SeaweedFS IAM file
  (Keycloak provider, one role, one policy); and creates the Keycloak
  client `workspace-backup`.
- **FR-18** The policy limits each user to `<bucket>/<username>/*`
  and grants all authenticated users `<bucket>/common/*`, using the
  username claim from the token as a policy variable.

## Security requirements

- **SR-1** No secret (refresh token, access token, S3 credentials)
  appears in logs, process arguments, `/storage/status` or errors.
- **SR-2** `.config/workspace-admin/` and
  `.local/share/workspace-admin/` are never uploaded.
- **SR-3** Login and logout are command-line only. The HTTP API stays
  read-only and unauthenticated, as today.
- **SR-4** A user's credentials cannot list, read or write another
  user's prefix.
- **SR-5** Revoking the user's offline session in Keycloak stops
  their backup within one round.
- **SR-6** SeaweedFS is pinned to 4.40 or later (CVE-2026-77298:
  trust policies not enforced for direct JWT requests).
- **SR-7** With SeaweedFS in compose, the S3 server is attached only
  to `dtaas-users`, with no host port and no Traefik route. With a
  store off the host, the endpoint must be HTTPS.
- **SR-8** SeaweedFS and Keycloak admin credentials are never given
  to a workspace container.

## Non-functional requirements

- **NFR-1** A sync never blocks the HTTP API; a stopping service ends
  it within the existing 8-second shutdown limit.
- **NFR-2** Every network call and `rclone` run has a time limit.
- **NFR-3** No new Python runtime dependency: OAuth and STS calls use
  the standard library. One pinned binary, `rclone`, is added.
- **NFR-4** Functions under 25 lines, new files under 250 lines,
  pylint at least 9.0.
- **NFR-5** Workspace-admin test coverage does not drop.

## Storage and durability

SeaweedFS keeps everything under its data directory (`/data`): file
contents in volume files (`<id>.dat`, `<id>.idx`), names, metadata
and version lists in the filer's LevelDB store, and cluster metadata
from the master. Mounting one persistent volume at `/data` is enough
to survive restarts.

A single SeaweedFS has no replication. On the same disk as
`./files/`, it protects against deletion, overwrite and mistakes, not
against losing the disk or host. The operator documentation must say
so and recommend a separate disk, another host, or a cloud store.

## Acceptance criteria

1. After one `workspace-admin login`, a file created in
   `assets/private` appears under `<bucket>/<user>/private/` within
   one sync interval.
2. Deleting it locally removes it from the current listing; it can be
   restored from its previous version.
3. Logging in as another user in the workspace is refused.
4. User A's temporary credentials get `AccessDenied` on user B's
   prefix.
5. After the offline session is revoked in Keycloak, the next round
   reports `login_expired`.
6. Searching logs, status responses and the bucket for any token or
   key finds nothing.
7. With S3 not configured, every existing test passes and
   `/storage/status` returns the same JSON as before.
8. From the host the S3 port is unreachable; from a workspace it is.
9. A back-up, delete and restore round-trip passes against a real
   SeaweedFS in an integration test.

## Decisions

| Question | Decision and reason |
| :--- | :--- |
| Sync tool | `rclone` binary: sync, excludes and version restore built in; no Python dependency |
| Credentials | Keycloak device flow, offline token, STS temporary credentials; static keys only as a fallback mode |
| Bucket layout | One bucket, one prefix per user: cloud providers limit and bill buckets, and prefixes scope as well |
| One backend per asset | Git pulls remote changes into the folder while S3 mirrors it one way; together, every pull becomes a new S3 version, an S3 restore can be overwritten by the next pull, and status reports two answers for one folder |
| Provisioning location | DTaaS repository: the user list, compose files, network and Keycloak live there; the workspace image knows none of them |
| Status JSON | S3 assets reported beside `repositories`; existing keys unchanged |
| Restore | Documented runbook; no command yet |

## Open questions

1. Should `common/` be writable by every user, as the shared git
   repository is today, or read-only with one writer?
2. Is 30 days the right noncurrent-version retention for course
   deployments, given host disk?
3. Which Keycloak offline-session idle and maximum lifespan should
   DTaaS set? They decide how often a long-stopped workspace needs a
   new login.
4. Does every DTaaS deployment use the same name for `MAIN_USER` and
   the Keycloak username? FR-9 relies on it.
