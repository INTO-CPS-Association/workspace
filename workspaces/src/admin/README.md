# Admin Service

FastAPI service for workspace service discovery and management.

## Features

- `/services` endpoint - Returns JSON list of available workspace services
- Environment-aware configuration (uses MAIN_USER environment variable)
- Command-line interface for standalone operation

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

# List services without starting the server
poetry run workspace-admin --list-services

# Run with auto-reload for development
poetry run workspace-admin --reload

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
