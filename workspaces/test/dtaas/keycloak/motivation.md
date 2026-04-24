# Keycloak Custom Claims — Motivation and System Structure

## Why This Exists

DTaaS uses Keycloak as its identity provider (IdP). The original deployment authenticated against
GitLab's OIDC endpoint. When moving to a self-hosted Keycloak instance, the claims present in
Keycloak's default token output do not fully match what the DTaaS frontend and access-enforcement
layer need.

This directory contains a configurator that automates the Keycloak setup required to close that gap.
It is idempotent: running it multiple times against the same realm has no effect if the configuration
is already in place.

---

## System Architecture

```
Browser
  │
  ▼
Traefik (TLS termination, reverse proxy)
  │
  ├─► traefik-forward-auth  ──► Keycloak (OIDC/PKCE login)
  │        │
  │        └─ validates session on every request
  │
  ├─► DTaaS web client (React SPA)
  │
  └─► Workspace services (per-user containers)
            │
            └─ receives X-Forwarded-User header from Traefik middleware
```

After a successful PKCE login, the DTaaS frontend stores the authenticated user object (from the
OIDC library) under `oidc.user::` in browser session storage. The frontend reads claims from that
object — particularly `profile` and `preferred_username` — to identify users and construct workspace
URLs.

`traefik-forward-auth` validates sessions on every request by checking the token against Keycloak
and forwarding the authenticated user identity downstream as an HTTP header.

---

## What Claims Are Needed and Why

The DTaaS frontend was built against GitLab's OIDC token format. The reference payload from a GitLab
login looks like:

```json
{
  "sub": "2",
  "name": "alice",
  "preferred_username": "alice",
  "profile": "https://gitlab.example.com/alice",
  "groups": ["dtaas"],
  "groups_direct": ["dtaas"],
  "sub_legacy": "xxx",
  "https://gitlab.org/claims/groups/owner": ["dtaas"]
}
```

For Keycloak to work as a drop-in replacement, the token must contain a structurally compatible set
of claims.

### Standard claims — work by default

| Claim | Keycloak source | Notes |
|---|---|---|
| `sub` | Always present | UUID format rather than GitLab's numeric ID — expected |
| `name` | `profile` scope | Confirm `profile` is a default scope on the client |
| `preferred_username` | `profile` scope | Same scope as above |

### Custom claims — require explicit configuration

| Claim | Keycloak source | Configuration required |
|---|---|---|
| `profile` | User attribute | Store `profile` attribute per user; add `oidc-usermodel-attribute-mapper` |
| `groups` | Group membership | Add `oidc-group-membership-mapper`; assign user to Keycloak group |

### Claims deliberately omitted

| Claim | Reason |
|---|---|
| `sub_legacy` | GitLab-specific backwards-compatibility ID. No Keycloak equivalent. Not read by the DTaaS client. |
| `groups_direct` | GitLab-specific. Distinguishes direct vs. inherited group membership, a concept absent in Keycloak. |
| `https://gitlab.org/claims/groups/owner` | GitLab-specific owner claim. Not read by the DTaaS client. Also broken in practice: Keycloak interprets dots in claim names as JSON path separators, producing a malformed nested object. |

---

## How the `profile` Claim Works

The `profile` claim (a URL in the form `https://shared.dtaas-digitaltwin.com/sandra`) requires two
steps because Keycloak does not know this value automatically.

**Step 1 — store the value on the user.** Each Keycloak user has a set of arbitrary key-value
attributes. The configurator writes a `profile` attribute for each configured user, set to
`{KEYCLOAK_PROFILE_BASE_URL}/{username}`.

**Step 2 — emit it in the token.** A protocol mapper of type `oidc-usermodel-attribute-mapper` reads
the `profile` attribute and writes it into the `userinfo` response. Without this mapper, the stored
attribute never appears in any token or userinfo response.

The full chain:

```
User attribute "profile" = "https://shared.dtaas-digitaltwin.com/sandra"
        │  (mapper reads attribute)
        ▼
userinfo → "profile": "https://shared.dtaas-digitaltwin.com/sandra"
```

The `groups` claim works differently — Keycloak tracks group membership internally, so the mapper
reads it directly without any user attribute.

---

## Verified Keycloak Userinfo Payload

The current live output from `https://shared.dtaas-digitaltwin.com`:

```json
{
  "sub": "b70fb488-9555-4fbb-9071-6aceb6502521",
  "email_verified": false,
  "profile": "https://shared.dtaas-digitaltwin.com/sandra",
  "name": "Sandra Sørensen",
  "groups": ["dtaas"],
  "preferred_username": "sandra",
  "given_name": "Sandra",
  "family_name": "Sørensen",
  "email": "sandra99.fs@gmail.com"
}
```

---

## Companion Code Structure

