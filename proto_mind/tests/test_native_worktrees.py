from pathlib import Path
import subprocess
import tempfile
import unittest

from proto_mind.native_worktrees import create, git, main_checkout
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

    def test_isolated_task_shares_its_main_checkout_memory_scope(self):
        from proto_mind.native_bridge import _canonical_hash, memory_scope
        from proto_mind.native_work_sessions import workspace_identity
        with tempfile.TemporaryDirectory() as temporary:
            base=Path(temporary).resolve(); root=base/'repo'; root.mkdir()
            subprocess.run(['/usr/bin/git','init','-q',str(root)],check=True)
            (root/'work.txt').write_text('committed')
            git(root,'add','work.txt')
            git(root,'-c','user.name=Fixture','-c','user.email=fixture@example.invalid','commit','-qm','baseline')
            work=Path(create(WorkspaceReader(str(root)),base/'managed')['path'])
            self.assertEqual(main_checkout(work), root)
            self.assertIsNone(main_checkout(root))
            relative=base/'relative'
            git(root,'-c','worktree.useRelativePaths=true','worktree','add','-q',str(relative))
            self.assertTrue((relative/'.git').read_text().startswith('gitdir: ../'))
            self.assertEqual(main_checkout(relative), root)
            main=workspace_identity(root)
            # The main checkout keeps the exact scope existing records were saved with.
            self.assertEqual(memory_scope(main), _canonical_hash(main))
            self.assertEqual(memory_scope(workspace_identity(work)), memory_scope(main))
            # A copied or crafted .git file that the repository never registered keeps its own scope.
            other=base/'other'; other.mkdir()
            (other/'.git').write_text((work/'.git').read_text())
            self.assertIsNone(main_checkout(other))
            self.assertEqual(memory_scope(workspace_identity(other)), _canonical_hash(workspace_identity(other)))

    def test_isolated_task_reads_and_saves_its_main_checkout_project_notes(self):
        from uuid import uuid4
        from proto_mind.native_project_memory import NativeProjectMemory
        from proto_mind.native_project_recall import ProjectRecall
        from proto_mind.native_work_sessions import workspace_identity
        with tempfile.TemporaryDirectory() as temporary:
            base=Path(temporary).resolve(); root=base/'repo'; root.mkdir(); core=base/'core'; state=base/'private'
            subprocess.run(['/usr/bin/git','init','-q',str(root)],check=True)
            (root/'work.txt').write_text('committed')
            git(root,'add','work.txt')
            git(root,'-c','user.name=Fixture','-c','user.email=fixture@example.invalid','commit','-qm','baseline')
            work=Path(create(WorkspaceReader(str(root)),base/'managed')['path'])
            conversation=str(uuid4())
            def memory(folder): return NativeProjectMemory(core,state,conversation,workspace_identity(folder))
            def save(folder,content):
                note={'kind':'decision','content':content,'basis':'Fixture operator statement','supersedes_id':''}
                preview=memory(folder).preview(note)
                return memory(folder).save({'note':note,'preview_fingerprint':preview['preview_fingerprint'],
                                            'confirmation_token':preview['confirmation_token'],'acknowledge_operator_note':True})['item']
            project=save(root,'Заказы храним в SQLite.')
            self.assertEqual([row['id'] for row in memory(work).listing()['items']],[project['id']])
            recall=ProjectRecall(core,state,conversation=conversation,workspace=workspace_identity(work),
                                 text='Где храним заказы, в SQLite?',mode='full_access')
            self.assertEqual(recall.report['selected_ids'],[project['id']])
            self.assertEqual(recall.notes[0]['workspace'],workspace_identity(work))
            task=save(work,'Тесты запускаем через unittest.')
            self.assertEqual({row['id'] for row in memory(root).listing()['items']},{project['id'],task['id']})
            # A folder with a copied .git file that the repository never registered stays separate.
            other=base/'other'; other.mkdir(); (other/'.git').write_text((work/'.git').read_text())
            self.assertEqual(memory(other).listing()['items'],[])

    def test_non_repository_does_not_create_a_destination(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary).resolve(); destination=root/'managed'
            with self.assertRaises(ValueError): create(WorkspaceReader(str(root)),destination)
            self.assertFalse(destination.exists())
