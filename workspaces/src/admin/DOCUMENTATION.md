# Admin Service Documentation

The admin service is a FastAPI-based REST API that provides service discovery
and management capabilities for the DTaaS workspace.

## Overview

The service runs on port 8091 (configurable via `ADMIN_SERVER_PORT` environment
variable) and is proxied through nginx to be accessible at the `/services`
endpoint.

## Endpoints

### GET /services

Returns a JSON object containing information about all available workspace
services.

**Request**:

```bash
curl http://localhost:8080/{username}/services
```

**Response**: Status 200 OK

```json
{
  "desktop": {
    "name": "Desktop",
    "description": "Virtual Desktop Environment",
    "endpoint": "tools/vnc?path={username}%2Ftools%2Fvnc%2Fwebsockify"
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

**Notes**:
- The `{username}` placeholder in endpoints is automatically replaced with the
  value of the `MAIN_USER` environment variable
- Service endpoints are relative paths that should be appended to the base
  workspace URL
- Empty string endpoints indicate the service is available at the root path

### GET /health

Health check endpoint for monitoring service availability.

**Request**:

```bash
curl http://localhost:8091/health
```

**Response**: Status 200 OK

```json
{
  "status": "healthy"
}
```

### GET /

Root endpoint providing service metadata and available endpoints.

**Request**:

```bash
curl http://localhost:8091/
```

**Response**: Status 200 OK

```json
{
  "service": "Workspace Admin Service",
  "version": "0.1.0",
  "endpoints": {
    "/services": "Get list of available workspace services",
    "/health": "Health check endpoint"
  }
}
```

## Architecture

### Service Discovery Flow

1. User accesses `http://{domain}/{username}/services`
2. nginx receives the request and routes it to the admin service on port 8091
3. Admin service reads the `services_template.json` file
4. Template placeholders (e.g., `{MAIN_USER}`) are replaced with environment
   variable values
5. JSON response is returned to the client

### Components

- **FastAPI Application** (`src/admin/main.py`): Core service implementation
- **Services Template** (`src/admin/services_template.json`): JSON template
  defining available services
- **nginx Configuration** (`startup/nginx.conf`): Reverse proxy routing
- **Startup Script** (`startup/custom_startup.sh`): Service bootstrap and
  monitoring

## Environment Variables

- `MAIN_USER`: Username for the workspace (default: `dtaas-user`)
- `ADMIN_SERVER_PORT`: Port for the admin service (default: `8091`)

## Development

### Running Tests

```bash
cd workspaces/src/admin
poetry install
poetry run pytest -v
```

### Running Locally

```bash
cd workspaces/src/admin
export MAIN_USER=testuser
export ADMIN_SERVER_PORT=8091
poetry run uvicorn admin.main:app --host 0.0.0.0 --port 8091
```

### Adding New Services

To add a new service to the workspace:

1. Update `services_template.json` with the new service definition:

```json
{
  "new_service": {
    "name": "New Service Name",
    "description": "Description of the service",
    "endpoint": "path/to/service"
  }
}
```

2. If the service requires dynamic values, use placeholders like `{MAIN_USER}`
   which will be substituted at runtime

3. No code changes are required - the service automatically reads and processes
   the template

## Integration with DTaaS

The `/services` endpoint enables the DTaaS frontend to:

1. Dynamically discover available workspace services
2. Display service shortcuts to users
3. Support different workspace configurations without hardcoded service lists
4. Handle multi-user deployments where each user has different available
   services

This replaces the previous approach of hardcoding service endpoints in the
frontend configuration, enabling more flexible workspace deployments.

## Future Enhancements

Potential future enhancements include:

- Service registry for dynamic service registration
- Authentication and authorization integration
- Service health monitoring and status reporting
- Custom service definitions per workspace type
- Web application firewall integration for zero-trust security
