import os

c = get_config()
c.notebookApp.ip = "0.0.0.0"
c.NotebookApp.port = 8090
c.NotebookApp.open_browser = False
c.NotebookApp.allow_root = True
c.NotebookApp.port_retries = 0
c.NotebookApp.quit_button = False
c.NotebookApp.allow_remote_access = True
c.NotebookApp.disable_check_xsrf = True
c.NotebookApp.allow_origin = "*"
c.NotebookApp.trust_xheaders = True

# set base url if available
base_url = os.getenv("WORKSPACE_BASE_URL", "/")
if base_url is not None and base_url != "/":
    c.NotebookApp.base_url = base_url

c.FileContentsManager.delete_to_trash = False

authenticate_via_jupyter = os.getenv("AUTHENTICATE_VIA_JUPYTER", "false")
if authenticate_via_jupyter and authenticate_via_jupyter.lower().strip() != "false":
    # authentication via jupyter is activated

    # Do not allow password change since it currently needs a server restart to accept the new password
    c.NotebookApp.allow_password_change = False

    if authenticate_via_jupyter.lower().strip() == "<generated>":
        # dont do anything to let jupyter generate a token in print out on console
        pass
    # if true, do not set any token, authentication will be activate on another way (e.g. via JupyterHub)
    elif authenticate_via_jupyter.lower().strip() != "true":
        # if not true or false, set value as token
        c.NotebookApp.token = authenticate_via_jupyter
else:
    # Deactivate token -> no authentication
    c.NotebookApp.token = ""