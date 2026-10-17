# Tasks: workspace storage backup

Implements the [plan](../plans/102-s3-backup.md); interfaces named
here are defined there. Each task is one reviewable unit with its own
tests, ends with the plan's test command passing, and updates the
docs it makes stale (plan, Global Constraints). Step-level, test-first
detail for a group is written just before that group starts, once the
spike has fixed versions and behaviour.

## G0: Spike

- [ ] **T001 SeaweedFS.** Pin a release `>= 4.40`. With Keycloak in
  throwaway containers, confirm and record: versioning and
  `rclone copy --s3-version-at` restore; `NoncurrentVersionExpiration`
  enforced on a versioned bucket; `AssumeRoleWithWebIdentity` with a
  Keycloak access token whose `aud` holds `workspace-backup`; a
  `${jwt:preferred_username}` prefix policy with an `s3:prefix`
  condition denies another user's prefix; the deny list and the
  `GetBucketVersioning` allow of design 4 behave as written; rclone
  works with `--s3-no-check-bucket`; role ARN format; issuer on the
  public URL with `jwksUri` on the internal address.
- [ ] **T002 rclone.** Pin a release with `--s3-version-at`, the
  `SeaweedFS` provider, session tokens, `--skip-links` and
  `--s3-no-check-bucket`; record the SHA-256.
- [ ] **T003 GitLab.** On the deployed release, confirm:
  non-confidential application with PKCE; exact redirect URIs as a
  list; `openid write_repository` scopes; 2-hour access tokens;
  refresh-token rotation and expiry; ID token on refresh; username
  claim names; device flow support.
- [ ] **T004 Keycloak.** Confirm: public `workspace-backup` client
  with PKCE, `offline_access` and "Consent required"; audience mapper
  puts `workspace-backup` in `aud`; exact per-user redirect URIs;
  `userinfo` accepts the `login-relay` token (scope includes
  `openid`) and returns `preferred_username`; `azp` is
  `dtaas-workspace`; offline idle and max settings.
  *Check*: findings recorded under "Spike findings"; design docs and
  this file updated where they differ.

## G1: Backup foundation (PR 1, PR 2)

- [ ] **T101 Status contract snapshot.** Before any change, add
  `test_status_snapshot_unchanged` for a git-only config; record the
  baseline test count and coverage.
- [ ] **T102 Backend package.** `backup/{errors,base,status,scheduler}.py`
  and `git/backend.py` per the plan; move `SyncErrorKind` into
  `BackupErrorKind` and update imports (no re-export modules). Tests:
  `test_scheduler_runs_each_backend`,
  `test_failure_in_one_backend_does_not_stop_others`,
  `test_stop_event_ends_round`. *Check*: T101 passes; test count not
  lower. (PR 1 ends here.)
- [ ] **T103 Asset model and loader.** `assets/{model,loader}.py`:
  `AssetConfig`, `GitSettings`, `BACKUP_BACKEND`, `GIT_AUTH` (default
  `token`), name rule, per-section validation; drop `ASSET_NAMES`.
  Tests: `test_private_common_configs_unchanged`,
  `test_name_rejected[Private|my-asset|a.b|""|64 chars]`,
  `test_invalid_section_skipped_others_run`,
  `test_unknown_section_now_read`.
- [ ] **T104 Writer.** `assets/writer.py`: `read_snapshot`,
  `add_asset`, `remove_asset`, TOML emitter, atomic `0600` write.
  Tests: `test_writer_refuses_changed_file`,
  `test_written_file_reloads_identically`,
  `test_written_file_mode_is_0600`.
- [ ] **T105 Wiring and live reload.** `wiring.build_backends`; the
  scheduler reloads between rounds on `request_reload()` or a changed
  modification time. Tests: `test_reload_waits_for_round`,
  `test_unparseable_edit_keeps_running`,
  `test_status_kept_for_surviving_assets`.
- [ ] **T106 Loopback bind.** `main.py` defaults `--host 127.0.0.1`;
  `custom_startup.sh` stops passing `0.0.0.0`. *Check*: from another
  container, port 8091 refuses; `/storage/status` through nginx
  answers.
