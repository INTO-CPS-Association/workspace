# Using Workspace with Traefik Reverse Proxy

This guide explains how to use the workspace container with Traefik reverse proxy
for multi-user deployments in the DTaaS installation.

## Prerequisites

- Docker Engine v27 or later
- Docker Compose v2.x
- Sufficient system resources (at least 1GB RAM per workspace instance)
- Port 80 available on your host machine

## Overview

The `compose.traefik.yml` file sets up:

- **Traefik** reverse proxy on port 80
- **user1** workspace using the workspace-nouveau image
- **user2** workspace using the mltooling/ml-workspace-minimal image
- Two Docker networks: `dtaas-frontend` and `dtaas-users`

Traefik routes requests to different workspace instances based on URL path prefixes.

## Building the Workspace Image

Before starting the services, build the workspace-nouveau image:

```bash
docker compose -f compose.traefik.yml build user1
```

Or use the standard build command:

```bash
docker build -t workspace-nouveau:latest -f Dockerfile .
```

## Starting Services

To start all services (Traefik and both workspace instances):

```bash
docker compose -f compose.traefik.yml up -d
```

This will:

1. Start the Traefik reverse proxy on port 80
2. Start user1 workspace with MAIN_USER=user1
3. Start user2 workspace with MAIN_USER=user2

## Accessing Workspaces

Once all services are running, access the workspaces through Traefik:

### User1 Workspace (workspace-nouveau)

- **VNC Desktop**: `http://localhost/user1/vnc`
- **VS Code**: `http://localhost/user1/tools/vscode`
- **Jupyter Notebook**: `http://localhost/user1`
- **Jupyter Lab**: `http://localhost/user1/lab`

### User2 Workspace (ml-workspace-minimal)

- **Main Interface**: `http://localhost/user2`
- **Other services**: Follow the ml-workspace-minimal documentation for
  available services under the `/user2` path prefix

## Monitoring and Debugging

### Check Service Status

```bash
docker compose -f compose.traefik.yml ps
```

### View Traefik Logs

```bash
docker compose -f compose.traefik.yml logs traefik
```

The Traefik API dashboard is available at `http://localhost/dashboard/`
(note the trailing slash).

### View Workspace Logs

```bash
# User1 logs
docker compose -f compose.traefik.yml logs user1

# User2 logs
docker compose -f compose.traefik.yml logs user2
```

## Stopping Services

To stop all services:

```bash
docker compose -f compose.traefik.yml down
```

To stop and remove volumes:

```bash
docker compose -f compose.traefik.yml down -v
```

## Network Configuration

The setup uses two Docker networks:

- **dtaas-frontend**: Used by Traefik for external communication
- **dtaas-users**: Shared network for workspace instances and Traefik

This separation allows for better network isolation and security.

## Customization

### Adding More Users

To add additional workspace instances, add a new service in `compose.traefik.yml`:

```yaml
user3:
  image: workspace-nouveau:latest
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

### Changing Ports

To use a different port for Traefik, modify the ports section:

```yaml
ports:
  - "8080:80"  # Access via http://localhost:8080/user1
```

## Troubleshooting

### Services Not Starting

1. Check if port 80 is available:

   ```bash
   sudo lsof -i :80
   ```

2. Verify Docker networks exist:

   ```bash
   docker network ls | grep dtaas
   ```

### Routing Issues

1. Verify Traefik configuration:

   ```bash
   docker compose -f compose.traefik.yml logs traefik | grep -i error
   ```

2. Check service labels:

   ```bash
   docker inspect <container_name> | grep -A 10 Labels
   ```

### Performance Issues

If workspaces are slow:

1. Increase shared memory size in `compose.traefik.yml`:

   ```yaml
   shm_size: 1g  # Increase from 512m
   ```

2. Monitor resource usage:

   ```bash
   docker stats
   ```

## Security Considerations

⚠️ **Important**: This configuration is designed for development and testing.
For production use:

- Disable Traefik insecure API (`--api.insecure=true`)
- Configure HTTPS/TLS certificates
- Implement authentication and authorization
- Review and tighten CORS settings
- Use secure communication between services
- Consider using Docker secrets for sensitive data

## Testing

To verify the setup is working correctly:

1. Start all services
2. Wait for containers to be healthy (30-60 seconds)
3. Access each workspace URL and verify the interface loads
4. Check that routing works correctly for each user path prefix

## Support

For issues or questions:

- Check the [main README](README.md) for general workspace information
- Review [DTaaS documentation](https://github.com/INTO-CPS-Association/DTaaS)
- Open an issue in the repository
