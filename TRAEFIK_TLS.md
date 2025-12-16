# Workspace with Traefik TLS/HTTPS and OAuth2

This guide explains how to deploy the workspace container with Traefik reverse proxy,
TLS/HTTPS encryption, and OAuth2 authentication for secure production deployments.

## ❓ Prerequisites

✅ Docker Engine v27 or later  
✅ Docker Compose v2.x  
✅ Sufficient system resources (at least 1GB RAM per workspace instance)  
✅ Ports 80 and 443 available on your host machine  
✅ A domain name pointing to your server (for production)  
✅ TLS/SSL certificates (see setup below)  
✅ GitLab OAuth Application configured  

## 🗒️ Overview

The `compose.traefik.secure.tls.yml` file builds upon `compose.traefik.secure.yml` and adds:

- **HTTPS/TLS encryption** on port 443 with automatic HTTP→HTTPS redirect
- **TLS certificate management** via Traefik dynamic configuration
- **Secure cookie settings** for OAuth2 authentication
- **Production-ready security** settings (no insecure flags)

All features from `compose.traefik.secure.yml` are preserved:
- OAuth2 authentication with GitLab via traefik-forward-auth
- DTaaS web interface
- Multi-user workspace support (user1 with workspace-nouveau, user2 with ml-workspace)
- Network isolation (frontend and users networks)

## 🔐 Step 1: OAuth2 Setup with GitLab

### Create GitLab OAuth Application

1. Log in to your GitLab instance (gitlab.com or self-hosted)
2. Navigate to:
   - **For personal use**: Settings → Applications
   - **For organization**: Admin Area → Applications
3. Create a new application with these settings:
   - **Name**: DTaaS Workspace
   - **Redirect URI**: `https://your-domain.com/_oauth` (⚠️ **Must use HTTPS for TLS setup**)
   - **Scopes**: Select `read_user`
   - **Confidential**: Yes (checked)
4. Click "Save application"
5. Copy the **Application ID** and **Secret**

### Configure Environment Variables

1. Copy the example environment file:

   ```bash
   cp dtaas/.env.example dtaas/.env
   ```

2. Edit `dtaas/.env` and fill in your values:

   ```bash
   # Your GitLab instance URL
   OAUTH_URL=https://gitlab.com

   # Application ID from GitLab OAuth app
   OAUTH_CLIENT_ID=your_application_id_here

   # Secret from GitLab OAuth app
   OAUTH_CLIENT_SECRET=your_secret_here

   # Generate a random secret (e.g., using: openssl rand -base64 32)
   OAUTH_SECRET=your_random_secret_key_here

   # Your domain name (must match your TLS certificate)
   SERVER_DNS=your-domain.com

   # Usernames for workspace paths
   USERNAME1=user1
   USERNAME2=user2
   ```

3. Generate a secure random secret:

   ```bash
   openssl rand -base64 32
   ```

### Configure Authorization Rules

1. Copy the example configuration file:

   ```bash
   cp dtaas/conf.example dtaas/conf
   ```

2. Edit `dtaas/conf` to configure user authorization rules (optional - see TRAEFIK_SECURE.md for details)

### Configure DTaaS Client

1. Copy the example client configuration:

   ```bash
   cp dtaas/client.js.example dtaas/client.js
   ```

2. Edit `dtaas/client.js` to match your domain and OAuth settings (update URLs to use HTTPS)

## 🔒 Step 2: TLS Certificate Setup

You need valid TLS certificates for HTTPS. Choose one of the following options:

### Option A: Self-Signed Certificates (Development/Testing ONLY)

⚠️ **Warning**: Self-signed certificates will trigger browser security warnings. Only use for development!

Generate self-signed certificates:

```bash
cd certs
./generate-self-signed-cert.sh your-domain.com
```

This creates:
- `certs/fullchain.pem` - Self-signed certificate
- `certs/privkey.pem` - Private key

**Trust the certificate in your browser** (see script output for instructions).

### Option B: Let's Encrypt (Recommended for Production)

Let's Encrypt provides free, automated SSL/TLS certificates. Use **certbot** or **acme.sh**:

#### Using Certbot

```bash
# Install certbot
sudo apt-get update
sudo apt-get install certbot

# Obtain certificate (standalone mode - requires port 80 to be free)
sudo certbot certonly --standalone -d your-domain.com

# Copy certificates to workspace directory
sudo cp /etc/letsencrypt/live/your-domain.com/fullchain.pem certs/fullchain.pem
sudo cp /etc/letsencrypt/live/your-domain.com/privkey.pem certs/privkey.pem
sudo chown $USER:$USER certs/fullchain.pem certs/privkey.pem
chmod 644 certs/fullchain.pem
chmod 600 certs/privkey.pem
```

