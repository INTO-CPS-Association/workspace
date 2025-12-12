# Copilot Instructions for Containerized Virtual Desktop Environment

## Repository Overview

This repository contains a Dockerfile and associated configuration for building a containerized virtual desktop environment with KasmVNC, Firefox, Jupyter, and VS Code Server.

## Project Structure

### `config/` - Configuration Files
Contains required configuration for software services installed in the Docker image.
- `kasm_vnc/kasmvnc.yaml` - KasmVNC server configuration

### `install/` - Installation Scripts
Contains installation scripts for all software components installed in the Docker image.
- `firefox/install_firefox.sh` - Firefox browser installation
- `jupyter/install_jupyter.sh` - Jupyter notebook installation
- `vscode/install_vscode_server.sh` - VS Code Server installation

**Script Requirements:**
- All bash/zsh scripts must be linted with shellcheck
- All Python scripts must be linted with pylint/flake8
- Scripts must follow proper style conventions for their respective languages
- Include error handling and proper exit codes

### `startup/` - Startup Scripts
Contains custom startup scripts for the container runtime.
- `custom_startup.sh` - Pluggable startup service configuration

**Startup Script Requirements:**
- Must be executable and properly handle signals
- Should support graceful shutdown
- Follow the same linting requirements as installation scripts

### Top-Level Files
- `Dockerfile` - Main container image definition (must be linted with hadolint)
- `compose.yaml` - Docker Compose configuration (must be validated with docker compose config)
- `LICENSE.md` - Project license
- `README.md` - Project documentation

## Development Guidelines

### Code Quality Standards

#### Shell Scripts (bash/zsh)
- Use shellcheck for linting
- Follow Google Shell Style Guide
- Include proper shebang lines
- Use `set -e` for error handling
- Quote variables appropriately
- Use meaningful variable names

#### Python Scripts
- Use pylint or flake8 for linting
- Follow PEP 8 style guide
- Include docstrings for functions and modules
- Use type hints where appropriate

#### Dockerfile
- Use hadolint for linting
- Pin specific versions for base images and packages
- Minimize layers by combining RUN commands where logical
- Use multi-stage builds if appropriate
- Clean up package manager caches
- Use non-root user when possible

#### Docker Compose
- Validate with `docker compose config`
- Use version 3.x syntax
- Define explicit service dependencies
- Use environment variables for configuration
- Include volume mounts for persistent data

### File Modifications

When modifying files:
1. **Installation scripts** - Ensure all dependencies are installed and versions are pinned
2. **Configuration files** - Validate syntax and compatibility with service versions
3. **Dockerfile** - Run linting and ensure build succeeds
4. **compose.yaml** - Validate configuration before committing

### Testing

Before committing changes:
- Lint all modified scripts
- Test Docker image builds successfully
- Verify services start correctly in the container
- Check that persistent directories are properly mounted

### Common Tasks

#### Adding a New Software Component
1. Create installation script in `install/<component>/`
2. Add configuration to `config/<component>/` if needed
3. Update Dockerfile to call the installation script
4. Update README.md with component information

#### Modifying Startup Behavior
1. Edit or add scripts in `startup/`
2. Ensure scripts are executable
3. Test container startup and shutdown
4. Verify all services initialize correctly

## Linting Commands

When suggesting or making changes, ensure these commands pass:

```bash
# Shell scripts
shellcheck install/**/*.sh startup/*.sh

# Dockerfile
hadolint Dockerfile

# Docker Compose
docker compose -f compose.yaml config

# Python scripts (if any)
pylint **/*.py
flake8 **/*.py
```

## Best Practices

- Always use absolute paths in scripts
- Handle errors gracefully with proper exit codes
- Log important operations for debugging
- Use environment variables for configurable values
- Document any non-obvious logic with comments
- Test changes in a clean container environment
