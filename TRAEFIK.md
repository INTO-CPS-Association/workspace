# Workspace with Traefik Reverse Proxy

This guide explains how to use the workspace container with Traefik reverse proxy
for multi-user deployments in the DTaaS installation.

## ❓ Prerequisites

✅ Docker Engine v27 or later
✅ Docker Compose v2.x
✅ Sufficient system resources (at least 1GB RAM per workspace instance)
✅ Port 80 available on your host machine

## 🗒️ Overview

The `compose.traefik.yml` file sets up:

- **Traefik** reverse proxy on port 80
- **user1** workspace using the workspace image
- **user2** workspace using the mltooling/ml-workspace-minimal image
- Two Docker networks: `dtaas-frontend` and `dtaas-users`

Traefik routes requests to different workspace instances based on URL path prefixes.

## 💪 Get Workspace Image

You can either use a pre-built image or build it locally.

### Option 1: Use Pre-built Image (Recommended)

Pull the latest image from GitHub Container Registry or Docker Hub:

```bash
# From GitHub Container Registry
docker pull ghcr.io/into-cps-association/workspace:latest
docker tag ghcr.io/into-cps-association/workspace:latest workspace:latest

# Or from Docker Hub
docker pull intocpsassociation/workspace:latest
docker tag intocpsassociation/workspace:latest workspace:latest
```

### Option 2: Build Locally

Before starting the services, build the workspace image:

```bash
docker compose -f compose.traefik.yml build user1
```

Or use the standard build command:

```bash
docker build -t workspace:latest -f Dockerfile .
```

## :rocket: Start Services

To start all services (Traefik and both workspace instances):

```bash
docker compose -f compose.traefik.yml up -d
```

This will:

1. Start the Traefik reverse proxy on port 80
2. Start workspace of both users

## :technologist: Accessing Workspaces

Once all services are running, access the workspaces through Traefik:

### User1 Workspace (workspace)

- **VNC Desktop**: `http://localhost/user1/tools/vnc?path=user1%2Ftools%2Fvnc%2Fwebsockify`
- **VS Code**: `http://localhost/user1/tools/vscode`
- **Jupyter Notebook**: `http://localhost/user1`
- **Jupyter Lab**: `http://localhost/user1/lab`

### User2 Workspace (ml-workspace-minimal)

- **VNC Desktop**: `http://localhost/user2/tools/vnc/?password=vncpassword`
- **VS Code**: `http://localhost/user2/tools/vscode/`
- **Jupyter Notebook**: `http://localhost/user2`
- **Jupyter Lab**: `http://localhost/user2/lab`

## 🛑 Stopping Services

To stop all services:

```bash
docker compose -f compose.traefik.yml down
```

## ⚙️ Network Configuration

The setup uses two Docker networks:

- **dtaas-frontend**: Used by Traefik for external communication
- **dtaas-users**: Shared network for workspace instances and Traefik

This separation allows for better network isolation and security.

## 🔧 Customization

### Adding More Users

To add additional workspace instances, add a new service in `compose.traefik.yml`:

```yaml
user3:
  image: workspace:latest
  restart: unless-stopped
  environment:
    - MAIN_USER=user3
  shm_size: 512m
  labels:
    - "traefik.enable=true"
    - "traefik.http.routers.u3.entryPoints=web"
    - "traefik.http.routers.u3.rule=PathPrefix(`/user3`)"
  networks:
    - users
```

## :shield: Security Considerations

⚠️ **Important**: This configuration is designed for development and testing.
For production use:

- Disable Traefik insecure API (`--api.insecure=true`)
- Configure HTTPS/TLS certificates
- Implement authentication and authorization
- Review and tighten CORS settings
- Use secure communication between services
- Consider using Docker secrets for sensitive data
