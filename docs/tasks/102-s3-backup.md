# Tasks: S3 object storage backup for workspace files

Implements [the plan](../plans/102-s3-backup.md). Each task names the
check that closes it. Tasks marked **[P]** can run in parallel with
the task before.

Test command for `workspaces/src/admin`:

```bash
poetry run pylint src/admin tests --rcfile=../../../.pylintrc --fail-under=9.0
poetry run pytest --cov=admin --cov-report=term-missing
```

## Phase 0: Spike

- [ ] **T001** Pin a SeaweedFS release, 4.40 or later. With Keycloak
  and SeaweedFS in throwaway containers, confirm:
  - bucket versioning can be enabled, and `rclone copy
    --s3-version-at` restores a deleted file;
  - a `NoncurrentVersionExpiration` rule is enforced on a versioned
    bucket;
  - `AssumeRoleWithWebIdentity` with a Keycloak access token returns
    temporary credentials;
  - a policy on `<bucket>/${jwt:preferred_username}/*` with an
    `s3:prefix` condition gives `AccessDenied` on another user's
    prefix, and allows `common/`;
  - the exact role ARN format SeaweedFS expects.
  *Check*: findings and the tag recorded below. If lifecycle is not
  enforced, switch FR-4 to a scheduled `rclone delete --min-age`.
- [ ] **T002** Pin an `rclone` release with `--s3-version-at`, the
  `SeaweedFS` provider and session-token support. Record its SHA-256.
- [ ] **T003** Confirm SeaweedFS accepts an issuer on the public URL
  with `jwksUri` on the internal Keycloak address. If not, record the
  fallback (public name resolved to Traefik on `dtaas-users`).
- [ ] **T004** [P] Confirm the Keycloak device flow from inside a
  workspace: the verification link opens in the workspace browser,
  and an existing DTaaS session makes approval one click.

## PR 1: SeaweedFS compose service (workspace)

- [ ] **T101** Add `seaweedfs` to
  `workspaces/test/dtaas/compose.traefik.secure.yml`: pinned image,
  `users` network only, no `ports:`, no labels, a persistent volume at
  `/data`, both config mounts, healthcheck.
- [ ] **T102** [P] Same service in `compose.traefik.yml` and
  `compose.traefik.secure.tls.yml`.
- [ ] **T103** Example `s3.json` (admin identity placeholder) and
  `iam.json` (provider, role, policy) templates.
- [ ] **T104** Extend `test-compositions.yml`: the host cannot reach
  the S3 port; `user1` can.
  *Check*: `docker compose config` passes for all three files; the
  workflow passes.

## PR 2: Backend refactor (workspace, no behaviour change)

- [ ] **T201** Record the baseline test count and coverage on `main`.
- [ ] **T202** `admin/backup/errors.py`: `BackupErrorKind`,
  `BackupError`, `BackupStopped`; re-export old names from
  `git/sync.py`.
- [ ] **T203** `Backend` protocol in `admin/backup/base.py`.
- [ ] **T204** Move `SyncStatus` to `admin/backup/status.py`, grouped
  by backend type; `snapshot()` identical for git-only configs.
- [ ] **T205** Move the scheduler loop to `admin/backup/scheduler.py`
  over `list[Backend]`.
- [ ] **T206** `git/backend.py`: `GitBackend` wrapping `clone_asset`
  and `sync_once`.
- [ ] **T207** Move startup wiring to `admin/backup/bootstrap.py`.
- [ ] **T208** Tests with a fake backend: success, failure, unexpected
  exception, stop.
- [ ] **T209** Update the layout in `workspaces/src/admin/README.md`.
  *Check*: test count at least T201's, coverage not lower, status
  snapshot test unchanged, pylint at least 9.0.

## PR 3: S3 backend, static-key mode (workspace)

- [ ] **T301** `admin/s3/config.py`: merge environment and
  `config.toml` section; `BACKUP_BACKEND_DEFAULT`; derive the prefix
  from `MAIN_USER` and the asset; validate endpoint scheme and
  required keys; `repr=False` on secrets.