```
keycloak/
├── motivation.md                  ← this file
├── src/
│   └── keycloak_rest/
│       ├── __main__.py            entry point (python -m keycloak_rest)
│       ├── cli.py                 argument parsing and top-level orchestration
│       ├── configurator.py        main workflow: realm, clients, mappers, user profiles
│       ├── constants.py           mapper definitions and client config templates
│       ├── settings.py            environment variable parsing and dataclasses
│       ├── http_client.py         minimal HTTP client (urllib + SSL context)
│       ├── user_profiles.py       user attribute read/write helpers
│       ├── dotenv.py              .env file loader
│       └── request_proxy.py       (internal HTTP request abstraction)
└── test/
    ├── TESTING.md                 test setup instructions
    ├── integration_helpers.py     Keycloak API helpers for test setup
    ├── integration_setup.py       service-account and readiness setup
    ├── container_helpers.py       Docker container lifecycle helpers
    ├── test_configure_keycloak_rest.py   unit tests
    └── test_integration_keycloak_rest.py integration tests (require real Keycloak)
```

### Configuration workflow (`configurator.py`)

`KeycloakRestConfigurator.run()` executes the following steps in order:

1. Obtain an admin access token (password grant or service-account credentials)
2. **Ensure realm** — create the `dtaas` realm if it does not already exist
3. **Ensure clients** — create `dtaas-workspace` and `dtaas-client` if absent (skipped when `KEYCLOAK_CLIENT_ROOT_URL` is not set)
4. **Configure mappers** — either as direct client mappers or through a shared client scope (controlled by `KEYCLOAK_USE_SHARED_SCOPE`)
5. **Ensure user profile metadata** — register the `profile` attribute in the realm's user-profile schema
6. **Update user profile attributes** — write `{base_url}/{username}` as the `profile` attribute for each configured user

Token expiry is checked between steps; the admin token is refreshed automatically if it is within 30 seconds of expiring.

---

## Mapper Placement: Direct vs. Shared Scope

A **client** is an application registered in Keycloak. Mappers can be placed directly on a client,
but those mappers then apply only to that one client.

A **client scope** is a named, reusable bundle of mappers. Defined once in the realm, it can be
attached to multiple clients as a default scope, making its mappers fire automatically on every token
request from those clients.

| Situation | Recommended mode |
|---|---|
| Only one client needs the custom claims | Direct client mapper (default) |
| Multiple clients need the same claims | Shared client scope |

The configurator switches between modes via `KEYCLOAK_USE_SHARED_SCOPE` in the `.env` file.

---

## How To Run

```bash
cd workspaces/test/dtaas
python -m workspaces.test.dtaas.keycloak.src.keycloak_rest --env-file config/.env
```

Or from the `keycloak` directory:

```bash
python -m keycloak_rest --env-file ../config/.env
```

See [`config/.env.example`](../config/.env.example) for required environment variables.

### Required variables

| Variable | Purpose |
|---|---|
| `KEYCLOAK_BASE_URL` | Base URL of the Keycloak server (e.g. `https://shared.dtaas-digitaltwin.com`) |
| `KEYCLOAK_CONTEXT_PATH` | URL context path (default: `/auth`) |
| `KEYCLOAK_REALM` | Target realm name (default: `dtaas`) |
| `KEYCLOAK_ADMIN` + `KEYCLOAK_ADMIN_PASSWORD` | Admin credentials (password-grant path) |
| `KEYCLOAK_ADMIN_CLIENT_ID` + `KEYCLOAK_ADMIN_CLIENT_SECRET` | Service-account credentials (alternative to password grant) |
| `KEYCLOAK_MAPPER_CLIENT_ID` | Client to attach mappers to (default: `dtaas-client`) |
| `KEYCLOAK_PROFILE_BASE_URL` | Base URL used when constructing user profile attribute values |
| `KEYCLOAK_USER_PROFILES` | JSON array of usernames to set profile attributes on (e.g. `["sandra", "user2"]`) |
| `KEYCLOAK_CLIENT_ROOT_URL` | Root URL for client creation; leave empty to skip client creation |
| `KEYCLOAK_USE_SHARED_SCOPE` | `true` to use shared client scope; `false` for direct client mappers (default: `false`) |

---

## Verification Checklist

After running the configurator, verify the following in the Keycloak admin UI or via the userinfo
endpoint:

- [ ] Realm `dtaas` exists and is enabled
- [ ] Clients `dtaas-workspace` and `dtaas-client` exist (if `KEYCLOAK_CLIENT_ROOT_URL` was set)
- [ ] `profile` and `groups` mappers are present on the target client or assigned shared scope
- [ ] Each configured user has a `profile` attribute in the form `{base_url}/{username}`
- [ ] Calling the userinfo endpoint with a valid token returns `profile` and `groups` claims
- [ ] `groups` contains the expected group names (flat array, not full paths)
