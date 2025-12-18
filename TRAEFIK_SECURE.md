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
- **user1** workspace using the workspace-nouveau image
- **user2** workspace using the mltooling/ml-workspace-minimal image
- Two Docker networks: `dtaas-frontend` and `dtaas-users`

All services (except the OAuth callback) are protected by OAuth2 authentication.
Users must authenticate with GitLab before accessing any workspace or the DTaaS web interface.

## 🔐 OAuth2 Setup with GitLab

### Step 1: Create GitLab OAuth Application

1. Log in to your GitLab instance (gitlab.com or your self-hosted instance)
2. Navigate to:
   - **For personal use**: Settings → Applications
   - **For organization**: Admin Area → Applications
3. Create a new application with these settings:
   - **Name**: DTaaS Workspace
   - **Redirect URI**: `http://localhost/_oauth`
   - **Scopes**: Select `read_user`
   - **Confidential**: Yes (checked)
4. Click "Save application"
5. Copy the **Application ID** and **Secret** - you'll need these in the next step

### Step 2: Configure Environment Variables

1. Copy the example environment file:

   ```bash
   cp dtaas/.env.example dtaas/.env
   ```

2. Edit `dtaas/.env` and fill in your OAuth credentials:

   ```bash
   # Your GitLab instance URL (without trailing slash)
   # Example: https://gitlab.com or https://gitlab.example.com
   OAUTH_URL=https://gitlab.com

   # OAuth Application Client ID
   # Obtained when creating the OAuth application in GitLab
   OAUTH_CLIENT_ID=your_application_id_here

   # OAuth Application Client Secret
   # Obtained when creating the OAuth application in GitLab
   OAUTH_CLIENT_SECRET=your_secret_here

   # Secret key for encrypting OAuth session data
   # Generate a random string (at least 16 characters)
   # Example: openssl rand -base64 32
   OAUTH_SECRET=your_random_secret_key_here
   ```

3. Generate a secure random secret:

   ```bash
   openssl rand -base64 32
   ```

   Use the output as your `OAUTH_SECRET` value.

4. (OPTIONAL) Update the USERNAME variables in .env, replacing the defaults with your desired usernames.

   ```bash
   # Username Configuration
   # These usernames will be used as path prefixes for user workspaces
   # Example: http://localhost/user1, http://localhost/user2
   USERNAME1=user1
   USERNAME2=user2
   ```

## 💪 Build Workspace Image

Before starting the services, build the workspace-nouveau image:

```bash
docker compose -f compose.traefik.secure.yml build user1
```

Or use the standard build command:

```bash
docker build -t workspace-nouveau:latest -f Dockerfile .
```

## 📁 Prepare Configuration Files

Before starting the services, prepare the DTaaS configuration files from their examples:

1. Copy the traefik-forward-auth configuration file:

   ```bash
   cp dtaas/conf.example dtaas/conf
   ```

2. Copy the DTaaS client configuration file:

   ```bash
   cp dtaas/client.js.example dtaas/client.js
   ```

3. Edit `dtaas/client.js` to configure the DTaaS client
   with your OAuth credentials and URL settings.

4. Update the usernames in `dtaas/conf` to customize the traefik-forward-auth
   rules for your deployment.

## :rocket: Start Services

To start all services (Traefik, auth, client, and workspaces):

```bash
docker compose -f compose.traefik.secure.yml --env-file dtaas/.env up -d
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

### User1 Workspace (workspace-nouveau)

All endpoints require authentication:

- **VNC Desktop**: `http://localhost/user1/tools/vnc?path=user1%2Ftools%2Fvnc%2Fwebsockify`
- **VS Code**: `http://localhost/user1/tools/vscode`
- **Jupyter Notebook**: `http://localhost/user1`
- **Jupyter Lab**: `http://localhost/user1/lab`

👉 Remember to replace `user1` with correct username.

### User2 Workspace (ml-workspace-minimal)

All endpoints require authentication:

- **VNC Desktop**: `http://localhost/user2/tools/vnc/?password=vncpassword`
- **VS Code**: `http://localhost/user2/tools/vscode/`
- **Jupyter Notebook**: `http://localhost/user2`
- **Jupyter Lab**: `http://localhost/user2/lab`

👉 Remember to replace `user2` with correct username.

## 🛑 Stopping Services

To stop all services:

```bash
docker compose -f compose.traefik.secure.yml --env-file dtaas/.env down
```

## ⚙️ Network Configuration

The setup uses two Docker networks:

- **dtaas-frontend**: Used by Traefik, traefik-forward-auth, and the client
  for external communication
- **dtaas-users**: Shared network for workspace instances and Traefik

This separation allows for better network isolation and security.

## 🔧 Customization

### Adding More Users

To add additional workspace instances, add a new service in `compose.traefik.secure.yml`:

```yaml
user3:
  image: workspace-nouveau:latest
  restart: unless-stopped
  environment:
    - MAIN_USER=${USERNAME3}
  shm_size: 512m
  labels:
    - "traefik.enable=true"
    - "traefik.http.routers.u3.entryPoints=web"
    - "traefik.http.routers.u3.rule=PathPrefix(`/user3`)"
    - "traefik.http.routers.u3.middlewares=traefik-forward-auth"
  networks:
    - users
```

And, add the desired `USERNAME3` variable in `.env`:

```bash
# Username Configuration
# These usernames will be used as path prefixes for user workspaces
# Example: http://localhost/user1, http://localhost/user2
USERNAME1=user1
USERNAME2=user2
USERNAME3=user3
```

### Using a Different OAuth Provider

traefik-forward-auth supports multiple OAuth providers. To use a different
provider:

1. Update the `DEFAULT_PROVIDER` in the traefik-forward-auth service
2. Adjust the OAuth URLs accordingly
3. Update the scope as needed for your provider

See [traefik-forward-auth documentation][tfa-docs] for details.

[tfa-docs]: https://github.com/thomseddon/traefik-forward-auth

## :shield: Security Considerations

### Current Setup (Development/Testing)

⚠️ **Important**: This configuration uses some insecure settings for development:

- `INSECURE_COOKIE=true` - Allows cookies over HTTP
- Traefik API is exposed (`--api.insecure=true`)
- No TLS/HTTPS encryption
- Debug logging enabled

### Production Recommendations

For production deployments:

1. **Enable HTTPS/TLS**:
   - Configure SSL certificates (Let's Encrypt recommended)
   - Remove `INSECURE_COOKIE=true` from traefik-forward-auth
   - Update OAuth redirect URLs to use HTTPS

2. **Secure Traefik API**:
   - Remove `--api.insecure=true`
   - Enable Traefik dashboard authentication
   - Restrict API access

3. **Environment Variables**:
   - Use Docker secrets for sensitive data
   - Never commit `.env` file to version control
   - Rotate OAuth secrets regularly

4. **Logging**:
   - Change log level from DEBUG to INFO or WARN
   - Implement log aggregation and monitoring

5. **Network Security**:
   - Review and restrict network access
   - Use firewall rules
   - Consider using internal networks for service communication

6. **OAuth Configuration**:
   - Use organization-wide OAuth applications
   - Restrict OAuth scopes to minimum required
   - Implement refresh token rotation

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
