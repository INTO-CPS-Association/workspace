## Building and running
In one command:
- `docker compose -f compose.minio.keycloak.yml up --build -d`

As seperate build and run steps:
- ***Build:*** `docker compose -f compose.minio.keycloak.yml build`
- ***Run:*** `docker compose -f compose.minio.keycloak.yml up -d`

## Changing Policies
This can be done in two ways:
### A - Semi-live through Keycloak UI
1. Navigate to the user overiwiev in the "workspace" realm in the Keycloak admin UI: http://localhost:8180/admin/master/console/#/workspace/users/
2. Choose the user you want to update the policy for by clicking their username.
3. Go to the "Attributes" tab.
4. Update the values for the "policy" key with the MinIO policies that should apply to the user. The possibilites are:
    - **common-read**: The user has read-access to the common persistent store.
    - **common-write**: The user has read-access AND write-access to the common persistent storage.
    - **user-full-access**: The user has read-access AND write-access to the users private persistent storage.
5. Restart the corresponding workspace to propegate the new access rights:
`docker compose -f compose.minio.keycloak.yml restart workspace-userX`
(replacing userX with the corresponding with either user1 or user2)

### B - Changing the initially loaded policy files
1. Modify the policy attribute in [keycloak/realm-export.json](keycloak/realm-export.json). 
**For example, changing user 2's access, the policy is on line 95:**
```json
{
    ...
    "users":[
        {
            "username": "user2"
            ...
            "attributes": {
                ...
                "policy": ["common-write,user-full-access"]  // was: ["common-read,user-full-access"]
            }
        } ...
    ] ...
}
```

2. Bring all contains down, rebuild and re-run:
```bash
# IMPORTANT: Must reset database volumes to reimport realm configuration
docker compose -f compose.minio.keycloak.yml down -v
docker compose -f compose.minio.keycloak.yml build
docker compose -f compose.minio.keycloak.yml up -d
```

## Notable services
- **Keycloak admin UI** - http://localhost:8180/admin/master/console/#/workspace
    - See keycloak policies, users, groups, services and so on.
- **MinIO Store browser UI** - http://localhost:9001/
    - UI for browsing buckets available to the user, accesible after signing in with user specific username and password.
- **AuthZ Proxy** - http://localhost:8300/
    - What is this?!?
- **User1 VNC** - http://localhost:8100/user1/tools/vnc?path=user1%2Ftools%2Fvnc%2Fwebsockify
- **User2 VNC** - http://localhost:8200/user2/tools/vnc?path=user2%2Ftools%2Fvnc%2Fwebsockify

## Access Creds
### Keycloak Admin
*username* - **admin** // 
*password* - **admin**

### MinIO User1
*username* - **user1** // *password* - **user1password**

### MinIO User2
*username* - **user2** // *password* - **user2password**

## Notes
- The workspaces do not have a basic editor installed by default. Having one is useful for quickly edditing files for testing access rights in the persistent storage. Nano is quickly installed with:
    - `apt-get update && apt-get install nano -y`
- When logging in to the MinIO web UI, the credentials of the user logged in is stored in the browser. To be able to log in as both users, please open the web UI in seperate (private) browser windows.
