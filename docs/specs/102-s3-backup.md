# Spec: workspace storage backup to git and S3

| | |
| :--- | :--- |
| Issue | [workspace#102](https://github.com/INTO-CPS-Association/workspace/issues/102) |
| Status | Draft |
| Design | [design/storage](../design/storage/README.md) |
| Roadmap | [FEATURE_ROADMAP.md](../FEATURE_ROADMAP.md) |
| Plan | [plan](../plans/102-s3-backup.md) |
| Tasks | [tasks](../tasks/102-s3-backup.md) |

## Problem

Workspace files are bind-mounted from host directories and protected
by nothing beyond the host filesystem. The git backup (#93) needs a
git remote and a hand-pasted token, and suits small text files.
Large or binary assets bloat a git history. Tokens are created,
pasted and renewed by hand, with no central revocation. MinIO is no
longer a viable default S3 server, so this feature adopts SeaweedFS.

## Goals

1. Back up named folders (assets) to git or S3, one scheme per asset.
2. Keep previous versions of S3-backed files for point-in-time restore.
3. Centralise access: Keycloak for S3, GitLab for git; revocation in
   one place; no per-user S3 keys in the default setup.
4. One login per provider, from the user's own browser, then nothing.
5. Manage assets and connections from a web page, a CLI or by
   editing `config.toml`.
6. SeaweedFS in Docker Compose now; cloud S3 later by configuration.
7. Existing git-backup configurations keep working.

## Non-goals

Restore from the page or CLI (runbook only); renaming assets; shared
areas chosen by the workspace; S3 FUSE mounts; Kubernetes manifests;
SeaweedFS replication; encryption at rest in SeaweedFS; device flow
and GitLab as STS issuer (roadmap G8).

## Users and scenarios

- **Workspace user** adds assets and connects providers, once.
- **Operator** provisions storage, Keycloak and GitLab once (again
  when users are added), monitors status, restores files and revokes
  access.

1. The operator runs provisioning: bucket, versioning, lifecycle,
   SeaweedFS IAM, Keycloak client, GitLab application redirect URIs.
2. The user opens `/<user>/config`, adds asset `models` on S3 and
   clicks Connect with Keycloak; the DTaaS session means one consent
   click. Backups start next round.
3. The user adds git asset `thesis` on the deployment's GitLab and
   connects GitLab; no token is pasted.
4. A terminal user does the same with `workspace-admin asset add` and
   `workspace-admin connect`, approving in their own browser.
5. A user deletes a folder by mistake; the operator restores it as it
   was an hour ago.
6. The S3 server is down; workspaces keep working, status reports
   `s3_unreachable`, backups resume afterwards.
7. An administrator revokes the user's offline session; the next
   round reports `login_expired` and the page offers Reconnect.
8. A workspace with today's `config.toml` behaves as before.

## Requirements

### Assets and configuration ([design 1](../design/storage/01-storage-schemes.md), [6](../design/storage/06-config.md))

- **FR-1** Asset names match `^[a-z0-9]{1,63}$`; no name is special;
  the `private`/`common` limit is lifted.
- **FR-2** Each asset has one backend, `git` (default) or `s3`.
- **FR-3** Assets can be added and removed; removal stops the backup
  and deletes neither the folder nor stored copies.
- **FR-4** `config.toml` stays hand-editable. Page and CLI write it
  through one validator, atomically, refusing to overwrite a file
  changed since it was read. Comments are lost on a machine save, with
  a warning before the first.
- **FR-5** Changes apply without restart. Validation is per section:
  an invalid section is logged and skipped; the others run.
- **FR-6** `private` and `common` sections valid today keep their
  meaning. Other `[assets.*]` sections, ignored today, are read from
  G1 on; the release notes say so.

### S3 backup ([design 1](../design/storage/01-storage-schemes.md))

- **FR-7** An S3 asset is mirrored, including deletions, to
  `s3://<S3_BUCKET>/<MAIN_USER>/<name>/` every round; the prefix is
  derived. `MAIN_USER` must equal the Keycloak username.
- **FR-8** Versioning keeps overwritten and deleted objects; a
  lifecycle rule expires noncurrent versions after N days (default
  30).
- **FR-9** The backend refuses to sync when versioning is off or the
  folder is missing or empty; skips symbolic links; and stops at
  `S3_MAX_DELETE` deletions (default 1000) until the user allows them
  once.
- **FR-10** An operator can restore an asset or path to a point in
  time by a documented procedure.

### Connections ([design 2](../design/storage/02-oidc-security.md), [3](../design/storage/03-connect-backends.md), [5](../design/storage/05-login-core.md))

- **FR-11** Connections: `keycloak` (S3 via STS), `gitlab` (git),
  `s3keys` (static S3 keys for services without STS); at most one of
  each per workspace.
- **FR-12** `keycloak` and `gitlab` are created by the browser
  authorization-code flow with PKCE (S256), public clients, and the
  exact callback `<PUBLIC_BASE_URL>/<user>/config/callback/<provider>`.
- **FR-13** Owner check before storing: Keycloak `preferred_username
  == MAIN_USER`; GitLab username `== MAIN_USER`, or the user confirms
  the shown account when `GITLAB_OWNER_CHECK = "confirm"`. A mismatch
  names both values.
- **FR-14** Every round obtains fresh credentials: refresh, save any
  rotated refresh token atomically before use, and for S3 exchange the
  access token with STS `AssumeRoleWithWebIdentity` for
  `S3_SESSION_SECONDS` (default 3600). Nothing is cached across rounds.
- **FR-15** Disconnect revokes at the provider, then deletes the
  stored connection.
- **FR-16** Git assets choose `GIT_AUTH = "gitlab"` or `"token"`
  (default); pasted `GIT_REPO_TOKEN` stays fully supported.
- **FR-17** Deployment-wide settings come from the environment
  ([table](../design/storage/03-connect-backends.md#deployment-wide-settings));
  nothing in the admin is specific to SeaweedFS.

### Clients ([design 6](../design/storage/06-config.md))

- **FR-18** A `/<user>/config` page lists connections and assets with
  status, and adds, removes, connects, disconnects and allows
  deletions.
- **FR-19** CLI subcommands `asset list|add|remove|allow-delete`,
  `connect|disconnect <provider>` and `status`; `asset list|add|remove`
  work without the running service.
- **FR-20** A CLI login prints the provider link; the user approves
  in their own browser; the CLI waits for completion.

### Status

- **FR-21** `/storage/status` adds `s3` and `connections` only when
  used, with the kinds listed in
  [design 3](../design/storage/03-connect-backends.md#status-kinds).
  Otherwise the response is byte-identical to today's.

### Provisioning (DTaaS)

- **FR-22** One idempotent job creates the bucket with versioning and
  lifecycle; writes SeaweedFS `s3.json` and `iam.json`; creates the
  Keycloak `workspace-backup` client (public, PKCE, consent, audience
  mapper); and registers the per-user redirect URIs on it and on the
  GitLab application. It writes no user file and creates no per-user
  secret.

## Security requirements ([design 4](../design/storage/04-threat-model.md))

- **SR-1** No secret in logs, process arguments, status, page
  responses or error messages; secret fields are write-only. Git
  credentials reach git through the environment from G5 on.
- **SR-2** `.config/workspace-admin/` and
  `.local/share/workspace-admin/` are never uploaded.
- **SR-3** The admin's TCP listener binds `127.0.0.1`; control routes
  are served only on a Unix socket in a `0700` directory.
- **SR-4** In deployments with Oathkeeper and `login-relay`, nginx
  checks the session (`auth_request`) for every path except `/ping`,
  so no workspace tool is reachable by bypassing Oathkeeper. Other
  deployments keep today's exposure until roadmap G8.
- **SR-5** Every `/config` request and `/_auth` check is verified
  through Keycloak `userinfo`, `azp == DTAAS_LOGIN_CLIENT_ID` and
  `preferred_username == MAIN_USER`; `X-User-*` headers are ignored;
  failure to verify denies.
- **SR-6** Every state-changing request needs an `X-CSRF-Token` (HMAC
  of the session username) and `Origin == PUBLIC_BASE_URL`; GET changes
  nothing except callbacks.
- **SR-7** OAuth `state` and PKCE verifier are server-side, single
  use, bound to the session username, valid 10 minutes.
- **SR-8** The page sends CSP `default-src 'self'; script-src 'self';
  frame-ancestors 'none'`, `nosniff`, `Referrer-Policy: no-referrer`,
  `Cache-Control: no-store`.
- **SR-9** The S3 role allows only the actions in
  [design 4](../design/storage/04-threat-model.md#storage-side-hardening)
  under the user's prefix and denies version deletion and bucket
  configuration changes.
- **SR-10** SeaweedFS 4.40 or later (CVE-2026-77298). Off-host
  endpoints use HTTPS.
- **SR-11** Workspaces run with `cap_drop: [NET_RAW]`, or all
  internal hops use TLS.
- **SR-12** SeaweedFS, Keycloak and GitLab admin credentials never
  reach a workspace.

## Non-functional requirements

- **NFR-1** Sync never blocks HTTP; shutdown within 8 seconds.
- **NFR-2** Every network call and subprocess has a time limit.
- **NFR-3** No new Python runtime dependency; one pinned `rclone`.
- **NFR-4** New files under 250 lines, functions under 25, pylint
  9.0+; files already over 250 lines do not grow.
- **NFR-5** Workspace-admin coverage does not drop.

## Acceptance criteria

1. A file in an S3 asset appears under `<bucket>/<user>/<name>/`
   within one round after a single Keycloak connect.
2. A locally deleted file can be restored from its previous version.
3. Logging in as another user is refused, stores nothing, and names
   both users.
4. User A's credentials get `AccessDenied` under user B's prefix and
   on `DeleteObjectVersion`.
5. A revoked offline session yields `login_expired` next round.
6. A git asset with `GIT_AUTH = "gitlab"` pushes without a pasted
   token, and no token appears in `ps` output.
7. From another workspace, requests to `user1:8080` for Jupyter,
   VS Code, `/config` or `/_auth`, and to `user1:8091`, are denied.
8. A POST without CSRF token or with a foreign `Origin` is denied.
9. Logs, status, page responses and the bucket contain no secret.
10. Today's configurations and tests pass unchanged, and
    `/storage/status` is byte-identical for them.
11. The S3 port is unreachable from the host and reachable from a
    workspace; workspaces lack `NET_RAW`.
12. A back-up, delete, restore round-trip passes against real
    Keycloak and SeaweedFS.
