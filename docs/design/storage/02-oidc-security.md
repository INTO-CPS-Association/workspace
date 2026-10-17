# 2. OIDC security

Part of the [storage design](README.md). This document explains the
tokens, the login flows and how Keycloak and GitLab differ. How the
tokens are used per backend is in
[Connect storage backends](03-connect-backends.md); the code that
runs the flows is in [Login core](05-login-core.md).

## Roles

| Role | S3 assets | Git assets |
| :--- | :--- | :--- |
| Identity provider | Keycloak realm | GitLab instance |
| OAuth client | Keycloak client `workspace-backup` | GitLab application `workspace-backup` |
| Resource server | STS and S3 (SeaweedFS, or AWS) | GitLab git over HTTPS |
| Token holder | workspace-admin in the user's workspace | same |

Both clients are **public** (Keycloak: client authentication off;
GitLab: "Confidential" unticked), so the workspace image carries no
client secret. PKCE (S256) replaces the secret by proving that whoever
redeems a code also started the login.

Provisioning configures the Keycloak client with:

- **Consent required** on, so the user sees what offline access means;
- an **audience mapper** adding `workspace-backup` to the access
  token's `aud`. Keycloak access tokens carry `aud: account` by
  default, and STS checks the audience;
- `preferred_username` in the access token (default mappers);
- one exact redirect URI per user (below).

## Tokens

| Token | Issued by | Lifetime | Stored | Used for |
| :--- | :--- | :--- | :--- | :--- |
| `dtaas_access_token` cookie | Keycloak, via `login-relay` | Minutes | Browser only | Proving the browser session to Oathkeeper, nginx and the `/config` page |
| Offline refresh token | Keycloak | Until 30 days unused, or a configured maximum | `tokens/keycloak.json` | Getting access tokens without the user |
| Keycloak access token | Keycloak | 5 minutes | Memory | Web identity for STS |
| STS temporary credentials | SeaweedFS or AWS STS | `S3_SESSION_SECONDS`, default 3600 | Memory, passed to `rclone` | Signing S3 requests |
| GitLab refresh token | GitLab | No fixed expiry; replaced on each use | `tokens/gitlab.json` | Getting GitLab access tokens |
| GitLab access token | GitLab | 2 hours, fixed | Memory | Git over HTTPS as `oauth2:<token>` |
| GitLab ID token | GitLab | About 2 minutes | Memory | Identity claims at connect time |
| Static S3 key pair | Operator | Until rotated | `tokens/s3keys.json` | S3 services without STS, and tests |
| Pasted git token | User, in GitLab or another host | Host policy; GitLab 365 days by default | `config.toml` | Git over HTTPS |

These are current values for supported releases; task T003 confirms
the GitLab ones against the deployed release.

### Why a refresh token at all

Backups run every few minutes, also when the user is not logged in.
The browser session cookie lasts minutes and belongs to `login-relay`'s
client, so the admin needs its own long-lived grant. A refresh token
is that grant: held by the admin, scoped to one client, revocable
centrally.

### How long the grants live

- **Keycloak.** Every round refreshes, so a running workspace never
  reaches the 30-day "Offline Session Idle" limit. It ends when the
  workspace is stopped longer than that, when an administrator
  revokes it, or at "Offline Session Max" if enabled. DTaaS should
  enable the maximum (for example 90 to 180 days) so abandoned grants
  end on their own.
- **GitLab.** The refresh token has no fixed expiry; each use returns
  a new one. It ends when the user or an administrator revokes the
  application, or the user is blocked.

Both may rotate the refresh token on every refresh. The admin saves
the new one before using the access token, by temp file and rename,
under a per-provider lock. When a grant ends, status reports
`login_expired` and the page offers **Reconnect**.

## Login flows

### Browser login with PKCE (primary)

```mermaid
sequenceDiagram
    participant B as User's browser
    participant A as workspace-admin
    participant P as Keycloak or GitLab
    B->>A: POST /<user>/config/api/connect/<provider> (session, CSRF)
    A->>A: create state, PKCE verifier; keep server-side
    A-->>B: authorize URL with code_challenge, state
    B->>P: GET authorize
    P-->>B: consent (first time), redirect with code, state
    B->>A: GET /<user>/config/callback/<provider>?code&state
    A->>P: POST token (code, code_verifier, redirect_uri)
    P-->>A: access, refresh (and ID) token
    A->>A: owner check, store refresh token 0600
    A-->>B: "Connected as <user>"
```

