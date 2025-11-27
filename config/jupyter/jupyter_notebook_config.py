import os

c = get_config()
c.ServerApp.ip = "0.0.0.0"
c.ServerApp.port = 8090
c.NotebookApp.open_browser = False
c.ServerApp.allow_root = True
c.ServerApp.port_retries = 0
c.ServerApp.quit_button = False
c.ServerApp.allow_remote_access = True
c.ServerApp.disable_check_xsrf = True
c.ServerApp.allow_origin = "*"
c.ServerApp.trust_xheaders = True

# set base url if available
base_url = os.getenv("WORKSPACE_BASE_URL", "/")
if base_url is not None and base_url != "/":
    c.ServerApp.base_url = base_url

c.FileContentsManager.delete_to_trash = False

# Deactivate token -> no authentication
c.IdentityProvider.token = ""