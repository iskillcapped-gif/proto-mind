"""Install pinned document libraries in an isolated directory, never operator site-packages."""
from pathlib import Path
import argparse
import hashlib
import json
import shutil
import subprocess
import tempfile


def prepare(python: Path, destination: Path, requirements: Path, *, marker_name="proto-mind-document-runtime.json"):
    fingerprint = hashlib.sha256(requirements.read_bytes()).hexdigest()
    marker = destination / marker_name
    if marker.is_file():
        try:
            saved = json.loads(marker.read_text())
            inventory = saved.get("files", {})
            if saved.get("requirements_sha256") == fingerprint and inventory and all(
                not Path(name).is_absolute() and ".." not in Path(name).parts and
                (destination / name).is_file() and not (destination / name).is_symlink() and
                hashlib.sha256((destination / name).read_bytes()).hexdigest() == digest
                for name, digest in inventory.items()
            ): return
        except (ValueError, OSError, AttributeError): pass
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="pm-documents-", dir=destination.parent) as temporary:
        staging = Path(temporary) / "packages"
        subprocess.run([str(python), "-m", "pip", "install", "--disable-pip-version-check", "--no-input",
                        "--only-binary=:all:", "--require-hashes", "--ignore-installed", "--no-compile", "--target", str(staging), "-r", str(requirements)], check=True)
        inventory = {str(path.relative_to(staging)): hashlib.sha256(path.read_bytes()).hexdigest()
                     for path in sorted(staging.rglob("*")) if path.is_file()}
        (staging / marker.name).write_text(json.dumps({"requirements_sha256": fingerprint, "files": inventory}, indent=2) + "\n")
        if destination.exists():
            # Only replace a runtime previously created by this helper.
            if not marker.is_file(): raise ValueError("Refusing to replace an unmanaged directory.")
            shutil.rmtree(destination)
        staging.rename(destination)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--python", type=Path, required=True)
    parser.add_argument("--destination", type=Path, required=True)
    args = parser.parse_args()
    prepare(args.python, args.destination, Path(__file__).resolve().parent.parent / "requirements-documents.txt")
