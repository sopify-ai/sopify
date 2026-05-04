from __future__ import annotations

import unittest

from tests.runtime_test_support import *

from runtime.action_projection import _SUPPORTED_PROJECTION_ACTIONS
from runtime.deterministic_guard import (
    _HOST_ACTION_ALLOWED_ACTIONS,
    _HOST_ACTION_EXPECTED_RESPONSE_MODE,
)
from runtime.failure_recovery import (
    DEFAULT_FAILURE_RECOVERY_SCHEMA_PATH,
    load_failure_recovery_schema,
)
from runtime.manifest import build_bundle_manifest

_RETIRED_HOST_ACTIONS = frozenset({
    "archive_review",
    "continue_host_quick_fix",
    "continue_host_workflow",
    "host_replay_bridge_required",
    "archive_completed",
})


class ContractConsistencyTests(unittest.TestCase):
    def test_allowed_response_modes_match_manifest_limits(self) -> None:
        schema = load_failure_recovery_schema(DEFAULT_FAILURE_RECOVERY_SCHEMA_PATH)
        manifest = build_bundle_manifest(bundle_root=REPO_ROOT, source_root=REPO_ROOT)
        self.assertEqual(
            schema["allowed_response_modes"],
            manifest.limits["runtime_gate_allowed_response_modes"],
        )

    def test_retired_host_actions_not_in_guard_or_projection(self) -> None:
        """Freeze constraint: retired legacy actions must not re-enter the control surface."""
        for action in _RETIRED_HOST_ACTIONS:
            self.assertNotIn(action, _HOST_ACTION_ALLOWED_ACTIONS, f"{action} leaked back into guard allowed_actions")
            self.assertNotIn(action, _HOST_ACTION_EXPECTED_RESPONSE_MODE, f"{action} leaked back into guard response_mode")
            self.assertNotIn(action, _SUPPORTED_PROJECTION_ACTIONS, f"{action} leaked back into projection")

