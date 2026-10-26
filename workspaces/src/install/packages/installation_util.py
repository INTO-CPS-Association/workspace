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
    assert lock_dict["lockVersion"] == LOCK_VERSION, f"Lock file uses version {lock_dict["lockVersion"]} formatting, installation util expects version {LOCK_VERSION}"


def get_dependencies_for_package(package_name: str, **kwargs):
    lock_contents = read_dependency_file()
    check_version(lock_contents)
    
    try:
        packages = lock_contents["packages"]
    except Exception as e:
        raise KeyError(f"No 'packages' found in dependencies") from e

    try:
        dependencies = packages[package_name]
    except Exception as e:
        raise KeyError(f"Package '{package_name}' not found in dependencies") from e
    
    try:
        dependency_type = dependencies["type"]
    except Exception as e:
        raise KeyError(f"The dependency type for package '{package_name}' isn't specified") from e
    
    match dependency_type:
        case "pip-venv":
            return PipVenvDependency(package_name, dependencies, **kwargs)
        case "bin-tar":
            return BinTarDependency(package_name, dependencies, **kwargs)
        case _:
            raise ValueError(f"Unknown dependency type '{dependency_type}' for package '{package_name}'")


class Dependency:
    def __init__(
            self,
            package_name: str,
            package_dict: dict,
            **kwargs
        ):
        self.package_name = package_name
        self.package_dict = package_dict
    

    def default_installation(self):
        raise NotImplementedError("This method should be implemented by subclasses.")


class BinTarDependency(Dependency):
    def __init__(
            self,
            package_name: str,
            package_dict: dict,
            fetch_directory: str = "/tmp",
            installation_directory: str = "/opt",
            binaries_location_in_tarball: str = "bin",
            installed_package_name: str = None,
            system_bin_directory: str = "/usr/local/bin"
        ):
        self.package_name = package_name
        print(ARCHITECTURE)
        match ARCHITECTURE:
            case "amd64" | "x86_64" | "x64":
                self.source = package_dict["amd64"]["source"]
                self.checksum = package_dict["amd64"]["checksum"]
            case "arm64" | "aarch64":
                self.source = package_dict["arm64"]["source"]
                self.checksum = package_dict["arm64"]["checksum"]
        match package_dict["compression"].lower():
            case "gz" | "gzip" | "lz77":
                self.compression = "gz"
            case "xz" | "lzma" | "lzma2":
                self.compression = "xz"
            case _:
                raise ValueError(f"Unknown compression type '{package_dict["compression"]}' for package '{package_name}'")
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


    def default_installation(self):
        self.fetch_tarball()
        self.check_integrity_of_fetched_tarball()
        self.extract_tarball()
        self.move_unfolded_contents_to_installation()
        self.add_to_path()


    def fetch_tarball(self):
        import subprocess
        subprocess.run(
            ["curl", "-fsSL", self.source, "-o", self.fetch_spot],
            check=True
            )


    def check_integrity_of_fetched_tarball(self):
        if not self.fetch_spot.exists():
            raise FileNotFoundError(f"File '{self.fetch_spot}' not found; package '{self.package_name}' hasn't been downloaded.")
        import hashlib
        with open(self.fetch_spot, "rb") as f:
            file_hash = hashlib.sha256(f.read()).hexdigest()
            if file_hash != self.checksum:
                raise ValueError(f"Checksum mismatch for package '{self.package_name}' - was '{file_hash}', expected '{self.checksum}'")


    def extract_tarball(self):
        if not self.fetch_spot.exists():
            raise FileNotFoundError(f"File '{self.fetch_spot}' not found; package '{self.package_name}' hasn't been downloaded.")
        import tarfile
        with tarfile.open(self.fetch_spot, f"r:{self.compression}") as tar:
            tar.extractall(path=self.unfolding_directory)


    def move_unfolded_contents_to_installation(self):
        if not self.unfolding_directory.exists():
            raise FileNotFoundError(f"Directory '{self.unfolding_directory}' not found; package '{self.package_name}' hasn't been extracted.")
        
        os.makedirs(self.installation_directory, exist_ok=True)
        unfolded_contents = list(self.unfolding_directory.iterdir())
        if len(unfolded_contents) == 1 and unfolded_contents[0].is_dir():
            # If the tarball extracted into a single directory, move that directory into the installation_directory.
            single_dir = unfolded_contents[0]
            if self.installed_package_name:
                self.installation_location = self.installation_directory / self.installed_package_name
            else:
                self.installation_location = self.installation_directory / single_dir.name
            single_dir.rename(self.installation_location)
        else:
            # If the tarball extracted multiple items unexpectedly, we raise and error mentioning all the extracted items.
            extracted_items = [item.name for item in unfolded_contents]
            raise ValueError(f"Package '{self.package_name}' extracted multiple items unexpectedly: {extracted_items}. Please check the package source or consider using a different installation method.")


    def add_to_path(self):
        if not hasattr(self, "installation_location"):
            raise AttributeError(f"Installation location for package '{self.package_name}' hasn't been set. Ensure that 'move_unfolded_contents_to_installation' has been called successfully.")
        binaries_path = self.installation_location / self.binaries_location_in_tarball
        if not binaries_path.exists():
            raise FileNotFoundError(f"Binaries path '{binaries_path}' not found; package '{self.package_name}' may not have been installed correctly.")

        os.makedirs(self.system_bin_directory, exist_ok=True)

        for item in binaries_path.iterdir():
            if not (item.is_file() or item.is_symlink()):
                continue
            link = self.system_bin_directory / item.name
            if link.exists() or link.is_symlink():
                link.unlink()
            os.symlink(item, link)


class PipVenvDependency(Dependency):
    def __init__(
            self,
            package_name: str,
            package_dict: dict,
            resulting_binaries: list[str] = [],
            venv_super_directory: str = "/opt",
            installation_directory: str = "/usr/local/bin"
        ):
        self.package_name = package_name
        try:
            self.python_packages = package_dict["pyPackages"]
        except Exception as e:
            raise KeyError(f"Package '{package_name}' has dependency type 'pip-venv' and therefore should include one or more python package definitions in 'pyPackages'") from e
        self.resulting_binaries = resulting_binaries if resulting_binaries else [package_name]
        self.venv_path = Path(os.path.join(venv_super_directory, f"{package_name}_env"))
        self.installation_directory = installation_directory
    

    def default_installation(self):
        self.create_venv()
        self.install_python_packages()
        self.link_binaries()


    def create_venv(self):
        import venv
        venv.create(self.venv_path, with_pip=True)


    def _package_to_pip_format(self, py_package_name: str, py_package_dict: dict) -> str:
        try:
            return f"{py_package_name}=={py_package_dict["version"]}"
        except KeyError:
            return f"{py_package_name}"


    def install_python_packages(self):
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
