# Workspace with Traefik Forward Auth (OAuth2 Security)

This guide explains how to use the workspace container with Traefik reverse proxy
and OAuth2 authentication via traefik-forward-auth for secure multi-user deployments
in the DTaaS installation.

## ❓ Prerequisites

✅ Docker Engine v27 or later  
✅ Sufficient system resources (at least 1GB RAM per workspace instance)  
✅ Port 80 available on your host machine  
✅ GitLab OAuth Application configured (see setup below)

## 🗒️ Overview

The `compose.traefik.secure.yml` file sets up:

- **Traefik** reverse proxy on port 80
- **traefik-forward-auth** for OAuth2 authentication with GitLab
- **client** - DTaaS web interface
- **user1** workspace using the workspace image
- **user2** workspace using the mltooling/ml-workspace-minimal image
- Two Docker networks: `dtaas-frontend` and `dtaas-users`

## ⚙️ Initial Configuration

Please follow the steps in [`CONFIGURATION.md`](CONFIGURATION.md)
for the `compose.traefik.secure.yml` composition before building
the workspace and running the setup.

### Create Workspace Files

All the deployment options require user directories for
storing workspace files. These need to
be created for `USERNAME1` and `USERNAME2` set in
`workspaces/test/dtaas/config/.env` file.

```bash
# create required files
cp -R workspaces/test/dtaas/files/user1 workspaces/test/dtaas/files/<USERNAME1>
cp -R workspaces/test/dtaas/files/user1 workspaces/test/dtaas/files/<USERNAME2>
# set file permissions for use inside the container
sudo chown -R 1000:100 workspaces/test/dtaas/files
```

## :rocket: Start Services

To start all services (Traefik, auth, client, and workspaces)::

```bash
docker compose -f workspaces/test/dtaas/compose.traefik.secure.yml --env-file workspaces/test/dtaas/config/.env up -d
```

This will:

1. Start the Traefik reverse proxy on port 80
2. Start traefik-forward-auth for OAuth2 authentication
3. Start the DTaaS web client interface
4. Start workspace instances for both users

## :technologist: Accessing Workspaces

Once all services are running, access the workspaces through Traefik at `http://localhost`.

### Initial Access

1. Navigate to `http://localhost` in your web browser
2. You will be redirected to GitLab for authentication
3. Log in with your GitLab credentials
4. Authorize the DTaaS Workspace application
5. You will be redirected back to the DTaaS web interface

### DTaaS Web Client

- **URL**: `http://localhost/`
- Access to the main DTaaS web interface (requires authentication)

### User1 Workspace (workspace)

All endpoints require authentication:

- **VNC Desktop**: `http://localhost/user1/tools/vnc?path=user1%2Ftools%2Fvnc%2Fwebsockify`
- **VS Code**: `http://localhost/user1/tools/vscode`
- **Jupyter Notebook**: `http://localhost/user1`
- **Jupyter Lab**: `http://localhost/user1/lab`

#### Service Discovery

The workspace provides a `/services` endpoint that returns a JSON list of
available services. This enables dynamic service discovery for frontend
applications.

**Example**: Get service list for user1

```bash
curl http://localhost/user1/services
```

**Response**:

```json
{
  "desktop": {
    "name": "Desktop",
    "description": "Virtual Desktop Environment",
    "endpoint": "tools/vnc?path=user1%2Ftools%2Fvnc%2Fwebsockify"
  },
  "vscode": {
    "name": "VS Code",
    "description": "VS Code IDE",
    "endpoint": "tools/vscode"
  },
  "notebook": {
    "name": "Jupyter Notebook",
    "description": "Jupyter Notebook",
    "endpoint": ""
  },
  "lab": {
    "name": "Jupyter Lab",
    "description": "Jupyter Lab IDE",
    "endpoint": "lab"
  }
}
```

The endpoint values are dynamically populated with the user's username from the
`MAIN_USER` environment variable. This variable corresponds to `USERNAME1` of
`.env` file.

### User2 Workspace (ml-workspace-minimal)

All endpoints require authentication:

- **VNC Desktop**: `http://localhost/user2/tools/vnc/?password=vncpassword`
- **VS Code**: `http://localhost/user2/tools/vscode/`
- **Jupyter Notebook**: `http://localhost/user2`
- **Jupyter Lab**: `http://localhost/user2/lab`

### Custom URL

Remember to change the following variables in URLs to the variable values
specified in `.env`:

- Change `user1` to `USERNAME1` value
- Change `user2` to `USERNAME2` value
- Change `localhost` in URL to the `SERVER_DNS` value

## 🛑 Stopping Services

To stop all services:

```bash
docker compose -f workspaces/test/dtaas/compose.traefik.secure.yml --env-file workspaces/test/dtaas/config/.env down
```

## 🔧 Customization

### Adding More Users

To add additional workspace instances, add a new service in `compose.traefik.secure.yml`:

```yaml
  user3:
    image: workspace:latest
    restart: unless-stopped
    build:
      context: .
      dockerfile: ../Dockerfile.ubuntu.noble.gnome
    environment:
      - MAIN_USER=${USERNAME3:-user3}
    volumes:
      - ./files/user3:/workspace
      - ./files/common:/workspace/common
    shm_size: 512m
    labels:
      - "traefik.enable=true"
      - "traefik.http.routers.u3.entryPoints=web"
      - "traefik.http.routers.u3.rule=Host(`${SERVER_DNS:-localhost}`) && PathPrefix(`/${USERNAME3:-user3}`)"
      - "traefik.http.routers.u3.middlewares=traefik-forward-auth"
    networks:
      - users
```

