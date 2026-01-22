#!/usr/bin/env bash

# KASM images runs any script named "custom_startup.sh" at startup if it is
# located in /dockerstartup dir. Thus, this serves as the default entrypoint
# for any DTaaS specific processes and services.

set -e
if [[ ${DTAAS_DEBUG:-0} == 1 ]]; then
    set -x
fi

STARTUPDIR="${STARTUPDIR:-/dockerstartup}"
PERSISTENT_DIR="${PERSISTENT_DIR:-/workspace}"
if [[ -z "${HOME:-}" ]]; then
    HOME="/home/${MAIN_USER}"
fi

mkdir -p "${HOME}/Desktop" || true

function cleanup {
    trap - SIGINT SIGTERM SIGQUIT SIGHUP ERR
    
    # Kill nginx process group if it exists
    if [[ -n "${DTAAS_PROCS['nginx']:-}" ]]; then
        kill -- -"${DTAAS_PROCS['nginx']}" 2>/dev/null || true
    fi
    
    # Kill all background jobs
    local job_pids
    job_pids="$(jobs -p)"
    if [[ -n "$job_pids" ]]; then
        kill -- $job_pids 2>/dev/null || true
    fi
    
    exit 0
}

# Takes all subprocesses with it if this dies.
trap cleanup SIGINT SIGTERM SIGQUIT SIGHUP ERR

declare -A DTAAS_PROCS
declare -a RESTART_QUEUE

function start_nginx {
    setsid nginx -g 'daemon off;' &
    DTAAS_PROCS['nginx']=$!
}

function start_jupyter {
    jupyter notebook &
    DTAAS_PROCS['jupyter']=$!
}

function start_vscode_server {
    local persistent_dir="$1"
    code-server \
    --auth none \
    --port "${CODE_SERVER_PORT}" \
    --disable-telemetry \
    --disable-update-check \
    --user-data-dir "${HOME}/.vscode-server" \
    "${persistent_dir}" &
    DTAAS_PROCS['vscode']=$!
}

# Mount MinIO buckets before starting services
# Note: mount_minio.sh creates Desktop shortcuts for 'common' and user-specific buckets
if [[ -f "${STARTUPDIR}/mount_minio.sh" ]]; then
    echo "[INFO] Mounting MinIO buckets with policy-based access control"
    bash "${STARTUPDIR}/mount_minio.sh"
else
    echo "[WARNING] mount_minio.sh not found, skipping MinIO bucket mounting"
fi

# Note: Desktop symlinks are now created by mount_minio.sh to avoid conflicts
# The workspace symlink is no longer needed since individual bucket shortcuts exist

start_nginx
start_jupyter
start_vscode_server "${PERSISTENT_DIR}"

# Monitor and resurrect DTaaS services.
sleep 3
while :
do
    RESTART_QUEUE=()

    for process in "${!DTAAS_PROCS[@]}"; do
        if ! kill -0 "${DTAAS_PROCS[${process}]}" 2>/dev/null ; then
            echo "[WARNING] ${process} stopped, queuing restart"
            RESTART_QUEUE+=("${process}")
        fi
    done

    for process in "${RESTART_QUEUE[@]}"; do
        case ${process} in
            nginx)
                echo "[INFO] Restarting nginx"
                kill -- -"${DTAAS_PROCS[${process}]}"
                start_nginx
                ;;
            jupyter)
                echo "[INFO] Restarting Jupyter"
                start_jupyter
                ;;
            vscode)
                echo "[INFO] Restarting VS Code server"
                start_vscode_server "${PERSISTENT_DIR}"
                ;;
            *)
                echo "[WARNING] An unknown service '${process}' unexpectededly monitored by the custom_startup script was reported to have exitted. This is most irregular - check if something is adding processes to the custom_startup scripts list of monitored subprocesses."
                ;;
        esac
    done

    sleep 3
done