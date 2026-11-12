# Developer Documentation

This document provides comprehensive information about environment variables,
build arguments, and configuration options used in the workspace Docker image
and build process.

## Table of Contents

- [Available Images](#available-images)
- [Docker Build Arguments](#docker-build-arguments)
- [Dockerfile Environment Variables](#dockerfile-environment-variables)
- [Runtime Environment Variables](#runtime-environment-variables)
- [Multi-Architecture Build](#multi-architecture-build)
- [Installation Scripts](#installation-scripts)
- [Startup Scripts](#startup-scripts)

## Available Images

The one Dockerfile variant:

| Dockerfile | Base Image | Desktop | Ubuntu Version |
| --- | --- | --- | --- |
| `Dockerfile.ubuntu.noble.xfce` | `kasmweb/core-ubuntu-noble:1.18.0` | XFCE | 24.04 (Noble) |

## Docker Build Arguments

These arguments are used when building the Docker image. Some
(`TARGETARCH`, `TARGETPLATFORM` and `BUILDPLATFORM`) are automatically
provided by Docker Buildx during multi-platform builds, while others
(`INSTALLATION`) can be set manually, changing contents of the resulting
image.

### INSTALLATION

- **Type**: Build ARG
- **Description**: Profile for installation of services.
- **Possible Values**: `full` or `minimal`
- **Default**: `full`
- **Usage**: Set it explicitly when building the image to change what
  services are installed:

  ```bash
  docker build -t workspace:latest \
    -f workspaces/Dockerfile.ubuntu.noble.xfce \
    --build-arg INSTALLATION=minimal ./workspaces
  ```

- **Example**:

  ```dockerfile
  ARG INSTALLATION
  FROM kasmweb/core-ubuntu-noble:1.18.0 AS configure
  ...
  FROM configure AS install-full
  # Install and environment layers for all services
  ...
  FROM configure AS install-minimal
  # Install and environment layers for the minimal number of services
  # needed to run the image
  ...
  FROM install-${INSTALLATION} AS setup
  ```

### TARGETARCH

- **Type**: Build ARG
- **Description**: Target architecture for the build
- **Possible Values**: `amd64`, `arm64`, `arm`, `ppc64le`, `s390x`, etc.
- **Usage**: Automatically set by Docker Buildx when building with `--platform`
- **Example**:

  ```dockerfile
  ARG TARGETARCH
  RUN echo "Building for architecture: ${TARGETARCH}"
  ```

### TARGETPLATFORM

- **Type**: Build ARG
- **Description**: Target platform in the format `os/arch[/variant]`
- **Possible Values**: `linux/amd64`, `linux/arm64`, `linux/arm/v7`, etc.
- **Usage**: Automatically set by Docker Buildx when building with `--platform`
- **Example**:

  ```dockerfile
  ARG TARGETPLATFORM
  RUN echo "Building for platform: ${TARGETPLATFORM}"
  ```

### BUILDPLATFORM

- **Type**: Build ARG
- **Description**: Platform of the builder machine (not the target)
- **Possible Values**: `linux/amd64`, `linux/arm64`, etc.
- **Usage**: Useful for cross-compilation scenarios
- **Example**:

  ```dockerfile
  ARG BUILDPLATFORM
  RUN echo "Building on platform: ${BUILDPLATFORM}"
  ```

## Dockerfile Environment Variables

These environment variables are set in the Dockerfile and are available during
both build and runtime.

### Service Ports

#### ADMIN_SERVER_PORT

- **Default**: `8091`
- **Description**: Port for the Admin FastAPI service
- **Usage**: Admin service listens on this port for service discovery requests

#### CODE_SERVER_PORT

- **Default**: `8054`
- **Description**: Port for VS Code Server
- **Usage**: VS Code web interface is accessible on this port

#### JUPYTER_SERVER_PORT

- **Default**: `8090`
- **Description**: Port for Jupyter Server
- **Usage**: Jupyter Notebook/Lab interface is accessible on this port

### Directory Paths

#### HOME

- **Default**: `/home/kasm-default-profile`
- **Description**: Home directory for the default Kasm user
- **Usage**: Working directory for user sessions

#### INST_DIR

- **Default**: `${STARTUPDIR}/install`
- **Description**: Directory containing installation scripts
- **Usage**: Referenced during Docker build to install software components

#### ADMIN_DIR

- **Default**: `${STARTUPDIR}/admin`
- **Description**: Build-time copy of the admin service sources
- **Usage**: `install_admin.sh` installs the service from it into
  `/opt/workspace-admin` and then deletes it; it does not exist in the
  final image

#### PERSISTENT_DIR

- **Default**: `/workspace`
- **Description**: Directory for persistent data storage
- **Usage**: Mounted volume for user data that persists across container restarts

#### STARTUPDIR

- **Default**: `/dockerstartup` (inherited from base image)
- **Description**: Directory containing startup scripts
- **Usage**: Executed during container initialization

### Kasm VNC Configuration

#### VNCOPTIONS

- **Default**: `"${VNCOPTIONS} -disableBasicAuth"`
- **Description**: Additional VNC server options
- **Usage**: Disables basic authentication for VNC (auth handled by container)

#### KASM_SVC_AUDIO

- **Default**: `0`
- **Description**: Disable audio service
- **Usage**: Audio streaming is disabled by default

#### KASM_SVC_AUDIO_INPUT

- **Default**: `0`
- **Description**: Disable audio input service
- **Usage**: Audio input/microphone is disabled by default

#### KASM_SVC_UPLOADS

- **Default**: `0`
- **Description**: Disable file upload service
- **Usage**: File uploads through Kasm interface are disabled

#### KASM_SVC_GAMEPAD

- **Default**: `0`
- **Description**: Disable gamepad service
- **Usage**: Gamepad support is disabled by default

#### KASM_SVC_WEBCAM

- **Default**: `0`
- **Description**: Disable webcam service
- **Usage**: Webcam access is disabled by default

#### KASM_SVC_PRINTER

- **Default**: `0`
- **Description**: Disable printer service
- **Usage**: Printing functionality is disabled by default

#### KASM_SVC_SMARTCARD

- **Default**: `0`
- **Description**: Disable smartcard service
- **Usage**: Smartcard reader support is disabled by default

## Runtime Environment Variables

These variables can be set when running the container to customize its behavior.

### MAIN_USER

- **Type**: Runtime ENV
- **Default**: Not set in Dockerfile, typically set in compose files or docker run
- **Description**: Username for the workspace session
- **Usage**: Used by startup scripts to configure user-specific paths and services
- **Example**:

  ```bash
  docker run -e MAIN_USER=user1 workspace:latest
  ```

### NO_VNC_PORT

- **Type**: Runtime ENV (read from Kasm base image)
- **Default**: Inherited from base image
- **Description**: Port for noVNC web interface
- **Usage**: Used by nginx configuration to proxy VNC connections

### JUPYTER_DISABLED

- **Type**: Runtime ENV
- **Default**: `0` (Jupyter is **enabled** by default in the `full` build)
- **Description**: Controls whether Jupyter Server is started at container runtime
- **Possible Values**: `0` (start Jupyter), `1` (skip Jupyter)
- **Usage**: Set to `1` to disable Jupyter (automatically set to `1` in the
  `minimal` build via Dockerfile)
- **Example**:

  ```bash
  docker run -e JUPYTER_DISABLED=1 workspace:latest
  ```

### VSCODE_DISABLED

- **Type**: Runtime ENV
- **Default**: `0` (VS Code Server is **enabled** by default in the `full` build)
- **Description**: Controls whether VS Code Server is started at container runtime
- **Possible Values**: `0` (start VS Code Server), `1` (skip VS Code Server)
- **Usage**: Set to `1` to disable VS Code Server (automatically set to `1` in the
  `minimal` build via Dockerfile)
- **Example**:

  ```bash
  docker run -e VSCODE_DISABLED=1 workspace:latest
  ```

## Multi-Architecture Build

### Building for Multiple Architectures

The workspace image supports building for multiple processor architectures using
Docker Buildx:

```bash
# Create a builder instance (one-time setup)
docker buildx create --name multiarch --use

# Single-platform build and load into local Docker
docker build -t workspace:latest \
  -f workspaces/Dockerfile.ubuntu.noble.xfce \
  --build-arg INSTALLATION=minimal \
  ./workspaces

# Multi-platform build without loading or saving
# Build arg is optional
docker buildx build \
  --platform linux/amd64,linux/arm64 \
  -t workspace:minimal-build \
  -f workspaces/Dockerfile.ubuntu.noble.xfce \
  --build-arg INSTALLATION=minimal \
  ./workspaces


# Multi-platform build -> push to registry
docker buildx build \
  --platform linux/amd64,linux/arm64 \
  -t workspace:minimal-build \
  -f workspaces/Dockerfile.ubuntu.noble.xfce \
  --build-arg INSTALLATION=minimal \
  --push \
  ./workspaces

# Build each arch to Docker-format tar, then load (creates separate images locally)
# NOTE: use type=docker (not type=tar) so that docker load can read the archive.
docker buildx build \
  --platform linux/amd64 \
  -t workspace-amd64 \
  -f workspaces/Dockerfile.ubuntu.noble.xfce \
  --output type=docker,dest=./workspace-amd64.tar \
  ./workspaces

docker buildx build \
  --platform linux/arm64 \
  -t workspace-arm64 \
  -f workspaces/Dockerfile.ubuntu.noble.xfce \
  --output type=docker,dest=./workspace-arm64.tar \
  ./workspaces

docker load -i ./workspace-amd64.tar
docker load -i ./workspace-arm64.tar
```

### Architecture-Specific Considerations

When adding new software or scripts:

1. **Check architecture compatibility**: Ensure downloaded binaries support both
   amd64 and arm64
2. **Pin both architectures**: A `bin-tar` entry in `dependencies.lock` holds
   a source URL and checksum for each of `amd64` and `arm64`
3. **Test on both architectures**: If possible, test builds on both platforms
4. **Use QEMU for testing**: You can test arm64 builds on amd64 using QEMU
   emulation

`src/install/packages/installation_util.py` picks the architecture once, as
`ARCHITECTURE`: `TARGETARCH` when Docker Buildx sets it, otherwise
`os.uname().machine`. `amd64`/`x86_64` select the `amd64` entry and
`arm64`/`aarch64` the `arm64` entry; any other value stops the build. Install
scripts therefore do not handle the architecture themselves.

## Installation Scripts

Installation scripts are located in `src/install/` and are executed during the
Docker build process, one `RUN` per script.

- `src/install/dependencies.lock` pins the version, source and checksum of
  every package. Its format is described in
  `src/install/LOCKFILE_DESCRIPTION.md`.
- `src/install/packages/install_<component>.py` installs one entry of the lock
  file through `installation_util.get_dependencies_for_package`.
- `src/install/packages/install_python.sh` installs Python and `python3-venv`
  with apt; it runs before the other scripts.
- `src/install/admin/install_admin.sh` installs the admin service from the
  local source tree into a venv under `/opt/workspace-admin`.

### Script Environment

- **Working Directory**: `$HOME` (`/home/kasm-default-profile`)
- **User**: `root`
- **Available Variables**: All Dockerfile ENV variables plus ARG variables
- **Execution**: Scripts run in order specified in Dockerfile RUN instruction

### Best Practices for Installation Scripts

1. **Pin versions in the lock file**: Add the package, with exact versions and
   checksums, to `dependencies.lock` instead of hard-coding them in a script
2. **Use the shared installer**: Call `get_dependencies_for_package` rather
   than downloading files yourself, so checksums are verified
3. **Keep shell scripts strict**: Start them with `#!/usr/bin/env bash` and
   `set -euo pipefail`
4. **Clean up**: Remove temporary files and package caches

### Real-World Examples

#### code-server Installation

code-server is a `bin-tar` package. Its lock entry names a tarball and its
checksum per architecture:

```json
"code-server": {
  "type": "bin-tar",
  "compression": "gz",
  "amd64": {
    "source": "https://github.com/coder/code-server/releases/download/v4.143.1/code-server-4.143.1-linux-amd64.tar.gz",
    "checksum": "614877cf71005f14ea252bd2d9b1c12237cf7d73681ef150f0dff7f13849fdb5"
  },
  "arm64": {
    "source": "https://github.com/coder/code-server/releases/download/v4.143.1/code-server-4.143.1-linux-arm64.tar.gz",
    "checksum": "51481a891754dc2585b86d007aec24ac675453fc5ef6cfa346c4462449277384"
  }
}
```

and `src/install/packages/install_code_server.py` installs it:

```python
from installation_util import get_dependencies_for_package

get_dependencies_for_package("code-server").default_installation()
```

`default_installation()` downloads the tarball for `ARCHITECTURE`, verifies
its checksum, unpacks it under `/opt` and links its binaries into
`/usr/local/bin`.

#### Firefox Installation

`src/install/packages/install_firefox.py` needs the GNU triplet for a system
library path, so it maps `ARCHITECTURE` itself:

```python
from installation_util import get_dependencies_for_package, ARCHITECTURE

LIB_ARCH_MAP = {
    "amd64": "x86_64", "x86_64": "x86_64", "x64": "x86_64",
    "arm64": "aarch64", "aarch64": "aarch64",
}
LIB_ARCH = LIB_ARCH_MAP[ARCHITECTURE]
```

## Startup Scripts

Startup scripts are located in `src/startup/` and are executed when the
container starts.

### Startup Script Order

1. `dtaas_shim.sh` - First script that restores environment and switches to
   MAIN_USER
2. `kasm_default_profile.sh` - Base image startup (inherited)
3. `vnc_startup.sh` - VNC server initialization (inherited)
4. `custom_startup.sh` - Custom service initialization

### Available Variables at Startup

- All Dockerfile ENV variables
- Runtime environment variables (e.g., `MAIN_USER`)
- Restored variables from `/tmp/.docker_set_envs`

### dtaas_shim.sh

- **Purpose**: Environment restoration and user switching
- **Key Functions**:
  - Sources `/tmp/.docker_set_envs` to restore build-time environment
  - Switches execution to `MAIN_USER` using `su -m`
  - Continues startup chain

### custom_startup.sh

- **Purpose**: Start custom services
- **Key Functions**:
  - Configures nginx reverse proxy
  - Starts Jupyter Server on `$JUPYTER_SERVER_PORT` (unless `INSTALLATION=minimal`)
  - Starts VS Code Server on `$CODE_SERVER_PORT` (unless `INSTALLATION=minimal`)
  - Starts Admin service on `$ADMIN_SERVER_PORT`

### configure_nginx.py

- **Purpose**: Generate nginx configuration from template
- **Key Functions**:
  - Substitutes environment variables in `nginx.conf` template
  - Configures routing for all services
  - Handles path-based routing for multi-user deployments

## Environment Variable Precedence

1. **Runtime** (`docker run -e` or `compose.yml`): Highest priority, overrides
   all
2. **Dockerfile ENV**: Default values, can be overridden at runtime
3. **Dockerfile ARG**: Only available during build, not at runtime

## Debugging Environment Variables

### During Build

```bash
# Add to Dockerfile to inspect values during build
RUN env | sort
RUN echo "TARGETARCH=${TARGETARCH}"
RUN echo "TARGETPLATFORM=${TARGETPLATFORM}"
```

### During Runtime

```bash
# Exec into running container
docker exec -it <container> bash
env | sort

# Check specific variable
echo $MAIN_USER
echo $ADMIN_SERVER_PORT
```

### Check Restored Environment

```bash
# View environment variables saved during build
docker exec -it <container> cat /tmp/.docker_set_envs
```

## Adding New Environment Variables

When adding new environment variables:

1. **Document here**: Add entry to this file with description and default value
2. **Update Dockerfile**: Add to ENV instruction or use ARG for build-time only
3. **Update scripts**: Use the variable in relevant scripts
4. **Update compose files**: Set runtime values in compose.yml examples if needed
5. **Update documentation**: Update README.md if user-facing

## References

- [Docker ARG and ENV](https://docs.docker.com/engine/reference/builder/#arg)
- [Docker Multi-platform builds](https://docs.docker.com/build/building/multi-platform/)
- [Dockerfile best practices](https://docs.docker.com/develop/develop-images/dockerfile_best-practices/)
- [Kasm Workspaces Documentation](https://kasmweb.com/docs/latest/index.html)
