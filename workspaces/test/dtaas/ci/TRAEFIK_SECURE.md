# Automated CI Testing (No Real OAuth Provider Needed)

Running the OAuth2 authentication flow in a CI environment (e.g. GitHub Actions)
is challenging because the standard authorization-code flow requires a human to
open a browser, enter credentials, and click "Authorize".

This project solves the problem by replacing the real identity provider with
**[Dex](https://dexidp.io/)** – a lightweight, CNCF-standard OIDC server –
and scripting the entire login flow with Python's `requests` library.

## How it works

```text
requests.get()  →  Traefik  →  traefik-forward-auth  →  302 to Dex
  ↓                                                         ↓
POST credentials to Dex form  (no approval screen)
  ↓
302 to /_oauth?code=XXX  →  traefik-forward-auth exchanges code
  ↓
Sets _forward_auth session cookie  →  302 to /user1/
  ↓
GET /user1/ with cookie  →  HTTP 200  ✅
```

Two Dex settings make this fully headless:

- `skipApprovalScreen: true` — no consent page is presented after login
- `enablePasswordDB: true` — static username/password pairs in config

## Using the CI compose setup locally

```bash
# Start the self-contained CI stack (Dex + Traefik + forward-auth + workspaces)
docker compose -f workspaces/test/dtaas/ci/compose.traefik.secure.yml up -d

# Add local hostname resolution for Dex (needed so requests can follow OAuth redirects)
echo "127.0.0.1 dex" | sudo tee -a /etc/hosts

# Run the automated login script (HTTP)
pip install requests
python3 workspaces/test/dtaas/ci/scripts/ci_auth_login.py \
  http://localhost user1 http://dex:5556 password

# For TLS testing (after generating mkcert certs):
python3 workspaces/test/dtaas/ci/scripts/ci_auth_login.py \
  https://localhost user1 http://dex:5556 password \
  --ca-bundle "$(mkcert -CAROOT)/rootCA.pem"
```

## Relevant files

| File | Purpose |
|---|---|
| `config/dex.yml` | Dex OIDC configuration with static test users |
| `compose.traefik.secure.yml` | Self-contained CI stack (HTTP) |
| `compose.traefik.secure.tls.yml` | Self-contained CI stack (HTTPS/TLS) |
| `scripts/ci_auth_login.py` | Headless OAuth2 login script (Python) |
| `certs/Dockerfile` | CA-aware traefik-forward-auth image for TLS |

## Static test users

The test users are configured in `config/dex.yml`. Emails must match the
whitelist rules in `config/conf`. Default credentials:

| Username | Email | Password |
|---|---|---|
| `user1` | `user1@localhost` | `password` |
| `user2` | `user2@localhost` | `password` |
