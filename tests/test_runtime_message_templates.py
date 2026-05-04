from __future__ import annotations

import copy

from tests.runtime_test_support import *

from runtime.message_templates import (
    MESSAGE_TEMPLATE_RENDER_FAILED,
    load_default_host_message_templates,
    render_host_message,
)


class MessageTemplatesTests(unittest.TestCase):
    def test_reason_code_family_prefix_template_renders(self) -> None:
        templates = load_default_host_message_templates()
        result = render_host_message(
            reason_code="recovery.truth_layer_contract_invalid.fail_closed.confirm_decision",
            prompt_mode="request_state_recovery",
            variables={
                "required_host_action_label": "决策确认",
                "contract_fix_hint": "修复契约",
            },
            templates=templates,
        )
        self.assertEqual(result["source_kind"], "reason_code_family_prefix")
        self.assertEqual(result["render_events"], [])
        self.assertIn("决策确认", result["text"])
        self.assertIn("修复契约", result["text"])

    def test_prompt_mode_fallback_is_used_when_no_template_matches(self) -> None:
        templates = load_default_host_message_templates()
        result = render_host_message(
            reason_code="recovery.unknown_reason.smoke",
            prompt_mode="reask_confirm_decision",
            templates=templates,
        )
        self.assertEqual(result["source_kind"], "prompt_mode_fallback")
        self.assertEqual(result["render_events"], [])
        self.assertIn("当前输入还不足以继续", result["text"])

    def test_missing_template_variable_falls_back_without_crashing(self) -> None:
        templates = load_default_host_message_templates()
        result = render_host_message(
            reason_code="recovery.effect_contract_invalid.fail_closed.confirm_decision",
            prompt_mode="safe_retry_after_contract_fix",
            variables={},
            templates=templates,
        )
        self.assertEqual(result["source_kind"], "prompt_mode_fallback")
        self.assertEqual(result["render_events"], [MESSAGE_TEMPLATE_RENDER_FAILED])
        self.assertIn("暂时不能安全执行", result["text"])

    def test_broken_fallback_uses_safe_fallback_message(self) -> None:
        templates = load_default_host_message_templates()
        broken = copy.deepcopy(templates)
        broken["prompt_mode_fallbacks"]["safe_retry_after_contract_fix"]["zh-CN"] = "请先{missing_hint}"
        result = render_host_message(
            reason_code="recovery.effect_contract_invalid.fail_closed.confirm_decision",
            prompt_mode="safe_retry_after_contract_fix",
            variables={},
            templates=broken,
        )
        self.assertEqual(result["source_kind"], "safe_fallback")
        self.assertEqual(result["render_events"], [MESSAGE_TEMPLATE_RENDER_FAILED])
        self.assertIn("暂时不能安全继续", result["text"])
