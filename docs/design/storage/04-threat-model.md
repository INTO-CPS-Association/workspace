# 4. Security threat model and protection

Part of the [storage design](README.md). Covers the backup data, the
connections, the `/config` page, the CLI, the storage servers, and
the workspace front door they all depend on.

## What is protected

| Asset | Why it matters |
| :--- | :--- |
| Users' backed-up files and their versions | The point of the feature; may hold unpublished research |
| Connections (refresh tokens, static keys, pasted git tokens) | Long-lived; whoever holds one can back up as the user |
| `config.toml` | Decides where files go; a changed URL redirects data |
| SeaweedFS, Keycloak and GitLab admin credentials | Control every user's storage and identity |

## Actors

| Actor | Can reach | Trusted? |
| :--- | :--- | :--- |
| Workspace owner | Their workspace through Oathkeeper; its terminal | Yes, for their own data |
| Other DTaaS users | Their own workspace, and from it every container on `dtaas-users` | No |
| Any website the owner visits | The owner's browser | No |
| Script running in the owner's tools (a notebook, an HTML file) | The owner's origin and session | No, but can act as the owner |
| Internet attacker | Traefik's public ports | No |
| Operator | Hosts, compose, Keycloak, GitLab, SeaweedFS | Yes |

## Trust boundaries

```text
Internet ──► Traefik ──► Oathkeeper ──► workspace nginx :8080 ──► Jupyter, VS Code, VNC
                                          │                   └─► admin 127.0.0.1:8091
                       other workspaces on dtaas-users reach :8080 directly
workspace terminal ──► admin control socket (0600 in a 0700 directory)
admin ──► Keycloak (internal HTTP) / GitLab   admin ──► STS + S3   admin ──► git
```

## The front-door problem (exists today)

Every workspace shares `dtaas-users`, and nginx listens on all
interfaces. Behind it, Jupyter runs without a token and with XSRF
checks off, and VS Code runs with `--auth none`. So today any
workspace can run code in any other workspace by calling
`user1:8080/user1/api/kernels` directly, bypassing Oathkeeper. That
also defeats everything below: code running as user1 can read
user1's tokens and use the control socket.

This design therefore requires two fixes before production (roadmap
G3 and G7), not as follow-ups. Both assume the Oathkeeper and
`login-relay` stack, whose `dtaas_access_token` cookie is a Keycloak
access token (see residual risk 5 for other deployments):

1. **Session check at the front door.** nginx calls
   `auth_request /_auth` for every location except `/ping`. `/_auth`
   is served by the admin's session verifier (the same check as layer
   2 below) and answers 204 or 401. Requests that bypass Oathkeeper
   then fail at nginx.
2. **No packet spoofing between tenants.** Workspaces run with
   `cap_drop: [NET_RAW]`, so one tenant cannot ARP-spoof another and
   read the plain-HTTP traffic on `dtaas-users` (refresh grants,
   userinfo calls, STS replies with secret keys). TLS on internal hops
   is the alternative where `NET_RAW` is needed.

## Protection layers for the `/config` page and control socket

0. **Front door** (above): nginx session check on every path.
1. **Oathkeeper** (exists): validates the cookie with Keycloak and
   requires the username to match the path.
