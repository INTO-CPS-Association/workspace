# Workspace Nouveau
A new workspace image for [DTaaS](https://github.com/INTO-CPS-Association/DTaaS).

# Current state
Based on the KASM core ubuntu image.
Added VSCode service with [code-server](https://github.com/coder/code-server), is started by the [custom_startup.sh](/startup/custom_startup.sh) script. It is for now available on port 8080.
Still need to install Jupyter.
Still need to allow user to sudo.
Still need to allow http.
Still need to remove KASM auth.
Still need to setup reverse proxy to redirect subpaths to tool ports.
Still need to get image under 500 MB.