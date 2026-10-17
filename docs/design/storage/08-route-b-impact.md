# 8. Effect of Route B on the storage design

Part of the [storage design](README.md). Route B
([auth design](../auth/login-relay-gitlab.md)) puts `login-relay` and
Oathkeeper in every deployment, with **GitLab** as the identity
provider in three of them and **Keycloak** in one. Documents 1 to 7
assume Keycloak everywhere. This document lists what Route B changes,
what it leaves alone, and proposes the design to adopt. Documents 1 to
7 are updated once the proposal is accepted.

## What stays the same

Assets and their names; `config.toml`; the writer and live reload;
the S3 backend and `rclone`; git backup; the `/config` page and CLI;
the control socket; status reporting; storage-side hardening; most of
the threat model.

## Facts that drive the changes

| Fact about GitLab | Source | Consequence |
| :--- | :--- | :--- |
| Access tokens are opaque | GitLab OAuth docs | Neither Oathkeeper nor STS can verify them alone |
| No RFC 7662 introspection endpoint found | GitLab docs; no `introspection_endpoint` in discovery | `login-relay` adapts `/oauth/token/info` and `/oauth/userinfo` |
| Refresh responses carry no ID token | GitLab OAuth API docs; issue #44485 | A background job cannot obtain a fresh ID token |
| ID tokens hold few claims (`sub`; username via `userinfo`) and live 2 minutes | GitLab OIDC provider docs; issues #388176, #377654 | No `${jwt:nickname}` policy variable to rely on |
| Refresh tokens have no fixed expiry | GitLab OAuth docs | The 180-day grant maximum cannot be enforced in GitLab |

These are documented behaviours; the spike (T003) confirms them on the
deployed release.

## Effects and proposals

### E1. Two identity profiles

The deployment's identity provider is Keycloak or GitLab. Storage stops
saying "Keycloak for S3": **S3 uses the deployment's identity
provider**, and git always uses GitLab. A deployment-wide
`IDENTITY_PROVIDER = keycloak | gitlab` selects the profile.

### E2. Session verification through login-relay

