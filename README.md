# Workspace Nouveau

A new workspace image for [DTaaS](https://github.com/INTO-CPS-Association/DTaaS).

We are still very much in the explorative phase. Everything that is
working is subject to change.

## 🦾 Build Workspace Image

*Either*  
Using plain `docker` command:

```ps1
sudo docker build -t workspace-nouveau:latest -f Dockerfile .
```

**Or**
using `docker compose`:

```ps1
sudo docker compose build
```

## :running: Run it

*Either*  
Using plain `docker` command:

```ps1
sudo docker run -it --shm-size=512m \
  -p 8080:8080\
  workspace-nouveau:latest
docker run -d --shm-size=512m \
  -p 8080:8080\
  -e MAIN_USER=dtaas-user --name workspace  workspace-nouveau:latest
```

:point_right: You can change the **MAIN_USER** variable to any other username of your choice.

*OR*  
using `docker compose`:

```ps1
sudo docker compose -f compose.yaml up -d
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
docker compose -f compose.yaml down
```
