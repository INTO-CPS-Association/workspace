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

1. Back up the private and common assets of every workspace to a
   self-hosted S3-compatible store, with no git remote involved.
2. Keep previous versions of every file, so a deleted or overwritten
   file can be restored from a point in time.
3. Run under Docker Compose now, and on Kubernetes later without
   changing the backup code.
4. Leave existing git-backup users entirely unaffected.

## Non-goals

- A restore user interface or a restore HTTP route. Restore is a
  documented operator procedure.
- Mounting S3 as a filesystem (S3 FUSE).
- Kubernetes manifests. The design must not block them; it does not
  deliver them.
- Running git and S3 backup on the same asset at the same time.
- Encrypting data at rest inside SeaweedFS.

## Users and scenarios

- **Workspace user**: edits files in `/workspace/assets/<name>`.
  Expects every change to be in the backup within one sync interval,
  without doing anything.
- **Operator**: deploys DTaaS with the secure-server compose file.
  Turns on S3 backup with one provisioning step, restores a user's
  files after an accident, and checks backup health per user.

Scenarios:

1. The operator runs provisioning. Every user gets a bucket and
   credentials, and the next workspace start begins backing up.
2. A user deletes a folder by mistake. The operator restores it as it
   was an hour ago.
3. The S3 store is down. Workspaces keep working; `/storage/status`
   reports `s3_unreachable` for each S3 asset; backups resume when the
   store returns.
4. A workspace has no S3 configuration. Nothing changes from today.

## Functional requirements

- **FR-1** The admin service supports a per-asset backup backend:
  `git` (today's behaviour, the default) or `s3`.
- **FR-2** The S3 backend mirrors `<root>/assets/<name>` to a bucket
  and optional prefix on every sync interval, including deletions.
- **FR-3** Buckets have versioning enabled. A file overwritten or
  deleted locally stays retrievable as a noncurrent version.
- **FR-4** A lifecycle rule expires noncurrent versions after a
  configurable number of days (default 30).
- **FR-5** The S3 backend refuses to sync to a bucket whose
  versioning is not enabled, and reports it, because a mirror with
  deletions and no versions can destroy the only copy.
- **FR-6** `/storage/status` reports each S3 asset's last attempt,
  last success and last error kind, with these new kinds:
  `s3_auth_failed`, `s3_unreachable`, `s3_bucket_missing`,
  `s3_versioning_disabled`, `s3_timeout`, `s3_failed`.
- **FR-7** S3 backup is disabled unless an asset selects it in
  `config.toml`. A missing or unusable S3 section never stops the
  workspace or its other assets.
- **FR-8** A provisioning step creates, per user, a bucket with
  versioning and lifecycle enabled, and an identity that can only
  reach that bucket. A shared `common` bucket gets one identity per
  user with read-write access. Re-running it changes nothing.
- **FR-9** Provisioning writes each user's S3 settings into that
  user's `config.toml` with mode `0600`.
- **FR-10** An operator can restore an asset, or a single path in
  it, to its state at a given time, by following a documented
  procedure.

## Security requirements

- **SR-1** No secret appears in logs, process arguments,
  `/storage/status` responses or error messages.
- **SR-2** The admin service's own directories
  (`.config/workspace-admin/` and `.local/share/workspace-admin/`)
  are never uploaded, whatever the asset layout.
- **SR-3** The S3 server is attached only to the internal
  `dtaas-users` network. It publishes no host port and has no
  Traefik route.
- **SR-4** One user's credentials cannot list, read or write another
  user's bucket.
- **SR-5** The S3 admin credentials used by provisioning are never
  given to a workspace container.

## Non-functional requirements

- **NFR-1** A sync never blocks the HTTP API, and a stopping service
  ends the sync within the existing shutdown limit (8 seconds).
- **NFR-2** Every S3 command has a time limit, as git commands do.
- **NFR-3** No new Python runtime dependency. One pinned binary
  (`rclone`) is added to the image.
- **NFR-4** The code follows the repository limits: functions under
  25 lines, new files under 250 lines, pylint score at least 9.0.
- **NFR-5** Workspace-admin test coverage does not drop.

## Acceptance criteria

1. With S3 configured, a file created in `assets/private` appears in
   the user's bucket within one sync interval.
2. Deleting that file locally removes it from the current listing,
   and it can still be restored from its previous version.
3. With S3 not configured, every existing test passes unchanged and
   `/storage/status` returns the same JSON as before.
4. From the host, the S3 port is not reachable. From a workspace
   container, it is.
5. User A's key gets `AccessDenied` on user B's bucket.
6. Searching logs, status responses and the bucket contents for the
   secret keys finds nothing.
7. A full back-up, delete and restore round-trip passes in an
   integration test against a real SeaweedFS.

## Decisions taken in this spec

The issue left these open. Each one is the plan's recommendation and
is open to review on the pull request.

| Question | Decision |
| :--- | :--- |
| Sync tool | `rclone` binary, not `boto3` |
| Status JSON | New S3 assets reported beside `repositories`, existing keys unchanged |
| Restore | Documented runbook; no CLI subcommand yet |
| Git and S3 on one asset | One backend per asset |
| Where provisioning lives | DTaaS repository, beside the secure-server compose file |

## Open questions

1. Should the common bucket be read-write for every user (as the
   shared git repository is today), or read-only with one writer?
2. Is a 30-day noncurrent-version retention the right default for
   course deployments, given disk on the host?
3. Which SeaweedFS release do we pin? Versioning and lifecycle
   enforcement on versioned buckets are recent; the pin must include
   both (verified in task T001).
