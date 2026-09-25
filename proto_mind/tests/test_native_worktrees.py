from pathlib import Path
import subprocess
import tempfile
import unittest

from proto_mind.native_worktrees import create, git
from proto_mind.native_workspace import WorkspaceReader


class IsolatedWorktreeTests(unittest.TestCase):
    def test_independent_checkout_does_not_copy_or_mutate_dirty_source(self):
        with tempfile.TemporaryDirectory() as temporary:
            base=Path(temporary).resolve(); root=base/'repo'; root.mkdir()
            subprocess.run(['/usr/bin/git','init','-q',str(root)],check=True)
            (root/'work.txt').write_text('committed')
            git(root,'add','work.txt')
            git(root,'-c','user.name=Fixture','-c','user.email=fixture@example.invalid','commit','-qm','baseline')
            original_head=git(root,'rev-parse','HEAD')
            (root/'work.txt').write_text('unsaved work')
            result=create(WorkspaceReader(str(root)),base/'managed')
            work=Path(result['path'])
            self.assertEqual((work/'work.txt').read_text(),'committed')
            self.assertEqual((root/'work.txt').read_text(),'unsaved work')
            self.assertEqual(git(root,'rev-parse','HEAD'),original_head)
            self.assertTrue(result['source_has_uncommitted_changes'])
            self.assertFalse(result['uncommitted_changes_copied'])
            self.assertTrue(result['branch'].startswith('codex/pm-'))
            (work/'work.txt').write_text('subtask edit')
            self.assertEqual((root/'work.txt').read_text(),'unsaved work')

    def test_non_repository_does_not_create_a_destination(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary).resolve(); destination=root/'managed'
            with self.assertRaises(ValueError): create(WorkspaceReader(str(root)),destination)
            self.assertFalse(destination.exists())
