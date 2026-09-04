"""Stable entry point for the core flow suite; cases are grouped by domain."""
import importlib
import unittest

from proto_mind.tests.flow_fixtures import (
    build_test_applied_procedural_skill,
    build_test_durably_archived_procedural_skill,
    build_test_learning_apply,
    build_test_procedural_skill_authoring,
    build_test_procedural_skill_outcome_events,
    build_test_restored_procedural_skill,
    build_test_restored_skill_outcome_events,
)

FLOW_MODULES = (
    'proto_mind.tests.test_flow_action',
    'proto_mind.tests.test_flow_cognitive',
    'proto_mind.tests.test_flow_consolidation',
    'proto_mind.tests.test_flow_context',
    'proto_mind.tests.test_flow_memory_contracts',
    'proto_mind.tests.test_flow_operator_contracts',
    'proto_mind.tests.test_flow_runner_contracts',
    'proto_mind.tests.test_flow_data',
    'proto_mind.tests.test_flow_desktop',
    'proto_mind.tests.test_flow_durable',
    'proto_mind.tests.test_flow_experience',
    'proto_mind.tests.test_flow_grounding',
    'proto_mind.tests.test_flow_learning',
    'proto_mind.tests.test_flow_memory',
    'proto_mind.tests.test_flow_natural',
    'proto_mind.tests.test_flow_procedural',
    'proto_mind.tests.test_flow_proto',
    'proto_mind.tests.test_flow_pyside',
    'proto_mind.tests.test_flow_runner',
    'proto_mind.tests.test_flow_session',
    'proto_mind.tests.test_flow_skill',
)


def load_tests(loader, tests, pattern):
    return unittest.TestSuite(loader.loadTestsFromModule(importlib.import_module(name)) for name in FLOW_MODULES)


if __name__ == "__main__":
    unittest.main()
