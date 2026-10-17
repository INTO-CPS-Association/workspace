# 5. Login core

Part of the [storage design](README.md). The login core is the code in
workspace-admin that creates, stores, refreshes and removes
[connections](03-connect-backends.md), and verifies browser sessions.
The `/config` page, the CLI and nginx are its clients; the backends
only ask it for credentials.

## Responsibilities

1. Start a login for a provider and return where the user must go.
2. Complete it from the callback: verify `state`, redeem the code with
   the PKCE verifier, run the owner check, store the connection.
3. Hand out fresh credentials to backends each round, saving rotated
   refresh tokens first.
4. Disconnect: revoke and delete.
5. Verify browser sessions for nginx (`/_auth`) and the `/config`
   routes.

It never decides which assets exist, never runs `git` or `rclone`,
and imports nothing from `admin/backup`, `admin/git` or `admin/s3`.

## Modules (`admin/login/`)

| Module | Interface | Notes |
| :--- | :--- | :--- |
| `types.py` | `ProviderName`, `ConnectionState`, `Connection` | Shared literals and the stored record |
| `http.py` | `post_form`, `get_json` with timeouts and size limits | `urllib.request`; failures become `LoginError` |
| `providers.py` | `Provider` (endpoints, scopes, username claim); `keycloak()`, `gitlab()` | Keycloak endpoints: authorize on `OIDC_ISSUER`, token, userinfo and revoke on `OIDC_INTERNAL_URL`. GitLab from discovery on `GITLAB_URL` |
| `pkce.py` | `new_verifier()`, `challenge(verifier)`, `new_state()` | `secrets`, `hashlib`; S256 only |
| `pending.py` | `PendingLogins.add(state, login)`, `take(state, username)` | In memory; single use; 10-minute expiry |
| `flow.py` | `start(provider, username, poll_id=None) -> str`, `complete(provider, code, state, username) -> Connection` | Browser flow; `redirect_uri` built from `PUBLIC_BASE_URL` |
| `owner.py` | `check(provider, claims, main_user)` | Username rules of [OIDC security](02-oidc-security.md#owner-checks-at-connect-time); `confirm` mode returns "needs confirmation" |
| `store.py` | `load`, `save`, `delete`, `locked(provider)` | `tokens/<provider>.json`; temp file, `fsync`, rename; `0600`; `fcntl` lock |
| `sts.py` | `S3Credentials`; `assume_role(token, role_arn, seconds) -> S3Credentials` | `AssumeRoleWithWebIdentity` request; XML reply parsed with `xml.etree` under a size limit |
| `credentials.py` | `s3_credentials() -> S3Credentials`, `gitlab_access_token() -> str` | Refresh, save rotation, STS; once per round |
| `session.py` | `verify(access_token) -> str` | Keycloak `userinfo`; returns the username |
| `errors.py` | `LoginError(kind)`, `SessionError` | Kinds below |

All network code uses the standard library, so no runtime dependency
is added.

### Session verification

Verifying a JWT signature locally needs an RSA library the image does
not have. Instead `session.verify` sends the session's access token
(cookie `dtaas_access_token`, or an `Authorization: Bearer` header) to
Keycloak's `userinfo` endpoint. Keycloak validates signature, expiry
and session and returns `preferred_username`. The admin then reads
`azp` from the same token's payload, which Keycloak has just
validated, and requires `azp == DTAAS_LOGIN_CLIENT_ID` and username
`== MAIN_USER`. Results are cached for 30 seconds by token hash.

`userinfo` needs the token's scope to include `openid`; `login-relay`
requests `openid profile`
(`workspaces/test/dtaas/login-relay/_helpers.py`), so it does; task
T004 re-confirms.

nginx calls the same check for every request through
`auth_request /_auth` ([threat model](04-threat-model.md#the-front-door-problem-exists-today)).
The workspace then depends on Keycloak for access, as Oathkeeper
already does.

### Trusting tokens from the token endpoint

At connect time the admin reads claims from tokens it received
directly from the token endpoint. OpenID Connect allows relying on the
connection instead of the signature in that case. Inside compose that
connection is plain HTTP on `dtaas-users`, which is why dropping
`NET_RAW` (or internal TLS) is a requirement, not a follow-up.

## Binding a login to its user

A pending login stores `provider`, `verifier`, the **session username**
that started it, an optional `poll_id`, and an expiry.

| Started by | Username comes from | Completed by |
| :--- | :--- | :--- |
| Page | The verified session | Callback in the same browser |
| CLI | `MAIN_USER` (the socket is owner-only) | Callback in the user's browser |

The callback verifies the browser session and calls
`complete(..., username=<session username>)`. `take` refuses a `state`
that is unknown, expired, already used, or stored for another
username. The `poll_id` only tells the CLI's waiting request which
login finished; it is not a credential.

## Control routes (Unix socket only)

| Route | Purpose |
| :--- | :--- |
| `POST /control/logins` `{provider}` | Start a login; returns `{poll_id, authorize_url}` |
| `GET /control/logins/<poll_id>` | Wait up to 30 seconds; returns `pending`, `connected`, `needs_confirmation` or an error kind |
| `POST /control/logins/<poll_id>/confirm` | Confirm the shown GitLab account in `confirm` mode |
| `POST /control/connections/<provider>/disconnect` | Disconnect |
| `PUT /control/connections/s3keys` | Store a static key pair (body from stdin) |

Asset routes are listed in [Configuration](06-config.md#control-routes).

## Sequences

### Connect from the page

```mermaid
sequenceDiagram
    participant B as Browser
    participant N as nginx
    participant C as config routes
    participant L as login core
    participant P as Provider
    B->>N: POST /user1/config/api/connect/keycloak
    N->>C: auth_request ok; proxy to 127.0.0.1:8091
    C->>L: session.verify, CSRF check
    C->>L: flow.start(keycloak, username)
    L-->>B: 200 {authorize_url}
    B->>P: authorize (SSO), consent
    P-->>B: 302 /user1/config/callback/keycloak?code&state
    B->>C: GET callback (session verified)
    C->>L: flow.complete(code, state, username)
    L->>P: token (code, verifier, redirect_uri), internal URL
    L->>L: owner.check, store.save
    C-->>B: 302 /user1/config#connected
```

### Credentials for a round

```mermaid
sequenceDiagram
    participant S as Scheduler
    participant L as credentials.py
    participant St as store.py
    participant K as Keycloak
    participant T as STS
    S->>L: s3_credentials()
    L->>St: lock keycloak; load
    L->>K: refresh_token grant
    K-->>L: access (+ new refresh)
    L->>St: save new refresh; unlock
    L->>T: assume_role
    T-->>L: S3Credentials
    L-->>S: credentials (memory only, this round)
```

`invalid_grant` becomes `login_expired`. The stored file is kept so
the page can show who was connected; reconnect replaces it.

### Disconnect

Lock, load, call the revocation endpoint (failure logged, not fatal),
delete the file, unlock, drop pending logins for that provider.

## Error kinds

| Kind | Meaning | Status kind ([03](03-connect-backends.md#status-kinds)) |
| :--- | :--- | :--- |
| `provider_unreachable` | Discovery, token, userinfo or STS endpoint unreachable | `login_unreachable` or `s3_unreachable` |
| `login_denied` | User declined consent | none; page shows "not connected" |
| `login_timeout` | Pending login expired | none; start again |
| `state_invalid` | Unknown, used, expired or other user's `state` | none; start again |
| `owner_mismatch` | Token belongs to another user; both names shown | none; log in as `MAIN_USER` |
| `login_expired` | Refresh rejected | `login_expired` |
| `sts_denied` | STS refused the token | `s3_auth_failed` |

Messages never include tokens, codes or provider response bodies.

## Testing

- Unit: PKCE vectors from RFC 7636; pending-login expiry, single use
  and username binding; store atomicity (kill between write and
  rename); rotation saved before use; lock prevents disconnect and
  refresh races; `azp` and username checks; 503 when Keycloak is down.
- Fakes: `tests/helpers/fake_idp.py` (`http.server` serving discovery,
  authorize redirect, token, userinfo, revoke, device), with switches
  for denial, `invalid_grant`, rotation and slow replies;
  `tests/helpers/fake_sts.py` returning fixed XML or errors.
- Integration: real Keycloak and SeaweedFS; the browser step replaced
  by Keycloak's password grant in tests only.
