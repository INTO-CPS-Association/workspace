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

Please see [CONFIGURATION.md](./CONFIGURATION.md) for information on
configuring the application setup specified in the compose file.

## 💪 Build Workspace Image

Before starting the services, build the workspace image:

```bash
docker compose -f compose.traefik.secure.yml build user1
```

Or use the standard build command:

```bash
docker build -t workspace:latest -f Dockerfile.ubuntu.noble.gnome .
```

## :rocket: Start Services

To start all services (Traefik, auth, client, and workspaces):

```bash
docker compose -f compose.traefik.secure.yml --env-file config/.env up -d
```

This will:

1. Start the Traefik reverse proxy on port 80
2. Start traefik-forward-auth for OAuth2 authentication
3. Start the DTaaS web client interface
4. Start workspace instances for both users

## :technologist: Accessing Services

Once all services are running, access them through Traefik at `http://localhost`.

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

👉 Remember to replace `user1` with the your username for user 1.

### User2 Workspace (ml-workspace-minimal)

All endpoints require authentication:

- **VNC Desktop**: `http://localhost/user2/tools/vnc/?password=vncpassword`
- **VS Code**: `http://localhost/user2/tools/vscode/`
- **Jupyter Notebook**: `http://localhost/user2`
- **Jupyter Lab**: `http://localhost/user2/lab`

👉 Remember to replace `user2` wwith the your username for user 2.

## 🛑 Stopping Services

To stop all services:

```bash
docker compose -f compose.traefik.secure.yml --env-file config/.env down
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
cp -r ./files/user1 ./files/user3
```

### Using a Different OAuth Provider

traefik-forward-auth supports multiple OAuth providers. To use a different
provider:

1. Update the `DEFAULT_PROVIDER` in the traefik-forward-auth service
2. Adjust the OAuth URLs accordingly
3. Update the scope as needed for your provider

See the [traefik-forward-auth documentation][tfa-docs] for details.

[tfa-docs]: https://github.com/thomseddon/traefik-forward-auth

## :shield: Security Considerations

### Current Setup (Development/Testing)

⚠️ **Important**: This configuration is designed for development and testing and uses some insecure settings:

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
   docker compose -f compose.traefik.secure.yml ps
   ```

2. Check Traefik logs:

   ```bash
   docker compose -f compose.traefik.secure.yml logs traefik
   ```

3. Check traefik-forward-auth logs:

   ```bash
   docker compose -f compose.traefik.secure.yml logs traefik-forward-auth
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
