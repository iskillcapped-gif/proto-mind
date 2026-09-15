"""Assemble a relocatable macOS beta from an explicit source and runtime inventory.

No operator state, installed Python environment or Codex account is copied.
Runtime archives are fetched from immutable releases and verified before extraction.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import plistlib
import shutil
import subprocess
import tarfile
import tempfile
import urllib.request


def run(*arguments: str | Path, **kwargs) -> subprocess.CompletedProcess:
    return subprocess.run([str(value) for value in arguments], check=True, **kwargs)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def download(spec: dict, cache: Path) -> Path:
    target = cache / spec["sha256"]
    cache.mkdir(parents=True, exist_ok=True)
    if target.exists() and sha256(target) == spec["sha256"]:
        return target
    with tempfile.NamedTemporaryFile(dir=cache, delete=False) as partial:
        temporary = Path(partial.name)
        try:
            with urllib.request.urlopen(spec["url"], timeout=60) as response:
                shutil.copyfileobj(response, partial)
            partial.close()
            if sha256(temporary) != spec["sha256"]:
                raise ValueError("Runtime download checksum mismatch")
            temporary.replace(target)
        finally:
            temporary.unlink(missing_ok=True)
    return target


def extract_runtime(archive: Path, destination: Path) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    with tarfile.open(archive) as source:
        # Preflight the complete inventory before any extraction, including link targets.
        # Archive headers cannot write through a symlink created by an earlier member.
        members = source.getmembers()
        links = {PurePosixPath(item.name) for item in members if item.issym() or item.islnk()}
        for item in members:
            name = PurePosixPath(item.name)
            if name.is_absolute() or ".." in name.parts or any(parent in links for parent in name.parents):
                raise ValueError("Unsafe runtime archive path")
            if not (item.isfile() or item.isdir() or item.issym() or item.islnk()):
                raise ValueError("Unsupported runtime archive member")
            if item.issym() or item.islnk():
                target = destination / (name.parent if item.issym() else PurePosixPath()) / item.linkname
                if PurePosixPath(item.linkname).is_absolute() or not target.resolve().is_relative_to(destination.resolve()):
                    raise ValueError("Unsafe runtime archive link")
        # data_filter also strips ownership and dangerous modes on supported build Pythons.
        source.extractall(destination, filter="data")


def source_inventory(root: Path) -> list[Path]:
    tracked = run("git", "-C", root, "ls-files", "-z", "--", "proto_mind", "scripts/native_github_cli.py",
                  capture_output=True).stdout.decode().split("\0")
    paths = []
    for raw in tracked:
        if not raw:
            continue
        path = PurePosixPath(raw)
        allowed = (path.parent in {PurePosixPath("proto_mind"), PurePosixPath("proto_mind/reasoners")}
                   and path.suffix == ".py") or (
            path.parent == PurePosixPath("proto_mind/persona") and path.suffix == ".json") or raw in {
                "proto_mind/starter_skills.json", "scripts/native_github_cli.py"}
        if allowed:
            source = root / raw
            if source.is_symlink() or not source.is_file():
                raise ValueError(f"Invalid packaged source: {raw}")
            paths.append(Path(raw))
    if Path("proto_mind/native_bridge.py") not in paths:
        raise ValueError("Native bridge missing from tracked source inventory")
    return sorted(paths)


def macho_files(root: Path) -> list[Path]:
    magic = {bytes.fromhex(value) for value in ("feedface", "cefaedfe", "feedfacf", "cffaedfe", "cafebabe", "bebafeca")}
    result = []
    for path in root.rglob("*"):
        if path.is_file() and not path.is_symlink():
            with path.open("rb") as source:
                if source.read(4) in magic:
                    result.append(path)
    return sorted(result, key=lambda path: len(path.parts), reverse=True)


def sign_app(app: Path, identity: str) -> None:
    options = ["--options", "runtime", "--timestamp"] if identity != "-" else []
    for path in macho_files(app):
        run("/usr/bin/codesign", "--force", "--sign", identity, *options, path, stderr=subprocess.DEVNULL)
    run("/usr/bin/codesign", "--force", "--sign", identity, *options, app)
    run("/usr/bin/codesign", "--verify", "--deep", "--strict", app)


def smoke_runtime(app: Path) -> None:
    resources = app / "Contents/Resources"
    python = resources / "runtime/python/bin/python3"
    executable = resources / "runtime/codex/bin/codex"
    run(python, "--version")
    run(executable, "--version")
    with tempfile.TemporaryDirectory(prefix="pm-package-check-") as temporary:
        profile = Path(temporary)
        env = {key: value for key, value in os.environ.items()
               if key in {"PATH", "HOME", "TMPDIR", "LANG", "LC_ALL", "USER", "SHELL"}}
        env.update(PYTHONPATH=str(resources / "core"), PYTHONDONTWRITEBYTECODE="1", PYTHONNOUSERSITE="1",
                   PROTO_MIND_CODEX_EXECUTABLE=str(executable))
        response = run(python, "-u", "-m", "proto_mind.native_bridge", "--code-root", resources / "core",
            "--project-root", profile / "core", "--state-dir", profile / "native", env=env, cwd=resources / "core",
            input='{"id":"package-check","method":"bootstrap","params":{}}\n',
            capture_output=True, text=True, timeout=30)
        values = [json.loads(line) for line in response.stdout.splitlines()]
        result = next((value for value in values if value.get("id") == "package-check"), {})
        if "error" in result or not result.get("result", {}).get("protocol_version"):
            raise ValueError("Packaged bridge failed to bootstrap a clean profile")
        if result["result"].get("operator_name") or (profile / "core").exists():
            raise ValueError("Bootstrap unexpectedly initialized or imported private core state")


def package(root: Path, binaries: Path, output: Path, cache: Path, identity: str = "-") -> Path:
    if output.exists():
        raise ValueError(f"Output already exists; choose a new release directory: {output}")
    lock = json.loads((root / "native/Distribution/runtime-lock.json").read_text())
    archives = {name: download(spec, cache) for name, spec in lock.items() if isinstance(spec, dict)}
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".portable-build-", dir=output.parent) as temporary:
        release = Path(temporary) / "release"
        app = release / "Proto-Mind.app"
        resources = app / "Contents/Resources"
        executables = app / "Contents/MacOS"
        executables.mkdir(parents=True)
        resources.mkdir()
        for name in ("ProtoMindNative", "ProtoMindPDF"):
            shutil.copy2(binaries / name, executables / name)
        shutil.copytree(binaries / "SwiftTerm_SwiftTerm.bundle", resources / "SwiftTerm_SwiftTerm.bundle")
        plist = plistlib.loads((root / "native/Info.plist").read_bytes())
        plist.update(CFBundleName="Proto-Mind", CFBundleDisplayName="Proto-Mind", CFBundleIdentifier="local.proto-mind.desktop")
        (app / "Contents/Info.plist").write_bytes(plistlib.dumps(plist))
        (resources / "native-config.json").write_text('{"distribution":"portable"}\n')
        runtime = resources / "runtime"
        extract_runtime(archives["python"], runtime)
        extract_runtime(archives["codex"], runtime / "codex")
        files = source_inventory(root)
        for relative in files:
            target = resources / "core" / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(root / relative, target)
        licenses = resources / "Licenses"
        licenses.mkdir()
        shutil.copy2(root / "LICENSE", licenses / "Proto-Mind-LICENSE.txt")
        shutil.copy2(root / "native/Distribution/SwiftTerm-LICENSE.txt", licenses / "SwiftTerm-LICENSE.txt")
        shutil.copy2(archives["codex_license"], licenses / "Codex-LICENSE.txt")
        shutil.copy2(archives["codex_notice"], licenses / "Codex-NOTICE.txt")
        for name in ("zsh_license", "ripgrep_license", "ripgrep_mit", "ripgrep_unlicense", "pcre2_license"):
            shutil.copy2(archives[name], licenses / (name + ".txt"))
        # The stripped Python runtime omits dependency notices. Preserve these from
        # the matching full distribution, without shipping its build tree.
        archive_names = run("/usr/bin/tar", "-tf", archives["python_licenses"], capture_output=True, text=True).stdout.splitlines()
        license_names = [name for name in archive_names if PurePosixPath(name).parent == PurePosixPath("python/licenses")
                         and PurePosixPath(name).name.startswith("LICENSE")]
        if not license_names:
            raise ValueError("Python distribution license inventory is empty")
        for name in license_names:
            content = run("/usr/bin/tar", "-xOf", archives["python_licenses"], name, capture_output=True).stdout
            (licenses / ("Python-" + PurePosixPath(name).name)).write_bytes(content)
        shutil.copy2(root / "native/Distribution/THIRD_PARTY_NOTICES.md", licenses / "README.md")
        run("/bin/bash", root / "scripts/build_native_icon.sh", resources / "ProtoMindCube.icns")
        manifest = {"schema": 1, "version": plist["CFBundleShortVersionString"], "build": plist["CFBundleVersion"],
                    "platform": lock["platform"], "signing": "ad-hoc beta" if identity == "-" else "Developer ID; notarization pending",
                    "source_commit": run("git", "-C", root, "rev-parse", "HEAD", capture_output=True, text=True).stdout.strip(),
                    "source_dirty": bool(run("git", "-C", root, "status", "--porcelain", "--untracked-files=no", capture_output=True).stdout),
                    "native_source_files": {str(path.relative_to(root)): sha256(path) for path in sorted((root / "native/Sources").glob("*.swift"))},
                    "source_files": {str(path): sha256(root / path) for path in files}, "runtimes": lock}
        (resources / "distribution-manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
        sign_app(app, identity)
        smoke_runtime(app)
        shutil.copy2(root / "INSTALL_MACOS.md", release / "START_HERE.md")
        (release / "Applications").symlink_to("/Applications")
        image = Path(temporary) / f"Proto-Mind-{plist['CFBundleShortVersionString']}-arm64{'-beta' if identity == '-' else ''}.dmg"
        run("/usr/bin/hdiutil", "create", "-quiet", "-fs", "HFS+", "-format", "UDZO", "-volname", "Proto-Mind", "-srcfolder", release, image)
        image.replace(release / image.name)
        (release / "SHA256SUMS").write_text(sha256(release / image.name) + "  " + image.name + "\n")
        release.rename(output)
    return output / "Proto-Mind.app"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--binaries", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--cache", type=Path)
    parser.add_argument("--sign-identity", default="-")
    args = parser.parse_args()
    root = Path(__file__).resolve().parent.parent
    app = package(root, args.binaries.resolve(), args.output.resolve(), args.cache or root / "dist/runtime-cache", args.sign_identity)
    print(f"Portable application: {app}")


if __name__ == "__main__":
    main()