- [ ] **T107 Drop NET_RAW.** `cap_drop: [NET_RAW]` on workspace
  services in `workspaces/test/dtaas/compose*.yml` and their `ci/`
  variants. *Check*: `test-compositions.yml` passes; Jupyter, VS Code
  and VNC still work. (PR 2 ends here.)

## G2: S3 storage (PR 3, PR 4)

- [ ] **T201 SeaweedFS in test compose.** Add the service to the
  multi-user compose files and the `ci/` variants that
  `test-compositions.yml` validates: pinned image, `users` network
  only, no `ports:`, no labels, `/data` volume, `s3.json` and
  `iam.json` mounts, healthcheck; example templates. Extend the
  workflow: host refuses, `user1` reaches. (PR 3.)
- [ ] **T202 S3 settings.** `s3/settings.py` reads the variables of
  design 3. Tests: `test_prefix_is_derived`,
  `test_missing_endpoint_reports_not_configured`.
- [ ] **T203 Connection store.** `login/{types,store}.py`. Tests:
  `test_store_save_is_atomic`, `test_store_mode_0600`,
  `test_connection_repr_hides_secret`.
- [ ] **T204 rclone runner and errors.** `s3/runner.py` (credentials
  in the environment only, empty stdin, time limit, stop event,
  process-group kill) and `s3/errors.py`. Tests with
  `tests/helpers/fake_rclone.py`: `test_credentials_never_in_argv`,
  `test_timeout_kills_group`, `test_error_mapping[...]`.
- [ ] **T205 S3 backend.** `s3/backend.py`: credentials, then bucket
  and versioning check, then `rclone sync` with both excludes,
  `--s3-no-check-bucket`, `--fast-list`, `--skip-links`,
  `--max-delete`, timeouts; `s3keys` credentials. Tests:
  `test_sync_refuses_empty_tree`, `test_excludes_on_every_call`,
  `test_versioning_off_refused`, `test_delete_limit_reported`.
- [ ] **T206 Image, integration, docs.** Pinned `rclone` with checksum
  in the Dockerfile. Integration against SeaweedFS with a static
  identity: sync, delete, sync, restore with `--s3-version-at`.
  Document placing `tokens/s3keys.json` by hand. (PR 4.)

## G3: Login core, Keycloak connection, front door (PR 5)

- [ ] **T301 HTTP, providers, PKCE, pending.** Public authorize URL,
  internal token, userinfo and revoke URLs. Tests:
  `test_pkce_rfc7636_vector`, `test_state_single_use`,
  `test_state_expires_after_10_minutes`,
  `test_state_bound_to_username`, `test_internal_urls_used`.
- [ ] **T302 Flow and owner check.** `flow.py`, `owner.py` with
  `tests/helpers/fake_idp.py`. Tests:
  `test_owner_mismatch_stores_nothing_and_names_both`,
  `test_denied_consent`, `test_code_redeemed_with_verifier`.
- [ ] **T303 Credentials and STS.** `credentials.py`, `sts.py` with
  `tests/helpers/fake_sts.py`. Tests:
  `test_rotated_token_saved_before_use`,
  `test_invalid_grant_is_login_expired`,
  `test_one_exchange_per_round_none_cached`,
  `test_expired_session_is_retried_next_round`,
  `test_round_isolates_connection_failure`.
- [ ] **T304 Session check.** `session.py`, 30-second cache. Tests:
  `test_foreign_user_denied`, `test_wrong_azp_denied`,
  `test_headers_ignored`, `test_keycloak_down_denies`.
- [ ] **T305 Servers and routes.** `server.py`: TCP on `127.0.0.1` and
  the control socket in a `0700` directory (pre-bound, stale socket
  removed); `web/callbacks.py`, `web/auth.py` (`/_auth`),
  `web/control.py` (login routes of design 5). Tests:
  `test_socket_directory_mode_0700`, `test_shutdown_within_8_seconds`,
  `test_callback_requires_session`.
- [ ] **T306 Front door.** nginx `auth_request /_auth` on every
  location except `/ping`, enabled only when `OIDC_ISSUER` and
  `DTAAS_LOGIN_CLIENT_ID` are set; locations for `/config`. *Check*: from
  another workspace, `user1:8080/user1/api/kernels` and
  `/user1/tools/vscode` get 401; through Traefik they work.
