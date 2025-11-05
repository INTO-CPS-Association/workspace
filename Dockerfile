FROM kasmweb/core-ubuntu-noble:1.18.0
USER root

ENV HOME=/home/kasm-default-profile \
    STARTUPDIR=/dockerstartup \
    INST_DIR=${STARTUPDIR}/install \
    MAIN_USER=dtaas-user \
    VNCOPTIONS="${VNCOPTIONS} -disableBasicAuth"
WORKDIR $HOME

COPY ./startup/ ${STARTUPDIR}
COPY ./install/ ${INST_DIR}
COPY ./config/kasm_vnc/kasmvnc.yaml /etc/kasmvnc/

RUN bash ${INST_DIR}/firefox/install_firefox.sh && \
    bash ${INST_DIR}/vscode/install_vscode_server.sh && \
    bash ${INST_DIR}/jupyter/install_jupyter.sh
    
EXPOSE 8080 8888 8899

RUN chown 1000:0 ${HOME} && \
    $STARTUPDIR/set_user_permission.sh ${HOME} && \
    rm -Rf ${INST_DIR}

ENV HOME=/home/${MAIN_USER}
RUN usermod --login ${MAIN_USER} --move-home --home ${HOME} kasm-user && \
    groupmod --new-name ${MAIN_USER} kasm-user
WORKDIR ${HOME}
USER 1000

CMD ["--tail-log"]