#### Automated Renewal

Certbot automatically sets up renewal. Verify it's working:

```bash
sudo certbot renew --dry-run
```

For automatic copying to the workspace directory, create a renewal hook:

```bash
sudo tee /etc/letsencrypt/renewal-hooks/deploy/copy-to-workspace.sh > /dev/null <<'EOF'
#!/bin/bash
WORKSPACE_DIR="/path/to/workspace"
cp /etc/letsencrypt/live/your-domain.com/fullchain.pem $WORKSPACE_DIR/certs/fullchain.pem
cp /etc/letsencrypt/live/your-domain.com/privkey.pem $WORKSPACE_DIR/certs/privkey.pem
chown $USER:$USER $WORKSPACE_DIR/certs/*.pem
chmod 644 $WORKSPACE_DIR/certs/fullchain.pem
chmod 600 $WORKSPACE_DIR/certs/privkey.pem
docker compose -f $WORKSPACE_DIR/compose.traefik.secure.tls.yml restart traefik
EOF

sudo chmod +x /etc/letsencrypt/renewal-hooks/deploy/copy-to-workspace.sh
```

### Option C: Commercial Certificate Authority

Purchase a certificate from a commercial CA (DigiCert, Sectigo, etc.) and:

1. Place `fullchain.pem` (certificate + intermediates) in `certs/`
2. Place `privkey.pem` (private key) in `certs/`
3. Set proper permissions:
   ```bash
   chmod 644 certs/fullchain.pem
   chmod 600 certs/privkey.pem
   ```

## 🏗️ Step 3: Build Workspace Image

Build the workspace-nouveau image:

```bash
docker compose -f compose.traefik.secure.tls.yml build user1
```

Or use the standard build command:

```bash
docker build -t workspace-nouveau:latest -f Dockerfile .
```

## 🚀 Step 4: Start Services

Start all services with TLS:

```bash
docker compose -f compose.traefik.secure.tls.yml up -d
```

This will:
1. Start Traefik reverse proxy on ports 80 (HTTP) and 443 (HTTPS)
2. Automatically redirect all HTTP traffic to HTTPS
3. Start traefik-forward-auth for OAuth2 authentication
4. Start the DTaaS web client
5. Start user workspaces (user1 and user2)

## 🌐 Step 5: Access Services

All services are now available via HTTPS with OAuth2 authentication:

- **DTaaS Web Interface**: https://your-domain.com/
- **User1 Workspace**: https://your-domain.com/user1
- **User2 Workspace**: https://your-domain.com/user2
- **Traefik Dashboard**: https://your-domain.com/dashboard/ (OAuth2 protected)

### First-Time Access

1. Navigate to https://your-domain.com/
2. You'll be redirected to GitLab for authentication
3. Authorize the DTaaS Workspace application
4. After successful authentication, you'll be redirected back to the DTaaS interface

## 🧪 Testing the Setup

### Verify TLS is Working

```bash
# Check certificate
openssl s_client -connect your-domain.com:443 -servername your-domain.com < /dev/null

# Or use curl
curl -vI https://your-domain.com/
```

### Verify HTTP → HTTPS Redirect

```bash
curl -I http://your-domain.com/
# Should return HTTP 301 or 308 redirect to HTTPS
```

### Check Service Status

```bash
docker compose -f compose.traefik.secure.tls.yml ps
```

### View Logs

```bash
# All services
docker compose -f compose.traefik.secure.tls.yml logs -f

# Specific service
docker compose -f compose.traefik.secure.tls.yml logs -f traefik
docker compose -f compose.traefik.secure.tls.yml logs -f traefik-forward-auth
```

## 🛠️ Maintenance

### Updating Services

```bash
# Pull latest images
docker compose -f compose.traefik.secure.tls.yml pull

# Recreate containers with new images
docker compose -f compose.traefik.secure.tls.yml up -d
```

### Stopping Services

```bash
docker compose -f compose.traefik.secure.tls.yml down
```

To also remove networks:

```bash
docker compose -f compose.traefik.secure.tls.yml down --remove-orphans
```

### Certificate Renewal

If using Let's Encrypt, certificates auto-renew. After renewal, restart Traefik:

