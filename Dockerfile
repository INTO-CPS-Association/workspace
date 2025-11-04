FROM kasmweb/core-ubuntu-noble:1.18.0
USER root

ENV HOME=/home/kasm-default-profile
ENV STARTUPDIR=/dockerstartup
ENV INST_DIR=$STARTUPDIR/install
WORKDIR $HOME

COPY ./kasm_desktop_install/ $INST_DIR

RUN bash ${INST_DIR}/firefox/install_firefox.sh

#RUN curl -fsSL https://code-server.dev/install.sh | sh

RUN $STARTUPDIR/set_user_permission.sh $HOME && \
    chown 1000:0 $HOME && \
    mkdir -p $HOME && \
    chown -R 1000:0 $HOME && \
    rm -Rf ${INST_DIR}

ENV HOME=/home/kasm-user
WORKDIR $HOME
USER 1000

CMD ["--tail-log"]