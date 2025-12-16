# Workspace Nouveau

A new workspace image for [DTaaS](https://github.com/INTO-CPS-Association/DTaaS).

We are still very much in the explorative phase. Everything that is
working is subject to change.

## 📦 Pre-built Images

Pre-built Docker images are available from:

- **GitHub Container Registry**: `ghcr.io/into-cps-association/workspace:latest`
- **Docker Hub**: `intocpsassociation/workspace-nouveau:latest`

You can pull the image directly:

```bash
# From GitHub Container Registry
docker pull ghcr.io/into-cps-association/workspace:latest

# From Docker Hub
docker pull intocpsassociation/workspace-nouveau:latest
```

## 🦾 Build Workspace Image

If you want to build the image locally instead of using pre-built images:

*Either*  
Using plain `docker` command:

```ps1
docker build -t workspace-nouveau:latest -f Dockerfile .
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
  -e MAIN_USER=dtaas-user --name workspace  workspace-nouveau:latest
```

:point_right: You can change the **MAIN_USER** variable to any other username of your choice.

*OR*  
using `docker compose`:

```ps1
docker compose -f compose.yml up -d
```

## :technologist: Use Services

An active container provides the following services
:warning: please remember to change dtaas-user to the username chosen in the previous command

* ***Open workspace*** - http://localhost:8080/dtaas-user/tools/vnc?path=dtaas-user%2Ftools%2Fvnc%2Fwebsockify
* ***Open VSCode*** - http://localhost:8080/dtaas-user/tools/vscode
* ***Open Jupyter Notebook*** - http://localhost:8080
* ***Open Jupyter Lab*** - http://localhost:8080/dtaas-user/lab

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

## :arrows_counterclockwise: Using with Traefik Reverse Proxy

For multi-user deployments with Traefik reverse proxy integration, see [TRAEFIK.md](TRAEFIK.md).

## Development

### Code Quality

This project enforces strict code quality checks via GitHub Actions:

* **Dockerfile**: Linted with [hadolint](https://github.com/hadolint/hadolint) - all errors must be fixed
* **Shell scripts**: Checked with [shellcheck](https://www.shellcheck.net/) - all warnings must be addressed
* **Python scripts**: Linted with [flake8](https://flake8.pycqa.org/) and [pylint](https://pylint.org/) - all errors must be resolved
* **YAML files**: Validated with [yamllint](https://yamllint.readthedocs.io/) - all issues must be corrected
* **Markdown files**: Checked with [markdownlint](https://github.com/DavidAnson/markdownlint) - all style violations must be fixed

All quality checks must pass before code can be merged. The workflows will fail if any linting errors are detected.

### Configuration Files

Linting behavior is configured through:

- `.shellcheckrc` - shellcheck configuration
- `.pylintrc` - pylint configuration
- `.yamllint.yml` - yamllint configuration
- `.markdownlint.yaml` - markdownlint configuration