- [ ] **T307 Status and integration.** `connections` in status.
  Integration with Keycloak and SeaweedFS: connect by password grant
  (test only), sync, cross-user and `DeleteObjectVersion`
  `AccessDenied`, revoke gives `login_expired`, no secret in logs.

## G4: CLI (PR 6)

- [ ] **T401 Client.** `cli/client.py` over the control socket. Tests:
  `test_service_not_running_message`.
- [ ] **T402 Commands.** `asset list|add|remove|allow-delete` (offline
  writer fallback for the first three), `connect`, `disconnect`,
  `status`, built with `argparse` subparsers as `main.py` is; secrets
  only from stdin or a prompt. Tests: `test_asset_add_offline`,
  `test_connect_prints_link_and_waits`,
  `test_secret_not_accepted_as_argument`.

## G5: GitLab connection (PR 7)

- [ ] **T501 GitLab provider and owner check.** GitLab in
  `login/providers.py`; `GITLAB_OWNER_CHECK` in `login/owner.py`; the
  git backend's `git ls-remote` check after connect. Tests:
  `test_gitlab_username_check`, `test_confirm_mode_requires_confirmation`,
  `test_repo_unreachable_reported_connection_kept`.
- [ ] **T502 Git uses the connection.** `git/auth.py` takes the token
  from `gitlab_access_token()` when `GIT_AUTH = "gitlab"`, and passes
  every git credential through `GIT_CONFIG_COUNT`/`KEY_n`/`VALUE_n`
  instead of `-c`. Tests: `test_token_auth_unchanged`,
  `test_gitlab_auth_header`, `test_gitlab_auth_rejects_other_host`,
  `test_no_credential_in_git_argv`.

## G6: `/config` page (PR 8)

- [ ] **T601 Routes.** `web/config_routes.py` per design 6. Tests:
  `test_every_route_requires_session`, `test_state_has_no_secrets`.
- [ ] **T602 CSRF and headers.** `web/csrf.py` (HMAC of the username),
  `web/headers.py`. Tests: `test_post_without_csrf_denied`,
  `test_foreign_origin_denied`, `test_csrf_survives_cookie_rotation`,
  `test_security_headers_present`.
- [ ] **T603 Static page.** `web/static/{index.html,app.js}`
  (`textContent` only). Playwright: add an S3 asset, connect Keycloak,
  add a git asset with GitLab, allow deletions, remove, disconnect,
  changed-on-disk warning, expired session.

## G7: Deployment (PR 9, PR 10, DTaaS repository)

- [ ] **T701 Provisioning job.** Bucket, versioning, lifecycle;
  `s3.json`, `iam.json` with the design-4 policy; Keycloak client
  (public, PKCE, consent, audience mapper, per-user redirect URIs);
  GitLab application redirect URIs; profile `provision`. *Check*:
  second run changes nothing; adding a user and re-running adds only
  that user's URIs; workspaces hold no admin credential.
- [ ] **T702 Deployment integration.** First decide with the
  maintainers which DTaaS deployment is the target and whether it
  adopts Oathkeeper and `login-relay` (roadmap, "Deployment target for
  G7"). Then: SeaweedFS on `dtaas-users`; workspace variables and
  `cap_drop: [NET_RAW]`.
- [ ] **T703 Operator docs.** Enabling, connecting, restore runbook,
  revocation, monitoring, durability, host backups holding tokens,
  the `MAIN_USER` invariant, re-provisioning for new users;
  `mkdocs.yml` and `mkdocs-github.yml` together. *Check*: end-to-end
  in a throwaway stack; `mkdocs build` passes.

## G8: Follow-ups

- [ ] **T801** Device flow (`connect --device`), for deployments
  without Keycloak sessions.
- [ ] **T802** GitLab as STS issuer (`OIDC_STS_TOKEN = "id_token"`).
- [ ] **T803** TLS on internal hops where `NET_RAW` is needed.
- [ ] **T804** Cloud S3 guide, including the Keycloak mapper for the
  `https://aws.amazon.com/tags` claim.
- [ ] **T805** Session verifier for `traefik-forward-auth`
  deployments, so they get the front door and the page.

## Spike findings

To be filled in by T001 to T004.