Add the desired `USERNAME3` variable in `.env`:

```bash
# Username Configuration
# These usernames will be used as path prefixes for user workspaces
# Example: http://localhost/user1, http://localhost/user2
USERNAME1=user1
USERNAME2=user2
USERNAME3=user3 # <--- replace "user3" with your desired username
```

And, setup the base structure of the persistent directories for the new user:

```bash
cp -r workspaces/test/dtaas/files/user1 workspaces/test/dtaas/files/user3
```

### Using a Different OAuth Provider

traefik-forward-auth supports multiple OAuth providers. To use a different
provider:

1. Update the `DEFAULT_PROVIDER` in the traefik-forward-auth service
2. Adjust the OAuth URLs accordingly
3. Update the scope as needed for your provider

See the [traefik-forward-auth documentation][tfa-docs] for details.

[tfa-docs]: https://github.com/thomseddon/traefik-forward-auth

## 🤖 Automated CI Testing (No Real OAuth Provider Needed)

Running the OAuth2 authentication flow in a CI environment (e.g. GitHub Actions)
is challenging because the standard authorization-code flow requires a human to
open a browser, enter credentials, and click "Authorize".

This project solves the problem by replacing the real GitLab provider with
**[Dex](https://dexidp.io/)** – a lightweight, CNCF-standard OIDC server –
and scripting the entire login flow with `curl`.

### How it works

```
curl   →   Traefik   →   traefik-forward-auth   →   302 to Dex
 ↓                                                        ↓
POST credentials to Dex form  (no approval screen)
 ↓
302 to /_oauth?code=XXX   →   traefik-forward-auth exchanges code
 ↓
Sets _forward_auth session cookie   →   302 to /user1/
 ↓
GET /user1/ with cookie   →   HTTP 200  ✅
```

Two Dex settings make this fully headless:

- `skipApprovalScreen: true` — no consent page is presented after login
- `enablePasswordDB: true` — static username/password pairs in config

### Using the CI compose override locally

```bash
# Start services with Dex replacing GitLab
docker compose \
  -f workspaces/test/dtaas/compose.traefik.secure.yml \
  -f workspaces/test/dtaas/compose.ci.override.yml \
  --env-file workspaces/test/dtaas/config/.env \
  up -d

# Add local hostname resolution for Dex (needed so curl can follow OAuth redirects)
echo "127.0.0.1 dex" | sudo tee -a /etc/hosts

# Run the automated login script
workspaces/test/dtaas/scripts/ci_auth_login.sh \
  http://localhost user1 http://dex:5556 password
```

### Relevant files

| File | Purpose |
|---|---|
| `config/dex.yml` | Dex OIDC configuration with static test users |
| `compose.ci.override.yml` | Compose override: adds Dex, reconfigures forward-auth |
| `scripts/ci_auth_login.sh` | Headless OAuth2 login script (curl-based) |

### Static test users

The test users are configured in `config/dex.yml`. Emails must match the
whitelist rules in `config/conf`. Default credentials:

| Username | Email | Password |
|---|---|---|
| `user1` | `user1@localhost` | `password` |
| `user2` | `user2@localhost` | `password` |

## :shield: Security Considerations

### Current Setup (Development/Testing)

⚠️ **Important**: This configuration is designed for development and testing
and uses some insecure settings:

- `INSECURE_COOKIE=true` - Allows cookies over HTTP
- Traefik API is exposed (`--api.insecure=true`)
- No TLS/HTTPS encryption
- Debug logging enabled

For setting up a composition that includes TLS/HTTPS, see [TRAEFIK_TLS.md](./TRAEFIK_TLS.md).

## 🔍 Troubleshooting

### Authentication Loop

If you're stuck in an authentication loop:

1. Clear browser cookies for localhost
2. Check that `OAUTH_SECRET` is set and consistent
3. Verify GitLab OAuth redirect URL matches your setup

### Services Not Accessible

1. Check all services are running:

   ```bash
   docker compose -f workspaces/test/dtaas/compose.traefik.secure.yml ps
   ```

2. Check Traefik logs:

   ```bash
   docker compose -f workspaces/test/dtaas/compose.traefik.secure.yml logs traefik
   ```

3. Check traefik-forward-auth logs:

   ```bash
   docker compose -f workspaces/test/dtaas/compose.traefik.secure.yml logs traefik-forward-auth
   ```

### OAuth Errors

If you see OAuth errors:

1. Verify all environment variables in `.env` are correct
2. Check GitLab OAuth application settings
3. Ensure redirect URI matches exactly (including protocol and path)

## 📚 Additional Resources

- [Traefik Documentation](https://doc.traefik.io/traefik/)
- [traefik-forward-auth GitHub](https://github.com/thomseddon/traefik-forward-auth)
- [GitLab OAuth Documentation](https://docs.gitlab.com/ee/integration/oauth_provider.html)
- [DTaaS Documentation](https://github.com/INTO-CPS-Association/DTaaS)
