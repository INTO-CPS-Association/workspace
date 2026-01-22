#!/usr/bin/env bash

# KASM images runs any script named "custom_startup.sh" at startup if it is
# located in /dockerstartup dir. Thus, this serves as the default entrypoint
# for any DTaaS specific processes and services.

set -e
if [[ ${DTAAS_DEBUG:-0} == 1 ]]; then
    set -x
fi

function cleanup {
    trap - SIGINT SIGTERM SIGQUIT SIGHUP ERR
    kill -- -"${DTAAS_PROCS['nginx']}"
    kill -- "$(jobs -p)"
    exit 0# Takes all subprocesses with it if this dies.
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

function start_user_storage_sync {
    #TODO
    DTAAS_PROCS['user_storage_sync']=$!
}

function start_common_storage_sync {
    #TODO
    DTAAS_PROCS['common_storage_sync']=$!
}

start_nginx
start_jupyter
start_vscode_server "${PERSISTENT_DIR}"
start_user_storage_sync
start_common_storage_sync

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
            user_storage_sync)
                echo "[INFO] Restarting sync of ${PERSISTENT_DIR} to persistent user storage"
                start_user_storage_sync
                ;;
            common_storage_sync)
                echo "[INFO] Restarting sync of ${PERSISTENT_DIR}/${PERSISTENT_COMMON_DIR_NAME} to persistent common storage"
                start_common_storage_sync
                ;;
            *)
                echo "[WARNING] An unknown service '${process}' unexpectededly monitored by the custom_startup script was reported to have exitted. This is most irregular - check if something is adding processes to the custom_startup scripts list of monitored subprocesses."
                ;;
        esac
    done

    sleep 3
done