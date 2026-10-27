"""Installs the Eclipse Temurin JDK."""
from installation_util import get_dependencies_for_package

get_dependencies_for_package(
    "java",
    installed_package_name="java"
).default_installation()

with open("/etc/profile.d/java.sh", "w", encoding="utf-8") as f:
    f.write("export JAVA_HOME=/opt/java\n")
