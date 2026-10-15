#!/usr/bin/env bash
set -euo pipefail
source "$(dirname "$0")/../arch.sh"

JDK_MAJOR=21
JDK_URL="https://api.adoptium.net/v3/binary/latest/${JDK_MAJOR}/ga/linux/${JAVA_ARCH}/jdk/hotspot/normal/eclipse"

mkdir -p /opt/java
curl -fsSL "${JDK_URL}" | tar -xz -C /opt/java --strip-components=1

# System-wide, layer-safe PATH (survives .docker_set_envs snapshot):
ln -s /opt/java/bin/java  /usr/local/bin/java
ln -s /opt/java/bin/javac /usr/local/bin/javac
cat > /etc/profile.d/java.sh <<'EOF'
export JAVA_HOME=/opt/java
export PATH="${JAVA_HOME}/bin:${PATH}"
EOF

java -version