- **Keycloak** asks no password: the user's DTaaS browser holds the
  Keycloak SSO session from logging in to DTaaS.
- **GitLab** asks no password if the user is already signed in to
  GitLab in that browser; otherwise it asks once. DTaaS login does not
  create a GitLab session unless the deployment logs in through
  GitLab.

The VNC desktop browser is not used: it has no session at all.

The CLI uses the same flow: it starts the login over the control
socket and prints the authorize URL ([Config](06-config.md#cli)).

### Redirect URIs

GitLab matches redirect URIs exactly, and Keycloak allows a wildcard
only at the end. Provisioning therefore registers one exact URI per
user on both clients:

```text
https://<server>/<user>/config/callback/keycloak
https://<server>/<user>/config/callback/gitlab
```

Adding a user means re-running provisioning. No secret is created per
user; only this list grows.

### Device authorization (later)

`workspace-admin connect keycloak --device`: the admin asks for a
device code, prints a short code and a link, and polls. The user
approves in any browser; no callback or session check is involved.
Keycloak supports it; GitLab only in recent releases. It is the path
for deployments without Keycloak sessions (roadmap G8).

### Flows not used

| Flow | Why not |
| :--- | :--- |
| Loopback redirect to `127.0.0.1` | The user's browser runs outside the container and cannot reach it |
| Client credentials | Needs a client secret per workspace, and the token is not the user's |
| Token exchange from the session cookie | Needs a confidential client, so a secret in every workspace |
| `login-relay` keeps a refresh token at DTaaS login | It would hold every user's grant, and every user would be asked for offline access |
| Password grant | Deprecated; the admin would see passwords. Integration tests only |

## Keycloak and GitLab compared

| Aspect | Keycloak | GitLab |
| :--- | :--- | :--- |
| Discovery | `<realm>/.well-known/openid-configuration` | `<gitlab>/.well-known/openid-configuration` |
| Authorize, token | `<realm>/protocol/openid-connect/auth`, `/token` | `/oauth/authorize`, `/oauth/token` |
| Revoke | `<realm>/protocol/openid-connect/revoke` | `/oauth/revoke` |
| Public and internal addresses | Differ in compose: authorize uses the public URL, token, userinfo and revoke the internal one | One public URL |
| Scopes requested | `openid offline_access` | `openid write_repository` |
| Long-lived grant | Offline token; idle and max per realm or client | Refresh token; no fixed expiry |
| Access token format | Signed JWT; usable as STS web identity | Opaque string; not verifiable by STS |
| Username claim | `preferred_username` | `nickname`; `preferred_username` in recent releases |
| Audience | Needs an audience mapper | Client id in the ID token |
| Redirect URIs | Exact list, or wildcard at the end | Exact list only |
| Consent screen | Only with "Consent required" on | Always on first authorisation |
| Device flow | Supported, per-client switch | Recent releases only |
| Central revocation | Admin console: user's offline sessions, or the client | Admin: block user; user: revoke application |

### GitLab as the STS issuer (optional, later)

Deployments that log in through GitLab instead of Keycloak could
trust GitLab in SeaweedFS's IAM file. The admin would then send the
GitLab **ID token** (the access token is opaque) and the policy would
use `${jwt:nickname}`. This needs only settings
(`OIDC_STS_TOKEN = "id_token"`, `OIDC_USERNAME_CLAIM = "nickname"`)
and is scheduled with the device flow in roadmap G8, because those
deployments have no Keycloak session for the page.

## Owner checks at connect time

| Provider | Check | Reason |
| :--- | :--- | :--- |
| Keycloak | `preferred_username == MAIN_USER`; else refuse, store nothing, and report both names | Stops someone completing a login with their own account so the owner's files go to the attacker's prefix |
| GitLab | Username claim equals `MAIN_USER` when `GITLAB_OWNER_CHECK = "username"` (default). With `"confirm"`, the page or CLI shows the GitLab account and stores only after the user confirms | GitLab and DTaaS usernames may differ in some deployments |

After a GitLab connect, the git backend checks read access to every
git asset using the connection (`git ls-remote`) and reports
`repo_unreachable` per asset. The connection is kept: access can be
granted later. Push rights cannot be checked without an API scope, so
the first sync confirms them.
