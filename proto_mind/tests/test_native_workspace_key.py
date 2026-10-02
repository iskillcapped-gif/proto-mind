"""A saved folder identity survives a reboot that renumbers the volume's device."""
import unittest

from proto_mind.native_workspace_key import same_workspace, workspace_key


class WorkspaceKeyTests(unittest.TestCase):
    def test_path_and_inode_identify_the_folder(self):
        saved = {"path": "/Users/fixture/project", "device": 16777229, "inode": 50296836}
        self.assertTrue(same_workspace(saved, {**saved, "device": 16777233}))
        self.assertFalse(same_workspace(saved, {**saved, "inode": 50296837}))
        self.assertFalse(same_workspace(saved, {**saved, "path": "/Users/fixture/other"}))
        self.assertEqual(workspace_key(saved), {"path": "/Users/fixture/project", "inode": 50296836})

    def test_missing_or_malformed_identities_compare_as_they_are(self):
        self.assertTrue(same_workspace(None, None))
        self.assertFalse(same_workspace(None, {"path": "/p", "device": 1, "inode": 2}))
        self.assertFalse(same_workspace({"path": "/p"}, {"path": "/p", "device": 1, "inode": 2}))


if __name__ == "__main__":
    unittest.main()
