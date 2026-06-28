"""Tests for the Runner + stub backend."""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from prompt_registry.registry import PromptVersion, now_iso  # noqa: E402
from prompt_registry.runner import Runner  # noqa: E402


def _version(name: str, version: str, template: str) -> PromptVersion:
    return PromptVersion(
        name=name, version=version, template=template,
        model="m", params={}, description="", created_at=now_iso(),
    )


def test_runner_returns_result_with_latency_and_backend():
    v = _version("customer_complaint_classifier", "v1", "Classify: {message}")
    r = Runner().run(v, message="I want a refund")
    assert r.prompt_name == "customer_complaint_classifier"
    assert r.version == "v1"
    assert r.backend == "stub"
    assert r.latency_ms >= 0
    assert r.error is None


def test_runner_renders_template_into_rendered_field():
    v = _version("default_prompt", "v1", "Hello {name}")
    r = Runner().run(v, name="world")
    assert r.rendered == "Hello world"


def test_runner_returns_error_when_missing_variable():
    v = _version("customer_complaint_classifier", "v1", "Classify: {message}")
    r = Runner().run(v)  # no message
    assert r.error is not None
    assert "message" in r.error


def test_classifier_stub_examines_message_not_template():
    """The stub must look at vars['message'], not the rendered prompt -
    otherwise instructions like 'one of: refund_request, ...' would always
    match 'refund' and classify everything as refund_request."""
    v = _version("customer_complaint_classifier", "v1",
                 "Classify into one of: refund_request, service_issue, "
                 "billing_dispute, general. Message: {message}")
    r = Runner().run(v, message="Hi, just saying the design looks great.")
    assert r.response == "general"  # NOT refund_request


def test_classifier_stub_handles_refund_message():
    v = _version("customer_complaint_classifier", "v1", "{message}")
    r = Runner().run(v, message="I want my money back.")
    assert r.response == "refund_request"


def test_classifier_stub_handles_service_message():
    v = _version("customer_complaint_classifier", "v1", "{message}")
    r = Runner().run(v, message="The dashboard is broken.")
    assert r.response == "service_issue"


def test_classifier_stub_handles_billing_message():
    v = _version("customer_complaint_classifier", "v1", "{message}")
    r = Runner().run(v, message="There is an unauthorized charge on my invoice.")
    assert r.response == "billing_dispute"


def test_policy_summary_v1_returns_one_sentence():
    v = _version("policy_summary", "v1", "Summarize: {policy_text}")
    r = Runner().run(v, policy_text="This document covers data residency for EU tenants.")
    assert "data residency" in r.response.lower()
    assert "Action:" not in r.response  # v1 has no Action: line


def test_policy_summary_v2_adds_action_line():
    v = _version("policy_summary", "v2", "Summarize: {policy_text}")
    r = Runner().run(v, policy_text="This document covers data residency for EU tenants.")
    assert "Action:" in r.response


def test_meeting_recap_v1_returns_three_sections():
    v = _version("meeting_recap", "v1", "Recap: {transcript}")
    r = Runner().run(v, transcript="We agreed to proceed.")
    for section in ("Summary:", "Decisions:", "Action items:"):
        assert section in r.response


def test_meeting_recap_v2_owners_in_brackets():
    v = _version("meeting_recap", "v2", "Recap: {transcript}")
    r = Runner().run(v, transcript="We agreed to proceed.")
    assert "[Alice]" in r.response or "[Bob]" in r.response


def test_default_backend_is_stub():
    saved = os.environ.pop("PROMPT_REGISTRY_LLM", None)
    try:
        runner = Runner()
        assert runner.backend == "stub"
    finally:
        if saved is not None:
            os.environ["PROMPT_REGISTRY_LLM"] = saved
