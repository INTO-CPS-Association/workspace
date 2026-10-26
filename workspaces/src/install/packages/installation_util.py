import json
import os
from pathlib import Path

# Determines the lock file formatting that this util works with.
LOCK_VERSION = "0.2.1"

# Default location of the lock file.
DEFAULT_DEPENDENCY_LOCK_FILE = os.path.join(
    os.environ.get("INST_DIR", os.getcwd()),
    "dependencies.lock"
)

# Placement and name of the lock file.
DEPENDENCY_LOCK_FILE = os.environ.get(
    "DEPENDENCY_LOCK_FILE",
    DEFAULT_DEPENDENCY_LOCK_FILE
)

ARCHITECTURE = os.environ.get("TARGETARCH", os.uname().machine).lower()

# Default directory for downloaded files
DEFAULT_FETCH_DIRECTORY = "/tmp"

# Default directory for installation of packages
DEFAULT_INSTALLATION_DIRECTORY = "/opt"

# Default directory for binaries to be linked to (should be in PATH)
DEFAULT_LINK_DIRECTORY = "/usr/local/bin"


def lock_file_location() -> Path:
    """Returns the location of the lock file as a Path object.

    Raises a FileNotFoundError if the lock file doesn't exist.

    :return: Path object to the lock file.
    :rtype: Path
    """
    location = Path(DEPENDENCY_LOCK_FILE).resolve()
    if location.exists():
        return location
    raise FileNotFoundError(f"Lock file not present at '{location}'")


def read_dependency_file() -> dict:
    """Reads the dependency file and returns its contents as a dictionary.

    :return: Dictionary containing the dependency information.
    :rtype: dict
    """
    with open(lock_file_location()) as lock_file:
        return json.load(lock_file)


def check_version(lock_dict: dict):
    """Checks if the lock file version matches the expected version.

    Raises an AssertionError if the versions do not match.

    :param lock_dict: Dictionary containing the lock file contents.
    :type lock_dict: dict
    """
    lock_ver = lock_dict["lockVersion"]
    assert lock_ver == LOCK_VERSION, (
        f"Lock file uses version {lock_ver} formatting, "
        f"installation util expects version {LOCK_VERSION}"
    )


def get_dependencies_for_package(package_name: str, **kwargs):
    """Factory function to get the appropriate Dependency object for a given package.

    :param package_name: Name of the package to retrieve dependencies for.
    :type package_name: str
    :param kwargs: Additional keyword arguments to pass to the Dependency constructor.
    :return: An instance of a subclass of Dependency corresponding to the package's dependency type.
    :rtype: Dependency
    """
    lock_contents = read_dependency_file()
    check_version(lock_contents)

    try:
        packages = lock_contents["packages"]
    except Exception as e:
        raise KeyError("No 'packages' found in dependencies") from e

    try:
        dependencies = packages[package_name]
    except Exception as e:
        raise KeyError(
            f"Package '{package_name}' not found in dependencies"
        ) from e

    try:
        dependency_type = dependencies["type"]
    except Exception as e:
        raise KeyError(
            f"The dependency type for package '{package_name}' "
            "isn't specified"
        ) from e

    match dependency_type:
        case "pip-venv":
            return PipVenvDependency(package_name, dependencies, **kwargs)
        case "bin-tar":
            return BinTarDependency(package_name, dependencies, **kwargs)
        case _:
            raise ValueError(f"Unknown dependency type '{dependency_type}' for package '{package_name}'")


class Dependency:
    """An abstract base class representing a generic dependency.

    Subclasses should implement the default_installation method.
    """
    def __init__(
        self,
        package_name: str,
        package_dict: dict,
        **kwargs
    ):
        self.package_name = package_name
        self.package_dict = package_dict

    def default_installation(self):
        """Abstract method to perform the default installation of the dependency.

        Subclasses must implement this method.
        """
        raise NotImplementedError("This method should be implemented by subclasses.")


