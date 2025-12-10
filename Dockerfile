FROM kasmweb/core-ubuntu-noble:1.18.0
USER root

ENV CODE_SERVER_PORT=8054 \
    HOME=/home/kasm-default-profile \
    INST_DIR=${STARTUPDIR}/install \
    JUPYTER_SERVER_PORT=8090 \
    PERSISTENT_DIR=/workspace \
    STARTUPDIR=/dockerstartup \
    VNCOPTIONS="${VNCOPTIONS} -disableBasicAuth"
WORKDIR $HOME

COPY ./install/ ${INST_DIR}
COPY ./config/kasm_vnc/kasmvnc.yaml /etc/kasmvnc/

RUN bash ${INST_DIR}/firefox/install_firefox.sh && \
    bash ${INST_DIR}/nginx/install_nginx.sh && \
    bash ${INST_DIR}/vscode/install_vscode_server.sh && \
    bash ${INST_DIR}/jupyter/install_jupyter.sh

COPY ./startup/ ${STARTUPDIR}

COPY ./config/nginx/nginx.conf /etc/nginx/nginx.conf

COPY ./config/jupyter/jupyter_notebook_config.py /etc/jupyter/

RUN chown 1000:0 ${HOME} && \
    $STARTUPDIR/set_user_permission.sh ${HOME} && \
    rm -Rf ${INST_DIR}

RUN mkdir ${PERSISTENT_DIR} && \
    chmod a+rwx ${PERSISTENT_DIR}

RUN adduser kasm-user sudo && \
    passwd -d kasm-user
    
EXPOSE 8080

USER 1000

ENTRYPOINT ["/dockerstartup/dtaas_user_setup.sh", "/dockerstartup/kasm_default_profile.sh", "/dockerstartup/vnc_startup.sh", "/dockerstartup/kasm_startup.sh"]
CMD ["--wait"]