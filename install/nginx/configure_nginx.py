from subprocess import call
import os
from urllib.parse import quote, unquote

NGINX_FILE = "/etc/nginx/nginx.conf"

# Replace base url placeholders with actual base url -> should 
decoded_base_url = unquote(os.getenv("WORKSPACE_BASE_URL", "").rstrip('/'))
call("sed -i 's@{WORKSPACE_BASE_URL_DECODED}@" + decoded_base_url + "@g' " + NGINX_FILE, shell=True)
# Set url escaped url
encoded_base_url = quote(decoded_base_url, safe="/%")
call("sed -i 's@{WORKSPACE_BASE_URL_ENCODED}@" + encoded_base_url + "@g' " + NGINX_FILE, shell=True)