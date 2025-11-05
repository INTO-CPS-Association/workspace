# Workspace Nouveau
A new workspace image for [DTaaS](https://github.com/INTO-CPS-Association/DTaaS).

We are still very much in the explorative phase. Everything that is working is subject to change.

# Try it out
***Build it*** - `sudo docker build -t workspace-nouveau:latest -f Dockerfile .`

***Run it*** - `sudo docker run -it --shm-size=512m -p 6901:6901 -p 8080:8080 -p 8888:8888 -p 8899:8899 workspace-nouveau:latest`

***Open workspace*** - https://localhost:6901

***Open VSCode*** - http://localhost:8080

***Open Jupyter Notebook*** - http://localhost:8888

***Open Jupyter Lab*** - http://localhost:8899

# Current progress
- Based on the KASM core ubuntu image.
- Added VSCode service with [code-server](https://github.com/coder/code-server), is started by the [custom_startup.sh](/startup/custom_startup.sh) script. It is for now available on port 8080.
- Jupyter is available, Notebook on port 8888, Lab on 8899.
(All ports are subject to change)
- No longer need to authenticate when opening VNC Desktop.
- Still need to allow user to sudo.
- Still need to allow http (Only the virtual desktop itself currently demands HTTPS).
- Still need to setup reverse proxy to redirect subpaths to tool ports.
- Still need to get image under 500 MB.