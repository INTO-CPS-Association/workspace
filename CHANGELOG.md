# Purpose

The main changes made so far are listed here.

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
