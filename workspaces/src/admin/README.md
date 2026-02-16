# Admin Service

FastAPI service for workspace service discovery and management.

## Features

- `/services` endpoint - Returns JSON list of available workspace services
- Path prefix support for multi-user deployments
- Command-line interface for standalone operation
- Optional git backup worker for `$WORKSPACE_DIR/private` and `$WORKSPACE_DIR/common`

## Running

### As a Service (in workspace container)

The service is automatically started when the workspace container starts.
It runs on port 8091 and is accessible via the nginx reverse proxy at `/services`.

### As a CLI Utility

```bash
# Install dependencies
poetry install

# Run the service
poetry run workspace-admin

# Run with custom port
poetry run workspace-admin --port 9000

# Run with path prefix for multi-user setup
poetry run workspace-admin --path-prefix dtaas-user

# List services without starting the server
poetry run workspace-admin --list-services

# Run with auto-reload for development
poetry run workspace-admin --reload

# Run with git backup enabled from explicit config file
poetry run workspace-admin --config ./config.env

# Show help
poetry run workspace-admin --help
```

## Development

Install dependencies:

```bash
poetry install
```

Run tests:

```bash
poetry run pytest -v
```

Run tests with coverage:

```bash
poetry run pytest --cov=admin --cov-report=html --cov-report=term
```

Run code quality checks:

```bash
poetry run pylint src/admin tests
```

## Git backup configuration

Copy and edit `config.env.example` to `$HOME/.workspace/config.env` (or pass
`--config`):

```bash
cp config.env.example "$HOME/.workspace/config.env"
```

The admin service will clone and periodically sync configured `private` and
`common` repositories every 5 minutes by default.
