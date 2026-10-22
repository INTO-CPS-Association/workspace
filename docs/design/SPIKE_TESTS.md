# Spike tests for storage backup

The storage backup design for
[#102](https://github.com/INTO-CPS-Association/workspace/issues/102)
rests on behaviour of four third-party products. Spikes S1 to S4 of the
[feature roadmap](../FEATURE_ROADMAP.md#spike) checked that behaviour
against real containers before any feature work. They produce
findings, not features. This page summarises them; the full findings,
with every check, are in the
[task list](../tasks/102-s3-backup.md#spike-findings).

## At a glance

| Spike | Product | Pinned | Result | Harness |
| :--- | :--- | :--- | :--- | :--- |
| S1 | SeaweedFS (S3 store, STS) | `chrislusf/seaweedfs:4.48` | Done: 64 of 64 checks, 4 of 4 after a restart, lifecycle probe | `workspaces/test/dtaas/seaweedfs/spike/` |
| S2 | rclone (sync client) | v1.75.2, release zip | Done: 7 of 7 checks | `workspaces/test/dtaas/seaweedfs/spike/s2_rclone_flags.sh` |
| S3 | GitLab (OAuth provider) and Oathkeeper | GitLab 19.5.0 (not run), Oathkeeper v26.2.0 | In part: Oathkeeper confirmed; GitLab checks scripted, not run | `workspaces/test/dtaas/spike/gitlab/` |
| S4 | Keycloak (OAuth provider) | `quay.io/keycloak/keycloak:26.8.1` | Done: 58 of 58 checks | `workspaces/test/dtaas/spike/keycloak/` |

S1 and S2 ran on 2026-10-18 and again on 2026-10-21. S3 and S4 ran on
2026-10-22. The browser steps of S3 and S4 (sign-in, consent) run in
headless Chromium, and the server-side calls run from a container on
the compose network, as login-relay and workspace-admin would make
them.

## What the spikes changed

Most of the design held. These findings changed it; the design
documents are corrected.

| Spike | Finding | Change |
| :--- | :--- | :--- |
| S1 | `arn:seaweed:iam::role/WorkspaceBackup` is refused | `S3_ROLE_ARN=arn:aws:iam::role/WorkspaceBackup` |
| S1 | Operator keys come from the container's environment | No `s3.json` |
| S1 | STS does not start without `jwt.filer_signing.key`, and the filer's IAM gRPC is unauthenticated without it | `WEED_JWT_FILER_SIGNING_KEY` from `S3_SIGNING_KEY`; provisioning tests call STS, as `/healthz` stays green |
| S1 | The caller picks the session length, up to `maxSessionLength` | `maxSessionLength` 1 hour |
| S1 | `weed server` stores lifecycle rules but never applies them | A `seaweedfs-lifecycle` service runs them daily |
| S1 | rclone uploads large files in parts | The prefix policy also allows `AbortMultipartUpload` and `ListMultipartUploadParts` |
| S1 | A removed signing key stays trusted until the JWKS cache expires | Key rotation procedure in [LOGIN_RELAY](auth/LOGIN_RELAY.md) |
| S2 | `--max-delete` deletes up to the limit before it stops | The S3 backend passes `--delete-before`; exit 7 maps to `s3_delete_limit` |
| S2 | The `rclone/rclone:1.75.2` image is a different build from the release | Install rclone from the release zip, checked by SHA-256 |
| S3 | Oathkeeper's `.Subject` is the introspection `sub`, not `username` | [LOGIN_RELAY](auth/LOGIN_RELAY.md#api) corrected; the workspace check keeps reading `extra.username` |
| S4 | Keycloak answers introspection only to a client in the token's `aud` | `workspace-backup` gets an Audience mapper for `dtaas-workspace`; without it login-relay refuses every exchange |
| S4 | Internal discovery keeps the revoke and logout addresses public | workspace-admin builds the revoke address from `OIDC_INTERNAL_URL` |
| S4 | Keycloak adds `iss` to every redirect and reports refusals as `error` with `state` | The login-relay bounce passes the query on unchanged (LR-8) |

## S1 SeaweedFS

**Question.** Can SeaweedFS hold every user's backups in one versioned
bucket, give each workspace short-lived keys for its own prefix only,
in exchange for a storage pass signed by login-relay, and expire old
versions?

**How.** The SeaweedFS service of `compose.traefik.secure.yml`, with a
spike container standing in for login-relay: it holds an ES256 key
with `kid` and serves the JWKS at
`http://login-relay:8080/.well-known/jwks.json`.

**Confirmed.** Versioning keeps every overwritten and deleted version,
and the operator restores a prefix with `rclone copy --s3-version-at`.
`AssumeRoleWithWebIdentity` accepts the ES256 pass and refuses a wrong
`aud` or `iss`, an expired pass, an unknown key, a tampered signature,
`alg: none` and HS256. The `${jwt:preferred_username}` policy confines
`user1` to `user1/`, refusing `user2/`, the look-alike `user10/` and
listings without a prefix. The threat model's denies hold
(`DeleteObjectVersion`, `PutBucketVersioning`, lifecycle and policy
changes, bucket creation and deletion, `ListObjectVersions`). Data,
settings and an STS session survive a restart. The host cannot reach
port 8333.

**Not shown.** A 365-day expiry in steady state; the probe ages two
versions instead.

## S2 rclone

**Question.** Does the pinned rclone have the flags the S3 backend
needs, and do they behave as the design assumes?

**Confirmed.** `--s3-version-at`, `--s3-no-check-bucket`,
`--s3-session-token`, `--skip-links`, `--max-delete` and the
`SeaweedFS` provider exist. A remote defined only by
`RCLONE_CONFIG_<NAME>_*` variables syncs with STS keys, so no key
reaches the command line. A user's STS keys cannot list versions, so
restore stays with the operator. `rclone sync` from an empty folder
plans to delete everything, which makes workspace-admin's
`s3_empty_source` refusal necessary.

## S3 GitLab

**Question.** Does GitLab support what the GitLab deployments need: a
public `workspace-backup` application with PKCE, exact redirect URIs,
the fields of `/oauth/token/info` and `/oauth/userinfo` that
login-relay checks, 2-hour access tokens, refresh rotation and no ID
token on refresh? And which introspection fields reach Oathkeeper?

**Oathkeeper, confirmed.** With a stand-in login-relay answering the
introspection contract, `.Subject` is `sub` and `.Extra` holds
`username`, `client_id`, `scope` and the members of `ext` (`groups` at
the top level); `exp` and `token_type` do not arrive. The 30-second
introspection cache holds: two requests with one token cost one call.
An inactive token answers 401.

**GitLab, not run.** `probe.py` checks every item above and records
redacted GitLab replies for the login-relay contract tests (T303).
GitLab 19.5.0 thrashed at a 2.8 GB memory limit, even with one Puma
process and two Sidekiq threads, and the spike host's Docker VM has
4 GB in all. Running it needs a container with 4 GB, such as a
GitHub-hosted runner. Two setup facts found on the way: GitLab rejects
a root password made of common words, which fails its first boot, and
`/-/readiness` answers 404 outside its allowlist.

## S4 Keycloak

**Question.** Does Keycloak give containers internal addresses and
browsers public ones, support a public `workspace-backup` client with
PKCE, offline access and consent, enforce the 30-day idle and 180-day
offline limits, and let login-relay's client introspect backup tokens?

**How.** Keycloak with `KC_HOSTNAME=http://localhost:8180/auth` and
`KC_HOSTNAME_BACKCHANNEL_DYNAMIC=true`; a realm `dtaas` with the
design's clients and limits, and a realm `short` whose offline limits
are seconds long so expiry can be watched.

**Confirmed.** Every token's `iss` is the public URL; containers get
internal token, introspection, userinfo and JWKS addresses. The public
client redeems with its PKCE verifier and no secret; a missing, wrong
or `plain` challenge is refused, and a code works once. Redirect URIs
match exactly. `openid offline_access` returns an `Offline` refresh
token and a 300-second access token carrying `preferred_username` and
`azp: workspace-backup`. Consent is asked at the first connect only;
after a DTaaS login, connecting needs no password and leaves the DTaaS
session active. In realm `short` the maximum ended a session that was
refreshed every 20 seconds, and the idle limit refused an unused one.
Disabling the user, deleting their consent, or revoking the refresh
token from the public client each stop the backup. Only
`dtaas-workspace`, with its secret, can introspect.

**Also observed.** Each refresh returns a new refresh token, but the
old one stays valid unless the realm enables "Revoke Refresh Token".
A Keycloak session created only for the offline grant is not kept.

## Still open

- S3's GitLab checks: run `workspaces/test/dtaas/spike/gitlab/` where
  GitLab can have 4 GB, and record its findings before PR 5 (F3).
- The test compose files pin Keycloak 26.7.4; moving to 26.8.1 belongs
  with the deployment work (F9).
- SeaweedFS's lifecycle replays a meta-log that grows without bound;
  watch `/data` in long-running deployments.

## Running the spikes again

| Spike | Needs | From | Commands |
| :--- | :--- | :--- | :--- |
| S1, S2 | Docker | `workspaces/test/dtaas` | See [seaweedfs/README.md](../../workspaces/test/dtaas/seaweedfs/README.md#spike) |
| S3, Oathkeeper | Docker | `workspaces/test/dtaas/spike/gitlab` | `./oathkeeper_check.sh` |
| S3, GitLab | Docker with 4 GB for GitLab; Python with `requests`, `pyjwt`, `playwright` | `workspaces/test/dtaas/spike/gitlab` | `docker compose -f compose.yml up -d gitlab`, `./setup.sh`, `python3 -I probe.py` |
| S4 | Docker with 1 GB; Python as for S3 | `workspaces/test/dtaas/spike/keycloak` | `docker compose -f compose.yml up -d`, `python3 -I setup.py`, `python3 -I probe.py` (about 6 minutes) |

The probes drive the Chromium that Playwright has installed; set
`CHROMIUM` to use another one. Tear each stack down with
`docker compose -f compose.yml down -v`.