class BinTarDependency(Dependency):
    """A class representing a dependency on a tarball containing binaries.

    Running the default_installation method will fetch the tarball, check its
    integrity, extract it, move the contents to the installation directory, and
    add the binaries to the system PATH.
    """
    def __init__(
        self,
        package_name: str,
        package_dict: dict,
        fetch_directory: str = DEFAULT_FETCH_DIRECTORY,
        installation_directory: str = DEFAULT_INSTALLATION_DIRECTORY,
        binaries_location_in_tarball: str = "bin",
        installed_package_name: str = None,
        system_bin_directory: str = DEFAULT_LINK_DIRECTORY
    ):
        super().__init__(package_name, package_dict)
        match ARCHITECTURE:
            case "amd64" | "x86_64" | "x64":
                self.source = package_dict["amd64"]["source"]
                self.checksum = package_dict["amd64"]["checksum"]
            case "arm64" | "aarch64":
                self.source = package_dict["arm64"]["source"]
                self.checksum = package_dict["arm64"]["checksum"]
        compression = package_dict["compression"].lower()
        match compression:
            case "gz" | "gzip" | "lz77":
                self.compression = "gz"
            case "xz" | "lzma" | "lzma2":
                self.compression = "xz"
            case _:
                raise ValueError(
                    f"Unknown compression type '{compression}' "
                    f"for package '{package_name}'"
                )
        self.fetch_spot = Path(os.path.join(
            fetch_directory,
            f"{self.package_name}.tar.{self.compression}"
            ))
        self.unfolding_directory = Path(os.path.join(
            fetch_directory,
            self.package_name
            ))
        self.installation_directory = Path(installation_directory)
        self.binaries_location_in_tarball = binaries_location_in_tarball
        self.installed_package_name = installed_package_name
        self.system_bin_directory = Path(system_bin_directory)

    def set_fetch_directory(self, fetch_directory: str):
        """Sets the directory where the tarball will be fetched.

        :param fetch_directory: The directory to fetch the tarball to.
        :type fetch_directory: str
        """
        self.fetch_spot = Path(os.path.join(
            fetch_directory,
            f"{self.package_name}.tar.{self.compression}"
            ))
        self.unfolding_directory = Path(os.path.join(
            fetch_directory,
            self.package_name
            ))

    def set_installation_directory(self, installation_directory: str):
        """Sets the directory where the package will be installed.

        :param installation_directory: The directory to install the package to.
        :type installation_directory: str
        """
        self.installation_directory = Path(installation_directory)

    def set_binaries_location_in_tarball(self, binaries_location_in_tarball: str):
        """Sets the subdirectory within the tarball where binaries are located.

        :param binaries_location_in_tarball: The subdirectory in the tarball containing binaries.
        :type binaries_location_in_tarball: str
        """
        self.binaries_location_in_tarball = binaries_location_in_tarball

    def set_installed_package_name(self, installed_package_name: str):
        """Sets the name of the package once installed.

        :param installed_package_name: The name to use for the installed package.
        :type installed_package_name: str
        """
        self.installed_package_name = installed_package_name

    def set_system_bin_directory(self, system_bin_directory: str):
        """Sets the directory where symlinks to binaries will be created.

        :param system_bin_directory: The directory to create symlinks in.
        :type system_bin_directory: str
        """
        self.system_bin_directory = Path(system_bin_directory)

    def default_installation(self):
        """Runs the default installation process for the BinTarDependency.

        This method orchestrates the entire installation process, including fetching
        the tarball, checking its integrity, extracting it, moving the contents to
        the installation directory, and adding the binaries to the system PATH.
        """
        self.fetch_tarball()
        self.check_integrity_of_fetched_tarball()
        self.extract_tarball()
        self.move_unfolded_contents_to_installation()
        self.add_to_path()

    def fetch_tarball(self):
        """Fetches the tarball from the specified source URL and saves it to the fetch spot.

        Raises a CalledProcessError if the curl command fails.
        """
        import subprocess
        subprocess.run(
            ["curl", "-fsSL", self.source, "-o", self.fetch_spot],
            check=True
        )

    def check_integrity_of_fetched_tarball(self):
        """Checks the integrity of the fetched tarball against its checksum.

        Raises a ValueError if the checksum doesn't match.
        """
        if not self.fetch_spot.exists():
            raise FileNotFoundError(
                f"File '{self.fetch_spot}' not found; "
                f"package '{self.package_name}' hasn't been "
                "downloaded."
            )
        import hashlib
        with open(self.fetch_spot, "rb") as f:
            file_hash = hashlib.sha256(f.read()).hexdigest()
            if file_hash != self.checksum:
                raise ValueError(
                    f"Checksum mismatch for package "
                    f"'{self.package_name}' - was "
                    f"'{file_hash}', expected '{self.checksum}'"
                )

    def extract_tarball(self):
        """Extracts the tarball to the unfolding directory.

        Raises a FileNotFoundError if the tarball is not found.
        """
        if not self.fetch_spot.exists():
            raise FileNotFoundError(
                f"File '{self.fetch_spot}' not found; "
                f"package '{self.package_name}' hasn't been "
                "downloaded."
            )
        import tarfile
        with tarfile.open(self.fetch_spot, f"r:{self.compression}") as tar:
            tar.extractall(path=self.unfolding_directory)

    def move_unfolded_contents_to_installation(self):
        """Moves the contents of the unfolding directory to the installation directory.

        Raises a FileNotFoundError if the unfolding directory is not found.
        """
        if not self.unfolding_directory.exists():
            raise FileNotFoundError(
                f"Directory '{self.unfolding_directory}' not "
                f"found; package '{self.package_name}' hasn't "
                "been extracted."
            )

        os.makedirs(self.installation_directory, exist_ok=True)
        unfolded_contents = list(self.unfolding_directory.iterdir())
        if len(unfolded_contents) == 1 and unfolded_contents[0].is_dir():
            single_dir = unfolded_contents[0]
            if self.installed_package_name:
                self.installation_location = (
                    self.installation_directory
                    / self.installed_package_name
                )
            else:
                self.installation_location = (
                    self.installation_directory / single_dir.name
                )
            single_dir.rename(self.installation_location)
        else:
            extracted = [item.name for item in unfolded_contents]
            raise ValueError(
                f"Package '{self.package_name}' extracted "
                f"multiple items unexpectedly: {extracted}."
            )

    def add_to_path(self):
        """Adds the binaries from the installation location to the system PATH by creating symlinks.
        """
        if not hasattr(self, "installation_location"):
            raise AttributeError(
                f"Installation location for package "
                f"'{self.package_name}' hasn't been set. "
                "Ensure 'move_unfolded_contents_to_installation'"
                " has been called successfully."
            )
        bin_subdir = self.binaries_location_in_tarball
        binaries_path = self.installation_location / bin_subdir
        if not binaries_path.exists():
            raise FileNotFoundError(
                f"Binaries path '{binaries_path}' not found; "
                f"package '{self.package_name}' may not have "
                "been installed correctly."
            )

        os.makedirs(self.system_bin_directory, exist_ok=True)

        for item in binaries_path.iterdir():
            if not (item.is_file() or item.is_symlink()):
                continue
            link = self.system_bin_directory / item.name
            if link.exists() or link.is_symlink():
                link.unlink()
            os.symlink(item, link)


