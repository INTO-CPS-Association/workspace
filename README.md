# Workspace Nouveau

A new workspace image for [DTaaS](https://github.com/INTO-CPS-Association/DTaaS).

We are still very much in the explorative phase. Everything that is
working is subject to change.

## 📦 Pre-built Images

Pre-built Docker images are available from:

- **GitHub Container Registry**: `ghcr.io/into-cps-association/workspace:latest`
- **Docker Hub**: `intocpsassociation/workspace:latest`

You can pull the image directly:

```bash
# From GitHub Container Registry
docker pull ghcr.io/into-cps-association/workspace:latest

# From Docker Hub
docker pull intocpsassociation/workspace:latest
```

## 🦾 Build Workspace Image

If you want to build the image locally instead of using pre-built images:

*Either*  
Using plain `docker` command:

```ps1
docker build -t workspace:latest -f Dockerfile .
```

**Or**
using `docker compose`:

```ps1
docker compose build
```

## :running: Run it

*Either*  
Using plain `docker` command:

```ps1
docker run -d --shm-size=512m \
  -p 8080:8080\
  -e MAIN_USER=dtaas-user --name workspace  workspace:latest
```

:point_right: You can change the **MAIN_USER** variable to any other username
of your choice.

*OR*  
using `docker compose`:

```ps1
docker compose -f compose.yml up -d
```

## :technologist: Use Services

An active container provides the following services
:warning: please remember to change dtaas-user to the username chosen in the
previous command

* ***Open workspace*** -
  <http://localhost:8080/dtaas-user/tools/vnc?path=dtaas-user%2Ftools%2Fvnc%2Fwebsockify>
* ***Open VSCode*** - <http://localhost:8080/dtaas-user/tools/vscode>
* ***Open Jupyter Notebook*** - <http://localhost:8080>
* ***Open Jupyter Lab*** - <http://localhost:8080/dtaas-user/lab>

## :broom: Clean Up

*Either*  
Using plain `docker` command:

```bash
docker stop workspace
docker rm workspace
```

*Or*
using `docker compose`:

```bash
docker compose -f compose.yml down
```

## :arrows_counterclockwise: Deployment Options

This workspace supports multiple deployment configurations depending on your needs:

### 1. Standalone Development (Single User)

**File**: `compose.yml`  
**Use case**: Local development, single user  
**Features**: Basic workspace without reverse proxy  
**Documentation**: See sections above

### 2. Multi-User Development (HTTP)

**File**: `compose.traefik.yml`  
**Use case**: Multi-user development/testing without authentication  
**Features**: Traefik reverse proxy, multiple workspaces  
**Documentation**: [TRAEFIK.md](TRAEFIK.md)

### 3. Multi-User with OAuth2 (HTTP)

**File**: `compose.traefik.secure.yml`  
**Use case**: Development/testing with OAuth2 authentication  
**Features**: Traefik reverse proxy, OAuth2 authentication, HTTP only  
**Documentation**: [TRAEFIK_TLS.md](TRAEFIK_TLS.md)

### 4. Production Deployment (HTTPS + OAuth2)

**File**: `compose.traefik.secure.tls.yml`  
**Use case**: Production deployment with full security  
**Features**: Traefik reverse proxy, OAuth2 authentication, TLS/HTTPS  
**Documentation**: [TRAEFIK_TLS.md](TRAEFIK_TLS.md)

Choose the configuration that best matches your deployment requirements.

## 📊 Deployment Comparison

| Feature | compose.yml | compose.traefik.yml | compose.traefik.secure.yml | compose.traefik.secure.tls.yml |
| ------- | ----------- | ------------------- | -------------------------- | ------------------------------ |
| Reverse Proxy | ❌ | ✅ | ✅ | ✅ |
| Multi-user | ❌ | ✅ | ✅ | ✅ |
| OAuth2 Auth | ❌ | ❌ | ✅ | ✅ |
| TLS/HTTPS | ❌ | ❌ | ❌ | ✅ |
| Production Ready | ❌ | ❌ | ❌ | ✅ |
| Use Case | Local dev | Multi-user dev | Secure dev/test | Production |

## :package: Publishing

For information about publishing Docker images to registries,
see [PUBLISHING.md](PUBLISHING.md).

## Development

### Code Quality

This project enforces strict code quality checks via GitHub Actions:

* **Dockerfile**: Linted with [hadolint](https://github.com/hadolint/hadolint)
  \- all errors must be fixed
* **Shell scripts**: Checked with [shellcheck](https://www.shellcheck.net/)
  \- all warnings must be addressed
* **Python scripts**: Linted with [flake8](https://flake8.pycqa.org/) and
  [pylint](https://pylint.org/) - all errors must be resolved
* **YAML files**: Validated with [yamllint](https://yamllint.readthedocs.io/)
  \- all issues must be corrected
* **Markdown files**: Checked with
  [markdownlint](https://github.com/DavidAnson/markdownlint) - all style
  violations must be fixed

All quality checks must pass before code can be merged. The workflows will
fail if any linting errors are detected.

### Configuration Files

Linting behavior is configured through:

* `.shellcheckrc` - shellcheck configuration
* `.pylintrc` - pylint configuration
* `.yamllint.yml` - yamllint configuration
* `.markdownlint.yaml` - markdownlint configuration
