# Purpose

The main changes made so far are listed here.

## 21-Jan-2026

* **Keycloak Integration**: Added Keycloak as the default identity provider for authentication
  * Replaced GitLab OAuth with OIDC-based authentication
  * New `keycloak` service in `compose.traefik.secure.yml`
  * Updated `traefik-forward-auth` to use OIDC provider
  * Added persistent volume for Keycloak data
* **Environment Configuration**: Updated `.env.example` with Keycloak-specific variables
  * Maintained backward compatibility with GitLab OAuth
  * Added comprehensive comments for both authentication methods
* **Documentation**: Created comprehensive setup and migration guides
  * [KEYCLOAK_SETUP.md](KEYCLOAK_SETUP.md) - Detailed Keycloak configuration
  * [KEYCLOAK_MIGRATION.md](KEYCLOAK_MIGRATION.md) - Migration guide from GitLab
  * Updated [CONFIGURATION.md](CONFIGURATION.md) to reference Keycloak
  * Updated [TRAEFIK_SECURE.md](TRAEFIK_SECURE.md) with Keycloak instructions
* **Flexibility**: Designed for minimal changes when moving Keycloak external
  * Environment variable based configuration
  * Easy to switch between internal and external Keycloak
  * Can still use GitLab OAuth with minor compose file modifications

## 15-Dec-2025


* Adds both ml-workspace and workspace in one docker compose
  and puts them behind traefik proxy
* Based on the KASM core ubuntu image.
* Added VSCode service with [code-server](https://github.com/coder/code-server),
  is started by the [custom_startup.sh](/startup/custom_startup.sh) script.
* Jupyter is available.
* No longer need to authenticate when opening VNC Desktop.
* User is now a sudoer, can install debian packages, and user password
  can be set at container instantiation (via the environment variable USER_PW).
* All access to services is over http (VNC https is hidden behind reverse proxy).
* Reverse proxy exists, and VNC's websocket is forced to adchere to path structure with 'path' argument as path of http request.
* Still need to get image under 500 MB.