class PipVenvDependency(Dependency):
    """A class representing a dependency that requires a Python virtual environment and pip packages.

    Running the default_installation method will create a virtual environment,
    install the specified Python packages, and link the resulting binaries to a
    specified directory.
    """
    def __init__(
        self,
        package_name: str,
        package_dict: dict,
        resulting_binaries: list[str] = [],
        venv_super_directory: str = DEFAULT_INSTALLATION_DIRECTORY,
        installation_directory: str = DEFAULT_LINK_DIRECTORY
    ):
        self.package_name = package_name
        try:
            self.python_packages = package_dict["pyPackages"]
        except Exception as e:
            raise KeyError(
                f"Package '{package_name}' has dependency type "
                "'pip-venv' and therefore should include one or "
                "more python package definitions in 'pyPackages'"
            ) from e
        self.resulting_binaries = resulting_binaries if resulting_binaries else [package_name]
        self.venv_path = Path(os.path.join(venv_super_directory, f"{package_name}_env"))
        self.installation_directory = installation_directory

    def set_resulting_binaries(self, resulting_binaries: list[str]):
        """Sets the list of resulting binaries to be linked after installation.

        :param resulting_binaries: List of binary names to link.
        :type resulting_binaries: list[str]
        """
        self.resulting_binaries = resulting_binaries

    def set_venv_super_directory(self, venv_super_directory: str):
        """Sets the super directory where the virtual environment will be created.

        :param venv_super_directory: The directory to create the virtual environment in.
        :type venv_super_directory: str
        """
        self.venv_path = Path(os.path.join(venv_super_directory, f"{self.package_name}_env"))

    def set_installation_directory(self, installation_directory: str):
        """Sets the directory where the resulting binaries will be linked.

        :param installation_directory: The directory to link the binaries in.
        :type installation_directory: str
        """
        self.installation_directory = installation_directory

    def default_installation(self):
        """Runs the default installation process for the PipVenvDependency.

        This method orchestrates the entire installation process, including creating
        the virtual environment, installing the specified Python packages, and linking
        the resulting binaries to the specified directory.
        """
        self.create_venv()
        self.install_python_packages()
        self.link_binaries()

    def create_venv(self):
        """Creates a Python virtual environment at the specified venv_path."""
        import venv
        venv.create(self.venv_path, with_pip=True)

    def _package_to_pip_format(self, py_package_name: str, py_package_dict: dict) -> str:
        """Converts a Python package name and its dictionary to a pip install format string.

        :param py_package_name: The name of the Python package.
        :type py_package_name: str
        :param py_package_dict: The dictionary containing package details, including version.
        :type py_package_dict: dict
        :return: A string in the format 'package_name==version' or just 'package_name' if version is not specified.
        :rtype: str
        """
        try:
            return f"{py_package_name}=={py_package_dict['version']}"
        except KeyError:
            return f"{py_package_name}"

    def install_python_packages(self):
        """Installs the specified Python packages into the virtual environment using pip.

        Raises a FileNotFoundError if the virtual environment hasn't been created.
        """
        if not self.venv_path.exists():
            raise FileNotFoundError("Virtual environment hasn't been created.")

        pip_bin = os.path.join(self.venv_path, "bin", "pip")

        run_command = [pip_bin, "install", "--no-cache-dir"]
        run_command.extend([
            self._package_to_pip_format(package_name, package_dict)
            for package_name, package_dict
            in self.python_packages.items()
            ])

        import subprocess
        subprocess.run(run_command)

    def link_binaries(self):
        """Creates symlinks for the resulting binaries from the virtual
        environment to the installation directory.
        """
        os.makedirs(self.installation_directory, exist_ok=True)

        for resulting_binary in self.resulting_binaries:
            package_binary = Path(os.path.join(
                self.venv_path,
                "bin",
                resulting_binary
                ))

            if not package_binary.exists():
                raise FileNotFoundError(f"Binary '{resulting_binary}' hasn't been installed in the virtual environment.")

            os.symlink(
                package_binary,
                Path(os.path.join(
                    self.installation_directory,
                    resulting_binary
                    ))
                )
