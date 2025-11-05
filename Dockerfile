FROM kasmweb/core-ubuntu-noble:1.18.0 AS build-stage
USER root

ARG MAIN_USER=dtaas-user

ENV HOME=/home/kasm-default-profile \
    STARTUPDIR=/dockerstartup \
    INST_DIR=${STARTUPDIR}/install \
    PERSISTENT_DIR=/Workspace \
    VNCOPTIONS="${VNCOPTIONS} -disableBasicAuth" \
    MAIN_USER=${MAIN_USER}
WORKDIR $HOME

COPY ./startup/ ${STARTUPDIR}
COPY ./install/ ${INST_DIR}
COPY ./config/kasm_vnc/kasmvnc.yaml /etc/kasmvnc/

RUN bash ${INST_DIR}/firefox/install_firefox.sh && \
    bash ${INST_DIR}/vscode/install_vscode_server.sh && \
    bash ${INST_DIR}/jupyter/install_jupyter.sh

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

FROM scratch AS squashed-stage
COPY --from=build-stage / /

ARG CODE_SERVER_PORT=8080 \
    DISTRO=ubuntu \
    EXTRA_SH=noop.sh \
    JUPYTER_LAB_PORT=8899 \
    JUPYTER_NOTEBOOK_PORT=8888 \
    LANG='en_US.UTF-8' \
    LANGUAGE='en_US:en' \
    LC_ALL='en_US.UTF-8' \
    MAIN_USER=dtaas-user \
    START_PULSEAUDIO=1 \
    START_XFCE4=1 \
    TZ='Etc/UTC'

ENV AUDIO_PORT=4901 \
    CODE_SERVER_PORT=${CODE_SERVER_PORT} \
    DEBIAN_FRONTEND=noninteractive \
    DISPLAY=:1 \
    DISTRO=$DISTRO \
    GOMP_SPINCOUNT=0 \
    HOME=/home/${MAIN_USER} \
    INST_SCRIPTS=/dockerstartup/install \
    JUPYTER_LAB_PORT=${JUPYTER_LAB_PORT} \
    JUPYTER_NOTEBOOK_PORT=${JUPYTER_NOTEBOOK_PORT} \
    KASMVNC_AUTO_RECOVER=true \
    KASM_VNC_PATH=/usr/share/kasmvnc \
    LANG=$LANG \
    LANGUAGE=$LANGUAGE \
    LC_ALL=$LC_ALL \
    LD_LIBRARY_PATH=/opt/libjpeg-turbo/lib64/:/usr/local/lib/ \
    LD_LIBRARY_PATH=/usr/lib/x86_64-linux-gnu:/usr/lib/i386-linux-gnu${LD_LIBRARY_PATH:+:${LD_LIBRARY_PATH}}:/usr/local/nvidia/lib:/usr/local/nvidia/lib64 \
    MAIN_USER=${MAIN_USER} \
    MAX_FRAME_RATE=24 \
    NO_VNC_PORT=6901 \
    OMP_WAIT_POLICY=PASSIVE \
    PERSISTENT_DIR=/Workspace \
    PULSE_RUNTIME_PATH=/var/run/pulse \
    SDL_GAMECONTROLLERCONFIG="030000005e040000be02000014010000,XInput Controller,platform:Linux,a:b0,b:b1,x:b2,y:b3,back:b8,guide:b16,start:b9,leftstick:b10,rightstick:b11,leftshoulder:b4,rightshoulder:b5,dpup:b12,dpdown:b13,dpleft:b14,dpright:b15,leftx:a0,lefty:a1,rightx:a2,righty:a3,lefttrigger:b6,righttrigger:b7" \
    SHELL=/bin/bash \
    START_PULSEAUDIO=$START_PULSEAUDIO \
    STARTUPDIR=/dockerstartup \
    START_XFCE4=$START_XFCE4 \
    TERM=xterm \
    VNC_COL_DEPTH=24 \
    VNCOPTIONS="-PreferBandwidth -DynamicQualityMin=4 -DynamicQualityMax=7 -DLP_ClipDelay=0 -disableBasicAuth" \
    VNC_PORT=5901 \
    VNC_PORT=5901 \
    VNC_PW=vncpassword \
    VNC_RESOLUTION=1280x1024 \
    VNC_RESOLUTION=1280x720 \
    VNC_VIEW_ONLY_PW=vncviewonlypassword \
    TZ=$TZ
    
EXPOSE $VNC_PORT \
       $NO_VNC_PORT \
       $UPLOAD_PORT \
       $AUDIO_PORT \
       $CODE_SERVER_PORT \
       $JUPYTER_NOTEBOOK_PORT \
       $JUPYTER_LAB_PORT

WORKDIR ${HOME}

USER 1000

ENTRYPOINT ["/dockerstartup/kasm_default_profile.sh", "/dockerstartup/vnc_startup.sh", "/dockerstartup/kasm_startup.sh"]
CMD ["--wait"]