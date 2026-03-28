# Keycloak Configuration Script

This script configures the DTaaS Keycloak realm with the required client scope and
protocol mappers for the `dtaas-workspace` client.

| Script | Requires | Platform |
|--------|----------|----------|
| `configure_keycloak_rest.sh` | `curl`, `jq` | Linux / macOS / WSL |

## What They Configure

All scripts perform the same operations against a running Keycloak instance:

1. Create (or reuse) a shared client scope named `dtaas-shared`.
2. Ensure the following protocol mappers exist in that scope:
   - `profile` — maps the `profile` user attribute to the userinfo token.
   - `groups` — maps group memberships to the `groups` claim in the access token.
   - `groups_owner` — maps group memberships to the
     `https://gitlab.org/claims/groups/owner` claim in the access token.
   - `sub_legacy` — maps the `sub_legacy` user attribute to the userinfo token.
3. Ensure the `profile` and `sub_legacy` user profile attributes exist in the realm.
4. Assign the `dtaas-shared` scope to the `dtaas-workspace` client's default scopes.
5. Optionally update every user's `profile` attribute to `<PROFILE_BASE_URL>/<username>`.

---

## configure_keycloak_rest.sh

Uses the Keycloak **Admin REST API** directly via `curl` and `jq`. No `kcadm`
installation required. Well-suited for CI environments and containers.

### Prerequisites

- `curl`
- `jq`

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `KEYCLOAK_BASE_URL` | `http://localhost` | Keycloak base URL |
| `KEYCLOAK_CONTEXT_PATH` | `/auth` | Context path (use `/` for Keycloak 17+) |
| `KEYCLOAK_REALM` | `dtaas` | Target realm |
| `KEYCLOAK_CLIENT_ID` | `dtaas-workspace` | Client to configure |
| `KEYCLOAK_SHARED_SCOPE_NAME` | `dtaas-shared` | Shared scope name |
| `KEYCLOAK_ADMIN` | `admin` | Admin username |
| `KEYCLOAK_ADMIN_PASSWORD` | `admin` | Admin password |
| `PROFILE_BASE_URL` | `https://localhost/gitlab` | Base URL for user profile attributes |

### Usage

```sh
KEYCLOAK_BASE_URL=https://keycloak.example.com \
KEYCLOAK_ADMIN=admin \
KEYCLOAK_ADMIN_PASSWORD=admin \
./configure_keycloak_rest.sh
```

---

## Choosing the Script

Use `configure_keycloak_rest.sh`. It is the single supported Keycloak configuration
script for this repository.