The admin verifies browser sessions, for `/config` and for the nginx
front door, by calling `login-relay`'s internal `/token/introspect`
instead of Keycloak `userinfo`. `login-relay` already answers
inactive for tokens of other clients or unlisted users; the admin
requires `active` and `username == MAIN_USER`. One
code path serves both profiles, and the front door and page work in
all four deployments. Residual risk 5 in
[document 4](04-threat-model.md#residual-risks) and task T805 disappear
once track A lands. The 30-second cache stays.

### E3. S3 credentials: login-relay as token bridge

STS needs a verifiable JWT carrying the username. GitLab cannot supply
one in the background (opaque access tokens, no ID token on refresh).
Options:

| Option | Central revocation | Per-user secrets | Verdict |
| :--- | :--- | :--- | :--- |
| **Token bridge**: `login-relay` exchanges a provider access token for its own short JWT | Yes | None | **Proposed** |
| Per-user static S3 keys from provisioning | No | One per user | Fallback only |
| Keycloak just for storage | Yes | None | Contradicts Route B |

The bridge, an internal endpoint of `login-relay`:

```text
POST /token/exchange   (internal only, never routed by Traefik)
  subject_token=<provider access token>
  1. validate the token live: Keycloak introspection, or GitLab
     /oauth/token/info + /oauth/userinfo
  2. require client = workspace-backup, username in WORKSPACE_USERS
  3. return a JWT: iss=<login-relay issuer>, aud=workspace-backup,
     preferred_username=<username>, exp = now + 5 minutes,
     signed with login-relay's key (JWKS at /.well-known/jwks.json)
```

SeaweedFS's IAM file then trusts **one** issuer, `login-relay`, in
both profiles. The policy keeps `${jwt:preferred_username}`. Each round
becomes: refresh the provider grant, exchange it at `login-relay`, and
exchange the JWT at STS. The [credentials sequence](03-connect-backends.md#credentials-per-round)
gains one hop.

Using the bridge in the Keycloak profile too is a choice. It costs one
extra hop but keeps a single STS trust setup and a single code path,
so I propose it.

Consequences:

- `login-relay` holds a signing key, a high-value secret. It is
  generated at deployment, stored as a Docker secret, rotated with
  overlapping keys in the JWKS, and never given to workspaces.
- Removing a user from `WORKSPACE_USERS` stops their S3 backups at the
  next round, even with `gitlab.com` as the provider. That gives
  operators a central switch that GitLab alone lacks.
- `OIDC_STS_TOKEN` and the G8 item "GitLab as STS issuer" are dropped.
- For cloud S3, AWS must reach `login-relay`'s JWKS publicly over HTTPS
  (G8 cloud guide).

### E4. Connections in the GitLab profile

The user's GitLab grant serves both S3 (through the bridge) and git,
so the GitLab profile has **one connection, `gitlab`**, with scopes
`openid write_repository`. One click connects everything.

| Profile | Connections | Clicks for S3 and git |
| :--- | :--- | :--- |
| `keycloak` | `keycloak` (S3), `gitlab` (git) | 2 |
| `gitlab` | `gitlab` (S3 and git) | 1 |

The trade-off: a user who only backs up to S3 still grants
`write_repository`. Requesting it only when a git asset exists would
need a second, narrower grant. I propose the single grant.

### E5. Grant lifetime

GitLab refresh tokens never expire on their own, so the 180-day
maximum moves into the admin. `CONNECTION_MAX_AGE_DAYS` (default 180)
makes a connection older than that report `login_expired` and prompt a
reconnect. In the Keycloak profile, the realm's "Offline Session Max"
is set to the same value.

### E6. Revocation

| Profile | Per-user switches |
| :--- | :--- |
| `keycloak` | Disable the user; revoke offline sessions; remove from `WORKSPACE_USERS` |
| `gitlab` | Remove from `WORKSPACE_USERS` (bridge refuses); block in GitLab; the user revokes the application |

### E7. One redirect URI for all users

With GitLab applications on `gitlab.com` or a university GitLab, the
operator may not be able to provision redirect URIs through an API.
Adding a URI for every new user becomes a manual step.

**Proposal:** a callback bounce in `login-relay`. Both providers get
one URI, `https://<server>/login-relay/oauth/<provider>/callback`.
The admin puts the user into `state` (`<user>.<random>`). `login-relay`
checks the user against `WORKSPACE_USERS` and redirects the browser to
`/<user>/config/callback/<provider>?code&state`. `login-relay` never
redeems the code. The admin redeems it with the bounce URI as
`redirect_uri`, still under PKCE and the existing `state` and session
checks. This replaces decision D14 and removes the per-user step from
provisioning in both profiles.

### E8. Addresses

| Provider | Browser | Containers |
| :--- | :--- | :--- |
| Keycloak | Public URL | `http://keycloak:8080/auth` via `KC_HOSTNAME_BACKCHANNEL_DYNAMIC` |
| External GitLab | Public URL | Public URL; needs outbound internet |
| Integrated GitLab | Public URL | `GITLAB_INTERNAL_URL=http://gitlab/gitlab` |

The admin's git remotes for the integrated GitLab use the internal URL
for the same reason.

### E9. Settings

| Change | Setting |
| :--- | :--- |
| New | `IDENTITY_PROVIDER`, `LOGIN_RELAY_INTERNAL_URL`, `CONNECTION_MAX_AGE_DAYS`, `GITLAB_INTERNAL_URL` |
| Changed | `OIDC_ISSUER` and `OIDC_INTERNAL_URL` apply to the Keycloak profile only; STS trusts `login-relay` |
| Removed | `OIDC_STS_TOKEN`, `OIDC_USERNAME_CLAIM`, `DTAAS_LOGIN_CLIENT_ID` (the check moves into `login-relay`) |

### E10. Threat model

- **New asset:** `login-relay`'s signing key. Whoever holds it can mint
  S3 access for any listed user. Same trust level as `login-relay`'s
  existing role as the login gateway.
- **New boundary:** `/token/exchange` and `/token/introspect` must stay
  unreachable from Traefik. A compose test checks this.
- **Front door:** universal after track A (E2).
- **Bridge input:** an attacker inside the network can call
  `/token/exchange` with their own token and gets only their own
  prefix, as today with STS.

## Roadmap

A new track A, in parallel with storage groups G1 to G2:

| Group | Repository | Delivers | Needs |
| :--- | :--- | :--- | :--- |
| A1 | workspace | `login-relay` profiles, GitLab introspection adapter, TLS-aware cookies, Oathkeeper cache | none |
| A2 | workspace | `login-relay` token bridge and JWKS; callback bounce | A1 |
| A3 | DTaaS | Oathkeeper and `login-relay` in the four deployments; Keycloak backchannel setting | A1 |

Changed dependencies: G3 needs A2 (session check and bridge), and G7
needs A3. G8 loses "GitLab as STS issuer" and "forward-auth session
verifier"; the device flow stays optional.

## Changes to documents 1 to 7 once accepted

| Document | Change |
| :--- | :--- |
| 1 | S3 via the deployment's identity provider and the bridge |
| 2 | Profiles; bridge token; GitLab facts above; one bounce URI; GitLab-as-issuer section removed |
| 3 | Connections per profile (E4); credentials sequence with the bridge; settings (E9); `CONNECTION_MAX_AGE_DAYS` |
| 4 | Signing key asset; internal-only endpoints; residual risk 5 removed; trust policy names `login-relay` as issuer |
| 5 | `session.verify` via `login-relay`; `credentials.py` adds the exchange; `providers.py` gains GitLab-profile login |
| 6 | Page shows one connection in the GitLab profile |
| 7 | Context diagram with `login-relay` as issuer; decisions D10 and D14 replaced; deployments table for track A |
| Spec, plan, tasks, roadmap | Track A; FR-11 to FR-14, SR-5, SR-9; T805 dropped; G3 and G7 dependencies |

## Open questions

1. Use the bridge in the Keycloak profile too (proposed), or let
   Keycloak tokens go straight to STS?
2. One GitLab grant for S3 and git (proposed), or two narrower ones?
3. The callback bounce (E7), or per-user redirect URIs?
4. Version retention, "maximum": keep versions forever, or a long
   configurable period?
