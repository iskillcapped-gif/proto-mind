"""Project checkpoints cover native source without caches or external credentials."""
from pathlib import Path
import tarfile
import tempfile
import unittest
from unittest.mock import patch

from proto_mind.backup_utils import create_project_backup


class BackupCoverageTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="proto-checkpoint-test-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name) / "project"

    def write(self, relative, text="fixture"):
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return path

    def test_checkpoint_includes_native_scripts_docs_and_core_but_not_caches(self):
        included = ["proto_mind/data/persistent_memory.json", "native/Sources/AppModel.swift", "native/Package.swift",
                    "native/Tests/NativeChecks.swift", "native/Info.plist", "scripts/run_native.sh", "README.md",
                    "scripts/run_native_agent_evals.sh", "evals/native_agent_contract/cases.jsonl",
                    "proto_mind/native_agent_contract.py", "proto_mind/native_agent_evals.py",
                    "ARCHITECTURE_MAP_V2.md", "PROTO_MIND_ARCHITECT_LEDGER.md", "NATIVE_MACOS_ROADMAP.md", "LICENSE", ".env.example"]
        excluded = ["native/.build/app", "native/.swiftpm/local", "proto_mind/__pycache__/main.pyc", "proto_mind/x.pyo",
                    "proto_mind/.DS_Store", "backups/older.tar.gz", "dist/Native.app/Contents/MacOS/app", ".venv/bin/python",
                    ".env", "auth.json", "codex-profile/auth.json"]
        for name in included + excluded:
            self.write(name)
        before = {name: (self.root / name).read_bytes() for name in included + excluded}
        result = create_project_backup(self.root)
        with tarfile.open(result.archive_path) as archive:
            names = set(archive.getnames())
        self.assertTrue(set(included) <= names)
        self.assertFalse(set(excluded) & names)
        self.assertEqual(before, {name: (self.root / name).read_bytes() for name in included + excluded})

    def test_completed_checkpoint_is_private_and_same_stamp_never_overwrites(self):
        self.write("native/Sources/Fixture.swift", "first")
        first = create_project_backup(self.root, timestamp="same-second")
        original = first.archive_path.read_bytes()
        self.write("native/Sources/Fixture.swift", "second")
        second = create_project_backup(self.root, timestamp="same-second")
        self.assertNotEqual(first.archive_path, second.archive_path)
        self.assertEqual(first.archive_path.read_bytes(), original)
        self.assertEqual(second.archive_path.stat().st_mode & 0o777, 0o600)
        self.assertEqual(list((self.root / "backups").glob("*.tmp")), [])

    def test_failure_does_not_publish_partial_archive_or_replace_previous(self):
        self.write("native/Sources/Fixture.swift")
        first = create_project_backup(self.root, timestamp="first")
        original = first.archive_path.read_bytes()
        with patch.object(tarfile.TarFile, "add", side_effect=OSError("synthetic read failure")), self.assertRaises(OSError):
            create_project_backup(self.root, timestamp="failed")
        self.assertEqual(first.archive_path.read_bytes(), original)
        self.assertEqual({path.name for path in (self.root / "backups").iterdir()}, {first.archive_path.name})

    def test_checkpoint_does_not_follow_native_symlink_to_external_content(self):
        self.write("proto_mind/__init__.py", "")
        outside = self.root.parent / "private-outside"
        outside.mkdir()
        (outside / "secret.txt").write_text("not archived", encoding="utf-8")
        (self.root / "native").symlink_to(outside, target_is_directory=True)
        result = create_project_backup(self.root)
        with tarfile.open(result.archive_path) as archive:
            self.assertTrue(archive.getmember("native").issym())
            self.assertNotIn("native/secret.txt", archive.getnames())


if __name__ == "__main__":
    unittest.main()