- [ ] **T302** `admin/s3/runner.py`: `rclone` with credentials in the
  environment only, empty stdin, time limit, stop event, process-group
  kill. Tests with a fake `rclone`.
- [ ] **T303** `admin/s3/errors.py`: map `rclone` exit codes and
  stderr to kinds; redact secrets. Table-driven tests.
- [ ] **T304** `admin/s3/backend.py`: `prepare` (bucket, versioning)
  and `sync` (empty-tree refusal, excludes, `--fast-list`,
  `--max-delete`, timeouts).
- [ ] **T305** Status: `s3` key present only when an S3 asset exists.
- [ ] **T306** Tests: no secret in caplog, status or argv; both
  excludes on every call; empty tree never synced.
- [ ] **T307** Install the pinned `rclone` in
  `Dockerfile.ubuntu.noble.xfce`, checksum verified.
- [ ] **T308** Integration test against SeaweedFS with a static
  identity: sync, delete, sync, restore with `--s3-version-at`.
  *Check*: test command passes; integration test passes locally and
  in CI; `docker-lint.yml` passes.

## PR 4: OIDC mode (workspace)

- [ ] **T401** `admin/s3/oidc.py`: discovery, device authorization,
  polling with `slow_down` handling, refresh, revoke. Tests against a
  local fake Keycloak.
- [ ] **T402** `admin/s3/token_store.py`: read, atomic replace
  (write, fsync, rename), mode `0600`, tolerant of a missing file.
- [ ] **T403** `admin/s3/sts.py`: `AssumeRoleWithWebIdentity` request
  and XML parsing; error codes to kinds. Tests with a fake STS.
- [ ] **T404** `admin/s3/auth.py`: per round, token to temporary
  credentials; `not_logged_in` without a token, `login_expired` on
  `invalid_grant`.
- [ ] **T405** `login` and `logout` subcommands in `main.py`; owner
  check against `MAIN_USER`; `xdg-open` the link when a display
  exists, else print it.
- [ ] **T406** Tests: wrong user refused and nothing stored; rotated
  refresh token saved; revoked token reported; no token in logs.
- [ ] **T407** Extend the integration test with Keycloak: obtain a
  token by password grant (test only), sync, cross-user
  `AccessDenied`, revoke, `login_expired`.
- [ ] **T408** Docs: `config.toml.example`, `README.md`,
  `DOCUMENTATION.md` (login, configuration table, status kinds,
  restore runbook, cloud providers), `docs/CHANGELOG.md`.
  *Check*: test command passes; integration test passes.

## PR 5: Provisioning (DTaaS)

- [ ] **T501** Create the bucket, enable versioning, apply the
  lifecycle rule. Idempotent.
- [ ] **T502** Render `s3.json` and `iam.json` from templates and the
  deployment's `.env`.
- [ ] **T503** Create or update the `workspace-backup` Keycloak client
  through the admin REST API: public, device grant, offline access,
  audience and username mappers.
- [ ] **T504** Run as a one-shot compose service, profile
  `provision`, holding both admin credentials.
  *Check*: a second run changes nothing; workspace containers have
  neither admin credential in their environment.

## PR 6: secure-server integration (DTaaS)

- [ ] **T601** Add `seaweedfs` to
  `deploy/dtaas/docker/secure-server/docker-compose.yml`, on
  `dtaas-users` only; add the S3 and OIDC variables to the workspace
  services.
- [ ] **T602** Decide with the maintainers whether
  `deploy/workspace/keycloak/production/` gets it too.
- [ ] **T603** Operator docs: enabling S3 backup, the one-time user
  login, restore, monitoring through `/storage/status`, revocation in
  Keycloak, storage durability and moving to a cloud store. Update
  `mkdocs.yml` and `mkdocs-github.yml` together.
- [ ] **T604** End-to-end in a throwaway stack: provision, start,
  log in, create a file, wait one interval, delete it, restore it.
  *Check*: `docker compose config` passes; the round-trip succeeds;
  `mkdocs build` passes.

## Spike findings

To be filled in by T001 to T004.