```bash
docker compose -f compose.traefik.secure.tls.yml restart traefik
```

## 🔒 Security Checklist

- ✅ TLS/HTTPS enabled on all routes
- ✅ HTTP automatically redirects to HTTPS
- ✅ OAuth2 authentication required for all services
- ✅ Secure cookies enabled (`INSECURE_COOKIE=false`, `COOKIE_SECURE=true`)
- ✅ Valid TLS certificates from trusted CA (or Let's Encrypt)
- ✅ Private keys protected with proper file permissions (600)
- ✅ Secrets stored in `.env` file (not in compose file)
- ✅ No insecure Traefik API settings
- ✅ Log level set to INFO (not DEBUG) in production

## 🐛 Troubleshooting

### Browser Shows "Your connection is not private"

- **Using self-signed certificates**: This is expected. Add exception in browser or trust the certificate.
- **Using Let's Encrypt**: Verify certificate files exist and are valid. Check Traefik logs.
- **Domain mismatch**: Ensure `SERVER_DNS` matches your certificate's CN/SAN.

### OAuth2 Redirect Loop

1. Check that `OAUTH_URL` in `.env` is correct
2. Verify GitLab OAuth app redirect URI matches: `https://your-domain.com/_oauth` (must use HTTPS)
3. Check `SERVER_DNS` is set correctly in `.env`
4. Ensure `COOKIE_SECURE=true` is set for HTTPS

### "Invalid Certificate" Errors

```bash
# Check certificate validity
openssl x509 -in certs/fullchain.pem -text -noout | grep -A2 "Validity\|Subject:"

# Verify certificate matches private key
openssl x509 -noout -modulus -in certs/fullchain.pem | openssl md5
openssl rsa -noout -modulus -in certs/privkey.pem | openssl md5
# These should match
```

### Can't Access Traefik Dashboard

The dashboard is protected by OAuth2. Ensure:
1. You're authenticated (visit homepage first)
2. Your OAuth2 session is valid
3. URL is correct: `https://your-domain.com/dashboard/` (note trailing slash)

### Port 443 Already in Use

```bash
# Find what's using port 443
sudo lsof -i :443

# Or
sudo netstat -tlnp | grep :443
```

Common culprits: Apache, Nginx, or another Traefik instance.

### Certificate Not Loading

Check Traefik logs:

```bash
docker compose -f compose.traefik.secure.tls.yml logs traefik | grep -i cert
```

Verify file paths and permissions:

```bash
ls -l certs/
# Should show fullchain.pem (644) and privkey.pem (600)
```

## 📚 Additional Resources

- [Traefik Documentation](https://doc.traefik.io/traefik/)
- [Let's Encrypt Documentation](https://letsencrypt.org/docs/)
- [Traefik Forward Auth](https://github.com/thomseddon/traefik-forward-auth)
- [GitLab OAuth2 Documentation](https://docs.gitlab.com/ee/api/oauth2.html)
- [TRAEFIK_SECURE.md](TRAEFIK_SECURE.md) - OAuth2 setup without TLS

## 📋 Differences from compose.traefik.secure.yml

This TLS-enabled setup differs from `compose.traefik.secure.yml` in the following ways:

| Feature | compose.traefik.secure.yml | compose.traefik.secure.tls.yml |
|---------|---------------------------|--------------------------------|
| Protocol | HTTP only (port 80) | HTTPS (443) + HTTP→HTTPS redirect |
| TLS/SSL | ❌ No | ✅ Yes |
| Certificates | Not required | Required (Let's Encrypt, commercial, or self-signed) |
| Cookie Security | `INSECURE_COOKIE=true` | `INSECURE_COOKIE=false`, `COOKIE_SECURE=true` |
| Traefik API | Insecure mode enabled | Dashboard only, OAuth2 protected |
| Production Ready | ⚠️ Dev/Testing | ✅ Production |
| Entry Points | `web` only | `web` (80) + `websecure` (443) |
| Router TLS | Not configured | All routers use `tls=true` |
| Log Level | DEBUG | INFO |

## 🆘 Getting Help

If you encounter issues:

1. Check the [Troubleshooting](#-troubleshooting) section above
2. Review Traefik and traefik-forward-auth logs
3. Verify your `.env` configuration
4. Ensure certificates are valid and properly mounted
5. Consult the [Traefik documentation](https://doc.traefik.io/traefik/)
6. Open an issue in the repository with:
   - Error messages from logs
   - Your configuration (sanitized, no secrets)
   - Steps to reproduce the issue
