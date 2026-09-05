import unittest
from pathlib import Path

from proto_mind.native_agent import AgentRun
from proto_mind.native_file_changes import diff_line_counts, file_change_metadata
from proto_mind.native_work_sessions import public_tool


class FileChangeDisplayTests(unittest.TestCase):
    def test_full_hunks_not_headers_or_preview_are_counted(self):
        diff = "--- a/file\n+++ b/file\n@@ -1,2 +1,3 @@\n unchanged\n-old\n+new\n+++ source line\n"
        self.assertEqual(diff_line_counts(diff), (2, 1))
        diff += "@@ -100 +101,2 @@ a second hunk\n-old\n+one\n+two\n\\ No newline at end of file\n"
        self.assertEqual(diff_line_counts(diff), (4, 2))

    def test_add_delete_empty_and_no_newline(self):
        self.assertEqual(diff_line_counts("@@ -0,0 +1,2 @@\n+one\n+two"), (2, 0))
        self.assertEqual(diff_line_counts("@@ -1 +0,0 @@\n-one\n\\ No newline at end of file\n"), (0, 1))
        self.assertEqual(diff_line_counts("@@ -0,0 +0,0 @@\n"), (0, 0))

    def test_missing_truncated_and_malformed_diffs_are_unknown(self):
        for diff in (None, "", "binary files differ", "+raw preview", "@@ -1 +1 @@\n-old\n",
                     "@@ -0,0 +1 @@\n+one\n+extra", "@@ -1 +1 @@\ntruncated",
                     "@@ -1 +1 @@\n-old\n@@ -2 +2 @@\n-old\n+new", "@@ -" + "9" * 5000 + " +1 @@"):
            with self.subTest(diff=str(diff)[:60]):
                self.assertIsNone(diff_line_counts(diff))

    def test_large_diff_counts_survive_preview_truncation(self):
        run = AgentRun(Path("/synthetic"), lambda _: None)
        item = {"id": "edit", "type": "fileChange", "status": "inProgress", "changes": [
            {"path": "source.txt", "diff": "@@ -0,0 +1,2000 @@\n" + "+source\n" * 2000}]}
        run.record(item, False)
        item["status"] = "completed"
        run.record(item, True)
        self.assertEqual(len(run.items), 1)
        row = run.items["edit"]
        self.assertLess(len(row["diff_preview"]), 3100)
        self.assertEqual(row["file_changes"], [{"path": "source.txt", "additions": 2000, "deletions": 0}])
        saved = public_tool(row)
        self.assertNotIn("file_changes", saved)  # Keep the separate bounded journal contract unchanged.
        self.assertLess(len(saved["diff_preview"]), 800)

    def test_metadata_is_bounded_and_does_not_include_diff_contents(self):
        changes = [{"path": f"file-{i}", "diff": "@@ -0,0 +1 @@\n+PRIVATE CONTENT"} for i in range(70)]
        result = file_change_metadata(changes)
        self.assertEqual(len(result["file_changes"]), 64)
        self.assertTrue(result["file_changes_truncated"])
        self.assertNotIn("PRIVATE", str(result))
        self.assertTrue(file_change_metadata([None, {"path": "bad\npath"}])["file_changes_truncated"])

    def test_journal_stays_unchanged_and_path_metadata_has_a_byte_budget(self):
        legacy = {"kind": "fileChange", "id": "old", "paths": ["a"], "diff_preview": "+partial"}
        self.assertNotIn("file_changes", public_tool(legacy))
        changes = [{"path": "я" * 500 + str(i), "diff": "@@ -0,0 +1 @@\n+x"} for i in range(64)]
        bounded = file_change_metadata(changes)
        self.assertTrue(bounded["file_changes_truncated"])
        self.assertLessEqual(sum(len(item["path"].encode("utf-8")) for item in bounded["file_changes"]), 8192)



if __name__ == "__main__":
    unittest.main()
