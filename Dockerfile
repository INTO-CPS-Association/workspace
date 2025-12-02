FROM kasmweb/core-ubuntu-noble:1.18.0
USER root

ARG MAIN_USER=dtaas-user

ENV CODE_SERVER_PORT=8054 \
    HOME=/home/kasm-default-profile \
    INST_DIR=${STARTUPDIR}/install \
    JUPYTER_SERVER_PORT=8090 \
    MAIN_USER=${MAIN_USER} \
    PERSISTENT_DIR=/workspace \
    STARTUPDIR=/dockerstartup \
    VNCOPTIONS="${VNCOPTIONS} -disableBasicAuth" \
    WORKSPACE_BASE_URL="/${MAIN_USER}"
WORKDIR $HOME

COPY ./startup/ ${STARTUPDIR}
COPY ./install/ ${INST_DIR}
COPY ./config/kasm_vnc/kasmvnc.yaml /etc/kasmvnc/

RUN bash ${INST_DIR}/firefox/install_firefox.sh && \
    bash ${INST_DIR}/nginx/install_nginx.sh && \
    bash ${INST_DIR}/vscode/install_vscode_server.sh && \
    bash ${INST_DIR}/jupyter/install_jupyter.sh

COPY ./config/nginx/nginx.conf /etc/nginx/nginx.conf

RUN python3 ${INST_DIR}/nginx/configure_nginx.py

COPY ./config/jupyter/jupyter_notebook_config.py /etc/jupyter/

RUN chown 1000:0 ${HOME} && \
    $STARTUPDIR/set_user_permission.sh ${HOME} && \
    rm -Rf ${INST_DIR}

RUN mkdir ${PERSISTENT_DIR} && \
    chmod a+rwx ${PERSISTENT_DIR}

ENV HOME=/home/${MAIN_USER}
RUN usermod --login ${MAIN_USER} --move-home --home ${HOME} kasm-user && \
    groupmod --new-name ${MAIN_USER} kasm-user && \
    adduser ${MAIN_USER} sudo && \
    passwd -d ${MAIN_USER}
    
EXPOSE 8080

WORKDIR ${HOME}

USER 1000

ENTRYPOINT ["/dockerstartup/kasm_default_profile.sh", "/dockerstartup/vnc_startup.sh", "/dockerstartup/kasm_startup.sh"]
CMD ["--wait"]