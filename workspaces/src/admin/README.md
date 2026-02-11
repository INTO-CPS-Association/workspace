# Admin Service

FastAPI service for workspace service discovery and management.

## Features

- `/services` endpoint - Returns JSON list of available workspace services
- Environment-aware configuration (uses MAIN_USER environment variable)

## Running

The service is automatically started when the workspace container starts.
It runs on port 8091 and is accessible via the nginx reverse proxy at `/services`.

## Development

Install dependencies:

```bash
poetry install
```

Run tests:

```bash
poetry run pytest
```

Run the service locally:

```bash
poetry run uvicorn admin.main:app --host 0.0.0.0 --port 8091
```