2. **Session verification in the admin.** Every `/config` request
   must carry a `dtaas_access_token` that Keycloak's `userinfo`
   endpoint accepts (signature, expiry, live session), with `azp`
   equal to `DTAAS_LOGIN_CLIENT_ID` and `preferred_username ==
   MAIN_USER`. `X-User-*` headers are ignored. Keycloak unreachable
   means 503, never a pass
   ([Login core](05-login-core.md#session-verification)).
3. **Forged-request protection.** The cookie is `SameSite=Lax`. Every
   POST needs an `X-CSRF-Token` equal to an HMAC of the session
   username under a key created at service start, and an `Origin`
   equal to `PUBLIC_BASE_URL`. The token survives the cookie's
   five-minute rotation. GET changes nothing except OAuth callbacks.
4. **OAuth callback protection.** Random `state` and PKCE verifier,
   server-side, single use, 10 minutes, bound to the session username
   of whoever started or completes the login. The verifier never
   leaves the admin. Owner checks run before anything is stored
   ([OIDC security](02-oidc-security.md#owner-checks-at-connect-time)).
   Providers accept only the exact per-user redirect URIs.
5. **Input validation.** Names `^[a-z0-9]{1,63}$`; git URLs HTTPS
   only; the GitLab connection only for `GITLAB_URL`'s host; existing
   branch checks. One validator for page, CLI and hand edits. Saves
   are atomic and refused if the file changed since it was read.
6. **Secret handling.** Secrets are write-only: never rendered, never
   returned. `Cache-Control: no-store`. Logs record events, not values.
   Disconnect revokes, then deletes.
7. **Browser hardening.** Static HTML and one script; DOM filled with
   `textContent` only. Headers: `Content-Security-Policy: default-src
   'self'; script-src 'self'; frame-ancestors 'none'`, `nosniff`,
   `Referrer-Policy: no-referrer`.
8. **Listeners.** The admin's TCP port binds `127.0.0.1`. The control
   socket lives in a directory of mode `0700` owned by the workspace
   user, so the socket's own mode does not matter; a stale socket is
   removed at start.

## Threats and controls

| # | Threat | Control |
| :--- | :--- | :--- |
| T0 | Other workspace runs code in user1's Jupyter or VS Code via `user1:8080` | 0 |
| T1 | Other user opens `/user1/config` in a browser | 1, 2 |
| T2 | Other workspace calls `user1:8080/user1/config/api/...` | 0, 2 |
| T3 | Other workspace calls `user1:8091` | 8 |
| T4 | Spoofed `X-User-Name` | 2 (ignored) |
| T5 | Malicious site submits a form in the owner's browser | 3 |
| T6 | Replayed or leaked callback URL | 4 |
| T7 | Attacker's account planted as the owner's connection | 4 (owner checks) |
| T8 | Asset name with `..` or `/` | 5 |
| T9 | Page overwrites a hand edit | 5 (version check) |
| T10 | Token leak through page, cache, Referer or logs | 6, 7 |
| T11 | Script injection into the page | 7 |
| T12 | Network access to control commands | 8 |
| T13 | Sniffing tokens on `dtaas-users` | `cap_drop: [NET_RAW]`, or TLS |
| T14 | Stolen S3 credentials delete history | Role policy denies version deletion |
| T15 | Stolen git token rewrites history | Protected branch, no force-push |
| T16 | Unmounted volume mirrored as "delete all" | Empty-source refusal, `--max-delete` |
| T17 | SeaweedFS trust-policy bypass (CVE-2026-77298) | Pin 4.40 or later |
| T18 | Abandoned grant used months later | Offline session maximum |
| T19 | Git token visible in process listings | Credentials via `GIT_CONFIG_*` environment (G5) |

## Storage-side hardening

**S3 role** (SeaweedFS IAM or AWS IAM):

- Allow `s3:GetObject`, `s3:PutObject`, `s3:DeleteObject` on
  `<bucket>/${jwt:preferred_username}/*`.
- Allow `s3:ListBucket` on `<bucket>`, limited by `s3:prefix` to
  `${jwt:preferred_username}/*`; allow `s3:GetBucketVersioning` on
  `<bucket>`.
- Deny `s3:DeleteObjectVersion`, `s3:PutBucketVersioning`,
  `s3:PutLifecycleConfiguration`, `s3:PutBucketPolicy`,
  `s3:CreateBucket`. Stolen credentials can hide current objects, but
  every version survives.
- Trust policy: issuer, audience `workspace-backup`, optionally a
  required group.

Shared areas between users are an operator decision in this policy,
not something a workspace can request.

**Git**: protect the backup branch against force-push (the sync never
force-pushes); pasted tokens should be project access tokens with
only `write_repository`; the GitLab connection asks only for
`openid write_repository`.

## Residual risks

1. **Shared origin.** `/user1/config`, Jupyter and VS Code share one
   origin, and the cookie has `path=/`. A script running in the owner's
   tools can drive the page, but it can already run any command as the
   owner. The page protects against other users and the network, not
   against the owner's own compromised tools. Isolation would need a
   host name per workspace.
2. **Owner processes read tokens.** By design: the backup runs as the
   owner.
3. **Host-side copies.** Tokens live under `$PERSISTENT_DIR`, the host
   bind mount `./files/<user>`. Any host backup of `./files` copies
   long-lived grants. Operators should protect such backups like
   credentials; the offline-session maximum bounds their life.
4. **Revocation latency.** A revoked grant stops the next round, but
   STS credentials already issued stay valid up to
   `S3_SESSION_SECONDS`. Logged-out browser sessions stay valid for up
   to 30 seconds (the `userinfo` cache).
5. **Deployments using `traefik-forward-auth`.** DTaaS
   `secure-server` (GitLab login) and `workspace/keycloak/production`
   (Keycloak login) authenticate with `traefik-forward-auth`, whose
   cookie is not a Keycloak access token. The admin cannot verify it,
   so there the front-door check stays off (it is enabled only when
   `OIDC_ISSUER` and `DTAAS_LOGIN_CLIENT_ID` are set), today's
   neighbour exposure remains, and the page and browser-mode CLI login
   are unavailable. They need a session verifier for forward-auth
   (roadmap G8) or a move to Oathkeeper and `login-relay`; the device
   flow alone gives them connections but not the front door.
6. **Single SeaweedFS on the same disk** loses data with the disk
   ([storage schemes](01-storage-schemes.md#durability-limit)).
