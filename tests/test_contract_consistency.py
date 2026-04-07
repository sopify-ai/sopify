from __future__ import annotations

import unittest

from tests.runtime_test_support import *

from runtime.failure_recovery import (
    DEFAULT_FAILURE_RECOVERY_SCHEMA_PATH,
    load_failure_recovery_schema,
)
from runtime.manifest import build_bundle_manifest


class ContractConsistencyTests(unittest.TestCase):
    def test_allowed_response_modes_match_manifest_limits(self) -> None:
        schema = load_failure_recovery_schema(DEFAULT_FAILURE_RECOVERY_SCHEMA_PATH)
        manifest = build_bundle_manifest(bundle_root=REPO_ROOT, source_root=REPO_ROOT)
        self.assertEqual(
            schema["allowed_response_modes"],
            manifest.limits["runtime_gate_allowed_response_modes"],
        )

