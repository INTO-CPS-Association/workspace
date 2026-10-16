# Tasks: S3 object storage backup for workspace files

Implements [plan.md](plan.md). Each task names the check that closes
it. Tasks marked **[P]** can run in parallel with the task before.

Test command for `workspaces/src/admin`:

```bash
poetry run pylint src/admin tests --rcfile=../../../.pylintrc --fail-under=9.0
poetry run pytest --cov=admin --cov-report=term-missing
```

## Phase 0: Spike

- [ ] **T001** Pick and pin a SeaweedFS release. In a throwaway
  container, confirm: bucket versioning can be enabled and listed;
  `rclone copy --s3-version-at` restores a deleted file; a
  `NoncurrentVersionExpiration` rule is accepted and enforced (use a
  1-day rule and the worker's manual trigger); a bucket-scoped
  identity gets `AccessDenied` on another bucket.
  *Check*: findings and the chosen tag recorded in this file. If
  lifecycle is not enforced, switch FR-4 to the `rclone delete
  --min-age` fallback in plan.md before PR 1.
- [ ] **T002** Pick and pin an `rclone` release with
  `--s3-version-at` and the `SeaweedFS` provider. Record its SHA-256.

## PR 1: SeaweedFS compose service (workspace)

- [ ] **T101** Add a `seaweedfs` service to
  `workspaces/test/dtaas/compose.traefik.secure.yml`: pinned image,
  `users` network only, no `ports:`, no labels, named data volume,
  `-s3.config` mount, healthcheck.
- [ ] **T102** [P] Same service in `compose.traefik.yml` and
  `compose.traefik.secure.tls.yml`.
- [ ] **T103** Add an example `s3.json` with a placeholder admin
  identity, and document generating the real one.
- [ ] **T104** Extend `test-compositions.yml`: from the host, the S3
  port refuses connections; from `user1`, the health endpoint
  answers.
  *Check*: `docker compose config` passes for all three files and
  the workflow passes.

## PR 2: Backend refactor (workspace, no behaviour change)

- [ ] **T201** Record the baseline: test count and coverage of
  `workspaces/src/admin` on `main`.
- [ ] **T202** Add `admin/backup/errors.py` with `BackupErrorKind`,
  `BackupError` and `BackupStopped`. Re-export the old names from
  `git/sync.py`.
- [ ] **T203** Add the `Backend` protocol in `admin/backup/base.py`.
- [ ] **T204** Move `SyncStatus` to `admin/backup/status.py`, keyed
  by asset and backend type. Keep `snapshot()` output identical for
  git-only configs. Leave a re-export in `git/status.py`.
- [ ] **T205** Move the scheduler loop to `admin/backup/scheduler.py`
  over `list[Backend]`.
- [ ] **T206** Add `git/backend.py` (`GitBackend`) wrapping
  `clone_asset` and `sync_once`.
- [ ] **T207** Move startup wiring to `admin/backup/bootstrap.py`;
  `main.py` calls `start_backup` and `stop_backup`.
- [ ] **T208** Add unit tests for the protocol path: a fake backend
  that succeeds, fails, raises unexpectedly and stops.
- [ ] **T209** Update the layout section of
  `workspaces/src/admin/README.md`.
  *Check*: test count equal or higher than T201, coverage not lower,
  `/storage/status` snapshot test unchanged, pylint at least 9.0.

## PR 3: S3 backend (workspace)

- [ ] **T301** Add `BACKUP_BACKEND` to `config.py` parsing, default
  `git`; route `s3` sections to `admin/s3/config.py`.
- [ ] **T302** `admin/s3/config.py`: `S3Config` dataclass with
  `repr=False` keys, required keys, placeholder refusal, endpoint
  scheme check, work-tree containment check. Unit tests per rule.
- [ ] **T303** `admin/s3/runner.py`: run `rclone` with credentials
  in the environment only, empty stdin, time limit, stop event and
  process-group kill. Unit tests with a fake `rclone`.
- [ ] **T304** `admin/s3/errors.py`: map exit codes and stderr to
  the six S3 kinds; redact both keys from any message. Table-driven
  unit tests.
- [ ] **T305** `admin/s3/backend.py`: `prepare` (bucket and
  versioning check) and `sync` (`rclone sync` with excludes,
  `--fast-list`, `--max-delete`, timeouts). Refuse to sync a missing
  or empty work tree.
- [ ] **T306** Add the `s3` key to the status snapshot, present only
  when an S3 asset exists.
- [ ] **T307** No-secrets test: run a failing and a succeeding sync
  and assert neither key appears in caplog, the status JSON or the
  fake `rclone`'s recorded argv.
- [ ] **T308** Exclusion test: the fake records `--exclude` for both
  admin directories on every call.
- [ ] **T309** Install the pinned `rclone` in
  `Dockerfile.ubuntu.noble.xfce` with checksum verification.
- [ ] **T310** Integration test against a real SeaweedFS container:
  sync, delete locally, sync, restore with `--s3-version-at`, compare
  contents. Skipped when Docker is absent.
- [ ] **T311** Docs: `config.toml.example` (commented S3 section),
  `README.md` features, `DOCUMENTATION.md` configuration, status
  kinds and restore runbook, `docs/CHANGELOG.md`.
  *Check*: test command passes; integration test passes locally and
  in CI; `docker-lint.yml` passes.

## PR 4: Provisioning (DTaaS)

- [ ] **T401** Script that, for each user and `common`, creates the
  bucket, enables versioning and applies the lifecycle rule. Idempotent.
- [ ] **T402** Create bucket-scoped identities through `weed shell`;
  reuse an existing key instead of rotating it.
- [ ] **T403** Merge the S3 sections into each user's `config.toml`
  without touching git sections; mode `0600`, workspace uid.
- [ ] **T404** Run it as a one-shot compose service under a
  `provision` profile, holding the admin key; workspace containers
  never receive it.
- [ ] **T405** Tests: second run is a no-op; user A's key gets
  `AccessDenied` on user B's bucket; generated file mode and owner.

## PR 5: secure-server integration (DTaaS)

- [ ] **T501** Add the `seaweedfs` service to
  `deploy/dtaas/docker/secure-server/docker-compose.yml` on
  `dtaas-users` only.
- [ ] **T502** Decide with the maintainers whether
  `deploy/workspace/keycloak/production/` gets it too.
- [ ] **T503** Docs: operator guide for enabling S3 backup, the
  restore runbook and backup monitoring through `/storage/status`.
  Update `mkdocs.yml` and `mkdocs-github.yml` together.
- [ ] **T504** End-to-end check in a throwaway stack: provision,
  start, create a file, wait one interval, delete it, restore it.
  *Check*: `docker compose config` passes; the round-trip succeeds;
  `mkdocs build` passes.

## Spike findings

To be filled in by T001 and T002.
