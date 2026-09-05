import json
import os
from pathlib import Path
import subprocess
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import PropertyMock, patch

from proto_mind.native_codex import codex_environment
from proto_mind.native_github import GitHubConnection, repository_name


class GitHubConnectionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.state = self.root / "native"
        self.calls = []
        self.login = "fixture-user"
        self.failure = False
        self.output = None
        self.rows = [{"full_name": "fixture-user/project", "private": True, "description": "A project",
                      "html_url": "https://unexpected.example", "secret": "not-projected"}]
        self.cli = patch.object(GitHubConnection, "executable", new_callable=PropertyMock, return_value="/usr/local/bin/gh")
        self.cli.start(); self.addCleanup(self.cli.stop)
        self.connection = GitHubConnection(self.state, user_home=self.root, runner=self.run_command)

    def run_command(self, command, **kwargs):
        self.calls.append((command, kwargs))
        if self.failure:
            raise subprocess.TimeoutExpired(command, 25)
        if self.output is not None:
            return SimpleNamespace(returncode=0, stdout=self.output)
        if command[1:3] == ["auth", "status"]:
            value = [{"login": self.login, "active": True, "state": "success"}] if self.login else []
        elif command[1] == "api":
            value = self.rows
        else:
            value = [{"number": 12, "title": "Review this", "url": "javascript:untrusted", "body": "not-projected"}]
        return SimpleNamespace(returncode=0, stdout=json.dumps(value))

    def connect(self):
        return self.connection.connect("fixture-user")

    def test_status_does_not_create_connection_or_state(self):
        status = self.connection.status()
        self.assertFalse(status["connected"])
        self.assertEqual(status["available_login"], "fixture-user")
        self.assertFalse(self.state.exists())

    def test_missing_cli_is_actionable_without_subprocess(self):
        with patch.object(GitHubConnection, "executable", new_callable=PropertyMock, return_value=None):
            self.assertFalse(self.connection.status()["installed"])
        self.assertEqual(self.calls, [])

    def test_connection_persists_only_account_and_managed_command(self):
        self.assertTrue(self.connect()["connected"])
        value = json.loads(self.connection.path.read_text())
        self.assertEqual(value["github"], {"login": "fixture-user"})
        self.assertEqual(self.connection.path.stat().st_mode & 0o777, 0o600)
        helper = self.state / "integration-bin/proto-github"
        self.assertEqual(helper.stat().st_mode & 0o777, 0o700)
        self.assertNotIn("token", helper.read_text())
        restarted = GitHubConnection(self.state, user_home=self.root, runner=self.run_command)
        self.assertTrue(restarted.status()["connected"])

    def test_connect_rechecks_the_displayed_account(self):
        self.login = "changed-user"
        with self.assertRaisesRegex(ValueError, "изменился"):
            self.connect()
        self.assertFalse(self.connection.path.exists())

    def test_account_change_blocks_remote_reads(self):
        self.connect(); self.calls.clear(); self.login = "changed-user"
        with self.assertRaises(ValueError):
            self.connection.repositories()
        self.assertEqual(len(self.calls), 1)
        self.assertFalse(self.connection.status()["connected"])

    def test_disconnect_preserves_gh_sign_in_and_disables_runtime(self):
        self.connect(); self.calls.clear()
        self.connection.disconnect()
        self.assertEqual(self.calls, [])
        self.assertEqual(self.connection.runtime_environment(), {})
        self.assertEqual(self.connection.status()["available_login"], "fixture-user")

    def test_corrupt_configuration_is_not_overwritten(self):
        self.state.mkdir(); self.connection.path.write_text("broken")
        for action in (self.connect, self.connection.disconnect):
            with self.assertRaises(ValueError): action()
        self.assertEqual(self.connection.path.read_text(), "broken")

    def test_configuration_symlink_is_never_followed(self):
        self.state.mkdir(); original = self.root / "original"
        original.write_text("private"); self.connection.path.symlink_to(original)
        with self.assertRaises(ValueError): self.connect()
        self.assertEqual(original.read_text(), "private")

    def test_invalid_connect_input_never_calls_gh(self):
        for login in [None, "", "--help", "account\nsecret", "a/b", "a" * 40]:
            with self.assertRaises(ValueError): self.connection.connect(login)
        self.assertEqual(self.calls, [])

    def test_gh_environment_drops_tokens_debug_and_host_overrides(self):
        with patch.dict(os.environ, {"GH_TOKEN": "secret", "GITHUB_TOKEN": "secret", "GH_DEBUG": "api", "GH_HOST": "evil.example", "BROWSER": "evil", "GIT_CONFIG_COUNT": "99"}):
            env = self.connection.environment()
        self.assertNotIn("secret", json.dumps(env))
        self.assertNotIn("GH_DEBUG", env); self.assertNotIn("BROWSER", env)
        self.assertNotIn("GIT_CONFIG_COUNT", env)
        self.assertEqual(env["HOME"], str(self.root))
        self.assertEqual(env["GH_HOST"], "github.com")

    def test_only_full_mac_gets_connected_helper_and_git_credentials_route(self):
        self.connect()
        chat = codex_environment(self.state / "codex-profile")
        full = codex_environment(self.state / "codex-profile", full_access=True)
        self.assertNotIn("integration-bin", chat["PATH"])
        self.assertNotIn("GIT_CONFIG_COUNT", chat)
        self.assertIn("integration-bin", full["PATH"])
        self.assertEqual(full["HOME"], chat["HOME"])
        self.assertNotEqual(full["HOME"], str(self.root))
        self.assertEqual(full["GIT_CONFIG_KEY_1"], "credential.https://github.com.helper")
        self.assertIn("proto-github", full["GIT_CONFIG_VALUE_1"])
        self.assertNotIn("GH_TOKEN", full)

    def test_runtime_without_connection_is_unchanged_and_read_only(self):
        self.assertEqual(self.connection.runtime_environment(), {})
        self.assertFalse(self.state.exists())

    def test_repository_list_projects_metadata_and_canonical_links(self):
        self.connect(); self.calls.clear()
        value = self.connection.repositories()
        self.assertEqual(value["items"][0]["url"], "https://github.com/fixture-user/project")
        self.assertTrue(value["items"][0]["private"])
        self.assertNotIn("not-projected", json.dumps(value))
        self.assertIsNone(value["next_page"])
        self.assertIn("GET", self.calls[-1][0])

    def test_repository_pagination_and_invalid_pages(self):
        self.connect(); self.rows *= 30
        self.assertEqual(self.connection.repositories(2)["next_page"], 3)
        self.calls.clear()
        for page in [True, 0, -1, 1001, "2"]:
            with self.assertRaises(ValueError): self.connection.repositories(page)
        self.assertEqual(self.calls, [])

    def test_repository_details_are_bounded_reads_with_constructed_urls(self):
        self.connect(); self.calls.clear()
        value = self.connection.repository("fixture-user/project")
        self.assertEqual(value["pr"][0]["url"], "https://github.com/fixture-user/project/pull/12")
        self.assertEqual(value["issue"][0]["url"], "https://github.com/fixture-user/project/issues/12")
        self.assertNotIn("not-projected", json.dumps(value))
        self.assertTrue(all("list" in command or "status" in command for command, _ in self.calls))

    def test_repository_arguments_cannot_be_flags_paths_or_remote_hosts(self):
        for name in ["--help", "a/..", "a/.", "a/b/c", "a/b?x=y", "a/b\n", "https://github.com/a/b", "a/b;echo"]:
            with self.assertRaises(ValueError): self.connection.repository(name)
        self.assertEqual(self.calls, [])
        self.assertEqual(repository_name("a/repo-name_1.2"), "a/repo-name_1.2")

    def test_timeouts_and_bad_json_do_not_leak_subprocess_details(self):
        self.failure = True
        status = self.connection.status()
        self.assertFalse(status["connected"])
        self.assertNotIn("/usr/local/bin", status["notice"])
        self.failure = False; self.output = "secret-not-json"
        with self.assertRaises(ValueError) as error: self.connection._account()
        self.assertNotIn("secret", str(error.exception))

    def test_unknown_parameters_are_rejected_before_gh_or_write(self):
        with self.assertRaises(ValueError): self.connection.dispatch("github_connect", {"login": "fixture-user", "token": "secret"})
        self.assertEqual(self.calls, [])
        self.assertFalse(self.state.exists())

    def test_failed_publish_keeps_the_connection_disabled(self):
        replace = os.replace
        def fail_settings(source, destination):
            if Path(destination) == self.connection.path: raise OSError("disk full")
            replace(source, destination)
        with patch("proto_mind.native_github.os.replace", side_effect=fail_settings):
            with self.assertRaises(OSError): self.connect()
        self.assertEqual(self.connection.runtime_environment(), {})
        with self.assertRaises(ValueError): self.connection.require_connection()

    def test_large_or_malformed_remote_rows_are_rejected(self):
        self.connect()
        self.rows *= 31
        with self.assertRaises(ValueError): self.connection.repositories()
        self.rows = [{"full_name": "other.example/a/b"}]
        with self.assertRaises(ValueError): self.connection.repositories()

    def test_bridge_uses_the_same_connection_and_refuses_busy_mutation(self):
        from proto_mind.native_bridge import NativeBackend
        backend = NativeBackend(self.root / "project", self.state)
        self.addCleanup(backend.close)
        backend.github = self.connection
        emit = lambda _: None
        self.assertTrue(backend.dispatch("github_connect", {"login": "fixture-user"}, emit, "test")["connected"])
        backend.busy.acquire()
        try:
            with self.assertRaises(ValueError): backend.dispatch("github_disconnect", {}, emit, "test")
        finally:
            backend.busy.release()
        self.assertTrue(self.connection.settings()["github"])
        self.assertEqual(backend.agent_grants._grants, {})


if __name__ == "__main__":
    unittest.main()
