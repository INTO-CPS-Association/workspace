# Workspace with Traefik Reverse Proxy

This guide explains how to use the workspace container with Traefik reverse proxy
for multi-user deployments in the DTaaS installation.

## ❓ Prerequisites

✅ Docker Engine v27 or later  
✅ Sufficient system resources (at least 1GB RAM per workspace instance)  
✅ Port 80 available on your host machine

## 🗒️ Overview

The `compose.traefik.yml` file sets up:

- **Traefik** reverse proxy on port 80
- **user1** workspace using the workspace image
- **user2** workspace using the mltooling/ml-workspace-minimal image
- Two Docker networks: `dtaas-frontend` and `dtaas-users`

Traefik routes requests to different workspace instances based on URL path prefixes.

## ⚙️ Initial Configuration

Please follow the steps in [`CONFIGURATION.md`](CONFIGURATION.md) for the `compose.traefikyml` composition before running the setup.

## 💪 Get Workspace Image

You can either use a pre-built image or build it locally.

### Option 1: Use Pre-built Image (Recommended)

Pull the latest image from GitHub Container Registry or Docker Hub:

```bash
# From GitHub Container Registry
docker pull ghcr.io/into-cps-association/workspace:latest
docker tag ghcr.io/into-cps-association/workspace:latest workspace:latest

# Or from Docker Hub
docker pull intocps/workspace:latest
docker tag intocps/workspace:latest workspace:latest
```

### Option 2: Build Locally

Build the workspace image, either with docker compose:

```bash
docker compose -f workspaces/test/dtaas/compose.traefik.yml build user1
```

Or using the standard build command:

```bash
docker build -t workspace:latest -f workspaces/Dockerfile.ubuntu.noble.gnome ./workspaces
```

## :rocket: Start Services

To start all services (Traefik and both workspace instances):

```bash
docker compose -f workspaces/test/dtaas/compose.traefik.yml up -d
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
docker compose -f workspaces/test/dtaas/compose.traefik.yml down
```

## 🔧 Customization

### Adding More Users

To add additional workspace instances, add a new service in `compose.traefik.yml`:

```yaml
user3:
  image: workspace:latest
  restart: unless-stopped
    build:
      context: ../..
      dockerfile: Dockerfile.ubuntu.noble.gnome
  environment:
    - MAIN_USER=${USERNAME3:-user3}
  volumes:
    - ./files/user3:/workspace
    - ./files/common:/workspace/common
  shm_size: 512m
  labels:
    - "traefik.enable=true"
    - "traefik.http.routers.u3.entryPoints=web"
    - "traefik.http.routers.u3.rule=PathPrefix(`/${USERNAME3:-user3}`)"
  networks:
    - users
```

And then, setup the base structure of the persistent directories for the new user:

```bash
cp -r workspaces/test/dtaas/files/user1 workspaces/test/dtaas/files/user3
```

## :shield: Security Considerations

⚠️ **Important**: This configuration is designed for development and testing, and should not be reconfigured to be exposed to the internet.

For setting up a composition that can be exposed to the internet, see [TRAEFIK_TLS.md](./TRAEFIK_TLS.md).
