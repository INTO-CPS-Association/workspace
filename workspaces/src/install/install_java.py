from installation_util import get_dependencies_for_package

get_dependencies_for_package(
    "java"
    ).default_installation()

with open("/etc/profile.d/java.sh", "w") as java_profile:
    java_profile.write(
        "export JAVA_HOME=/opt/java\n"
        "export PATH=$JAVA_HOME/bin:$PATH\n"
    )