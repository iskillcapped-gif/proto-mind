"""Frozen Native agent authority and local eval coverage; no provider execution."""
from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import plistlib
import tempfile
import unittest

from proto_mind import native_agent_contract as contract
from proto_mind import native_agent_evals as evals
from proto_mind import native_computer_use as computer_use


class NativeAgentContractTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="native-agent-contract-")
        self.addCleanup(self.temp.cleanup)
        self.workspace = Path(self.temp.name).resolve()

    def build(self, **changes):
        values = dict(model="gpt-5.6-sol", reasoning_effort="high", computer_use=True,
                      criteria=["Verify the requested result."])
        values.update(changes)
        return contract.build_agent_contract(self.workspace, **values)

    def test_contract_is_deterministic_bounded_and_does_not_retain_criteria_text(self):
        first, second = self.build(), self.build()
        self.assertEqual(first, second)
        self.assertEqual(contract.contract_hash(first), contract.contract_hash(second))
        serialized = json.dumps(first)
        self.assertNotIn("Verify the requested result", serialized)
        self.assertFalse(first["limits"]["automatic_retry"])
        self.assertFalse(first["permissions"]["background_execution"])
        self.assertFalse(first["output"]["provider_completion_is_verification"])

    def test_contract_refuses_authority_and_limit_drift(self):
        for path, value in (("retry", True), ("background", True), ("tools", ["get_app_state", "run_shell"])):
            changed = deepcopy(self.build())
            if path == "retry":
                changed["limits"]["automatic_retry"] = value
            elif path == "background":
                changed["permissions"]["background_execution"] = value
            else:
                changed["tools"]["computer_use_enabled_tools"] = value
            with self.subTest(path=path), self.assertRaises(contract.AgentContractError):
                contract.validate_agent_contract(changed)

    def test_runtime_inventory_must_remain_inside_verified_allowlist(self):
        frozen = self.build()
        tools = set(computer_use.COMPUTER_USE_TOOLS)
        self.assertEqual(contract.validate_runtime_inventory(frozen, tools)["computer_use_tools"], sorted(tools))
        with self.assertRaises(contract.AgentContractError):
            contract.validate_runtime_inventory(frozen, tools | {"run_shell"})

    def test_invalid_criteria_are_refused_before_contract_creation(self):
        for criteria in ([""], ["x"] * 21, ["x\x00y"]):
            with self.subTest(criteria=len(criteria)), self.assertRaises(contract.AgentContractError):
                self.build(criteria=criteria)

    def test_local_eval_suite_passes_without_persisting_results(self):
        before = {path.name: path.read_bytes() for path in self.workspace.iterdir() if path.is_file()}
        result = evals.run_cases()
        self.assertEqual(result["passed"], result["total"])
        self.assertEqual(result["total"], 6)
        self.assertTrue(result["read_only"])
        self.assertEqual(before, {path.name: path.read_bytes() for path in self.workspace.iterdir() if path.is_file()})

    def test_native_bundle_and_ui_expose_operator_controlled_automation_recovery(self):
        root = Path(__file__).resolve().parents[2]
        info = plistlib.loads((root / "native" / "Info.plist").read_bytes())
        self.assertEqual(info["CFBundleShortVersionString"], "0.16.0")
        self.assertEqual(info["CFBundleVersion"], "20")
        self.assertIn("Computer Use", info["NSAppleEventsUsageDescription"])
        app = (root / "native" / "Sources" / "AppModel.swift").read_text(encoding="utf-8")
        workspace = (root / "native" / "Sources" / "WorkspaceView.swift").read_text(encoding="utf-8")
        self.assertIn("Privacy_Automation", app)
        self.assertIn("macos_automation_permission_denied", app)
        self.assertIn("Открыть Automation", workspace)
        self.assertTrue((root / "scripts" / "run_native_agent_evals.sh").stat().st_mode & 0o111)


if __name__ == "__main__":
    unittest.main()
