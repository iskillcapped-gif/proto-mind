"""Multiple private logins; fake accounts and no live provider calls."""
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import Mock, patch
from uuid import uuid4

from proto_mind.native_bridge import NativeBackend
from proto_mind.native_codex import CodexSubscription, codex_environment
from proto_mind.native_private_backup import PrivateBackup
from proto_mind.native_private_restore import without_authority


class CodexAccountTests(TestCase):
    def setUp(self):
        temp = TemporaryDirectory(prefix="pm-accounts-")
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name).resolve() / "project"
        self.state = Path(temp.name).resolve() / "native"
        self.account = str(uuid4())

    def backend(self, account=None, **kwargs):
        value = NativeBackend(self.root, self.state, codex_account=account, **kwargs)
        self.addCleanup(value.close)
        return value

    def test_launch_account_separates_credentials_rpc_workspace_and_registry_without_writes(self):
        main, other = self.backend(), self.backend(self.account)
        self.assertEqual(main.subscription.home, self.state / "codex-profile")
        self.assertEqual(other.subscription.home, self.state / "codex-accounts" / self.account / "codex-profile")
        self.assertNotEqual(main.subscription.workspace, other.subscription.workspace)
        self.assertNotEqual(main.subscription.threads.path, other.subscription.threads.path)
        self.assertEqual(main.state_dir, other.state_dir)
        self.assertEqual(main.work_sessions.directory, other.work_sessions.directory)
        self.assertFalse(self.state.exists())
        # The child environment cannot accidentally reuse a desktop/other profile.
        env = codex_environment(other.subscription.home)
        self.assertEqual(env["CODEX_HOME"], str(other.subscription.home))

    def test_invalid_launch_account_cannot_choose_arbitrary_paths(self):
        for value in ["", "../other", "/tmp/profile", self.account.upper(), "default", 42]:
            with self.subTest(value=value), self.assertRaises((ValueError, TypeError, AttributeError)):
                self.backend(value)
        self.assertFalse(self.state.exists())

    def test_linked_account_directory_is_rejected_before_any_connection(self):
        self.state.mkdir()
        (self.state / "codex-accounts").symlink_to(self.root, target_is_directory=True)
        with self.assertRaises(ValueError): self.backend(self.account)
        self.assertFalse(self.root.exists())

    def test_usage_reader_has_same_account_and_an_independent_transport(self):
        clients = []
        def factory(state, **kwargs):
            value = CodexSubscription(state, **kwargs)
            value.account = Mock(return_value={"connected": True, "plan": "plus", "email": "personal@example.invalid"})
            value.connect = Mock(return_value=SimpleNamespace(request=Mock(return_value={
                "rateLimits": {"primary": {"usedPercent": 31, "windowDurationMins": 300}}})))
            value.close = Mock()
            clients.append(value)
            return value
        backend = self.backend(self.account, subscription_factory=factory)
        with backend.busy:
            result = backend.dispatch("account_limits", {}, lambda _: None, "read")
        self.assertEqual(result["email"], "personal@example.invalid")
        self.assertEqual(result["buckets"][0]["windows"][0]["remaining_percent"], 69)
        self.assertEqual(len(clients), 2)
        self.assertEqual(clients[0].home, clients[1].home)
        self.assertEqual(clients[0].threads.path, clients[1].threads.path)
        clients[0].account.assert_not_called()
        clients[1].close.assert_called_once()

    def test_reset_uses_exact_subscription_and_shared_account_bound_journal(self):
        main, other = self.backend(), self.backend(self.account)
        with patch("proto_mind.native_bridge.consume_reset", return_value={"outcome": "fixture"}) as consume:
            other.dispatch("account_reset", {"fixture": True}, lambda _: None, "reset")
        self.assertIs(consume.call_args.args[0], other.subscription)
        self.assertIsNot(consume.call_args.args[0], main.subscription)

    def test_private_backup_excludes_logins_and_discards_all_account_bindings_on_restore(self):
        profile = self.state / "codex-accounts" / self.account / "codex-profile"
        profile.mkdir(parents=True)
        (profile / "auth.json").write_text("synthetic-secret")
        registry = self.state / "codex_account_threads" / self.account
        registry.mkdir(parents=True)
        (registry / "codex_threads.json").write_text('{"fixture":true}')
        name = "native/codex_account_threads/" + self.account + "/codex_threads.json"
        inventory = PrivateBackup(self.root, self.state).inventory()
        self.assertIn(name, inventory)
        self.assertFalse(any("auth.json" in key or "codex-accounts/" in key for key in inventory))
        self.assertIsNone(without_authority(name, b'{"fixture":true}'))

    def test_login_cancel_uses_only_the_owned_pending_id(self):
        main, other = self.backend(), self.backend(self.account)
        rpc = Mock()
        rpc.request.return_value = {"type": "chatgpt", "authUrl": "https://auth.openai.com/test", "loginId": "pending-fixture"}
        other.subscription.connect = Mock(return_value=rpc)
        other.subscription.login()
        other.dispatch("account_login_cancel", {}, lambda _: None, "cancel")
        rpc.request.assert_called_with("account/login/cancel", {"loginId": "pending-fixture"})
        self.assertIsNone(other.subscription.pending_login_id)
        self.assertIsNone(main.subscription.pending_login_id)
