FROM kasmweb/core-ubuntu-noble:1.18.0
USER root

ENV HOME=/home/kasm-default-profile
ENV STARTUPDIR=/dockerstartup
ENV INST_DIR=$STARTUPDIR/install
ENV MAIN_USER=kasm-user
WORKDIR $HOME

COPY ./startup/ $STARTUPDIR
COPY ./install/ $INST_DIR

RUN bash ${INST_DIR}/firefox/install_firefox.sh
RUN bash ${INST_DIR}/vscode/install_vscode_server.sh
RUN chmod +x $STARTUPDIR/custom_startup.sh
RUN chmod 755 $STARTUPDIR/custom_startup.sh
EXPOSE 8080

RUN $STARTUPDIR/set_user_permission.sh $HOME && \
    chown 1000:0 $HOME && \
    mkdir -p $HOME && \
    chown -R 1000:0 $HOME && \
    rm -Rf ${INST_DIR}

ENV HOME=/home/$MAIN_USER
WORKDIR $HOME
USER 1000

CMD ["--tail-log"]