"""Portable runtime routing and packaging without a real account or private state."""
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import tarfile
import tempfile
import unittest
from unittest.mock import patch

from proto_mind import native_codex as codex
from scripts.package_native_app import extract_runtime, linked_libraries, source_inventory


class PortableRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="pm-portable-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.runtime = self.root / "Moved App.app/Contents/Resources/runtime/codex"
        self.binary = self.runtime / "bin/codex"
        self.binary.parent.mkdir(parents=True)
        shutil.copyfile("/bin/cat", self.binary)
        self.binary.chmod(0o755)
        if Path("/usr/bin/codesign").exists():
            subprocess.run(["/usr/bin/codesign", "--force", "--sign", "-", str(self.binary)], check=True, capture_output=True)

    def test_explicit_runtime_wins_without_system_discovery_and_cannot_fall_back(self):
        with patch.dict(os.environ, {"PROTO_MIND_CODEX_EXECUTABLE": str(self.binary)}), \
                patch.object(codex.shutil, "which", side_effect=AssertionError("system Codex must not be used")):
            self.assertEqual(codex.find_codex_executable(), str(self.binary.resolve()))
            self.binary.unlink()
            with self.assertRaises(codex.CodexConnectionError):
                codex.find_codex_executable()

    def test_portable_child_home_and_path_remain_account_isolated(self):
        home = self.root / "profile/native/codex-profile"
        with patch.dict(os.environ, {"PROTO_MIND_CODEX_EXECUTABLE": str(self.binary), "OPENAI_API_KEY": "fixture-key",
                                     "CODEX_HOME": "/operator/account", "PYTHONPATH": "/operator/code"}):
            env = codex.codex_environment(home)
        self.assertEqual(env["CODEX_HOME"], str(home))
        self.assertEqual(env["HOME"], str(home.parent / "codex-user-home"))
        self.assertEqual(env["PATH"].split(os.pathsep)[0], str(self.binary.parent.resolve()))
        self.assertNotIn("OPENAI_API_KEY", env)
        self.assertNotIn("PYTHONPATH", env)

    @unittest.skipUnless(Path("/usr/bin/sandbox-exec").exists(), "macOS sandbox required")
    def test_relocated_runtime_is_readable_but_neighboring_private_files_are_not(self):
        home, workspace = self.root / "profile/codex-profile", self.root / "empty-workspace"
        home.mkdir(parents=True); workspace.mkdir()
        (home.parent / "codex-user-home").mkdir()
        resource = self.runtime / "codex-resources/resource.txt"
        resource.parent.mkdir(); resource.write_text("runtime-resource")
        (self.runtime / "codex-package.json").write_text('{}')
        secret = self.root / "private.txt"; secret.write_text("never-readable")
        with patch.dict(os.environ, {"PROTO_MIND_CODEX_EXECUTABLE": str(self.binary)}):
            prefix = codex.codex_process_command(str(self.binary), home, workspace)[:3]
        allowed = subprocess.run([*prefix, str(self.binary), str(resource)], capture_output=True, text=True)
        denied = subprocess.run([*prefix, str(self.binary), str(secret)], capture_output=True, text=True)
        self.assertEqual((allowed.returncode, allowed.stdout), (0, "runtime-resource"), allowed.stderr)
        self.assertNotEqual(denied.returncode, 0)
        self.assertNotIn("never-readable", denied.stdout)

    def test_packaging_inventory_excludes_even_tracked_personal_data_and_tests(self):
        repo = self.root / "repo"; repo.mkdir()
        subprocess.run(["git", "init", "-q", str(repo)], check=True)
        names = ["proto_mind/native_bridge.py", "proto_mind/data/identity.json", "proto_mind/tests/test_private.py",
                 "proto_mind/starter_skills.json", "proto_mind/persona/brother-0.1.0.json", "scripts/native_github_cli.py"]
        for name in names:
            path = repo / name; path.parent.mkdir(parents=True, exist_ok=True); path.write_text("fixture")
        subprocess.run(["git", "-C", str(repo), "add", "."], check=True)
        files = source_inventory(repo)
        self.assertEqual(set(map(str, files)), set(names) - {"proto_mind/data/identity.json", "proto_mind/tests/test_private.py"})

    def test_library_inventory_excludes_own_id_but_keeps_every_dependency_kind(self):
        commands = """Load command 0
          cmd LC_ID_DYLIB
      cmdsize 64
         name /DLC/PIL/.dylibs/libavif.dylib (offset 24)
Load command 1
          cmd LC_LOAD_DYLIB
         name @loader_path/libavif.dylib (offset 24)
Load command 2
          cmd LC_LOAD_WEAK_DYLIB
         name /opt/homebrew/lib/missing.dylib (offset 24)
Load command 3
          cmd LC_REEXPORT_DYLIB
         name /usr/lib/libSystem.B.dylib (offset 24)
Load command 4
          cmd LC_LAZY_LOAD_DYLIB
         name /external/With Spaces/lib.dylib (offset 24)
Load command 5
          cmd LC_LOAD_UPWARD_DYLIB
         name @rpath/Parent.framework/Parent (offset 24)
"""
        self.assertEqual(linked_libraries(commands), [
            "@loader_path/libavif.dylib", "/opt/homebrew/lib/missing.dylib",
            "/usr/lib/libSystem.B.dylib", "/external/With Spaces/lib.dylib",
            "@rpath/Parent.framework/Parent",
        ])

    def test_runtime_archive_cannot_escape_or_write_through_links(self):
        for members in [[("../outside", None)], [("runtime/link", "../../outside"), ("runtime/link/value", None)]]:
            archive = self.root / "fixture.tar.gz"
            with tarfile.open(archive, "w:gz") as output:
                for name, link in members:
                    info = tarfile.TarInfo(name)
                    if link:
                        info.type = tarfile.SYMTYPE; info.linkname = link
                        output.addfile(info)
                    else:
                        info.size = 4; output.addfile(info, io.BytesIO(b"test"))
            with self.assertRaises(ValueError):
                extract_runtime(archive, self.root / "extract")
        self.assertFalse((self.root / "outside").exists())


if __name__ == "__main__":
    unittest.main()
