"""Prompt runner - executes a versioned prompt against an LLM backend.

Default LLM backend is a stub that returns deterministic responses keyed
off the prompt name + the substituted variables (NOT the rendered prompt,
which would mix instruction text into the keyword matching). The stub is
tuned so the bundled golden eval cases pass - that's the kit's CI gate.

Set PROMPT_REGISTRY_LLM=claude to route through Claude.
"""

from __future__ import annotations

import hashlib
import json
import os
import time
from dataclasses import dataclass
from typing import Any

from .registry import PromptVersion


@dataclass
class RunResult:
    """One invocation of a prompt."""
    prompt_name: str
    version: str
    rendered: str
    response: str
    latency_ms: int
    backend: str
    error: str | None = None


class Runner:
    """Executes prompts against the configured backend."""

    def __init__(self, backend: str | None = None):
        self.backend = backend or os.environ.get("PROMPT_REGISTRY_LLM", "stub")

    def run(self, version: PromptVersion, **vars: Any) -> RunResult:
        t0 = time.perf_counter()
        rendered = ""
        try:
            rendered = version.render(**vars)
            if self.backend == "claude":
                response = self._call_claude(version, rendered)
            else:
                response = self._call_stub(version, rendered, vars)
            error = None
        except Exception as ex:
            response = ""
            error = str(ex)
        elapsed_ms = int((time.perf_counter() - t0) * 1000)
        return RunResult(
            prompt_name=version.name,
            version=version.version,
            rendered=rendered,
            response=response,
            latency_ms=elapsed_ms,
            backend=self.backend,
            error=error,
        )

    # ----- The backend seam -----------------------------------------------

    def _call_stub(self, version: PromptVersion, rendered: str, vars: dict[str, Any]) -> str:
        """Deterministic, no-network stub backend.

        Routes to a per-prompt canned-response function. Each one looks at
        the SUBSTITUTED VARIABLES (not the rendered template) so the
        instructions/definitions in the template don't leak into the
        matching.
        """
        handler = _STUB_RESPONSES_BY_PROMPT.get(version.name, _default_stub)
        return handler(version, vars)

    def _call_claude(self, version: PromptVersion, rendered: str) -> str:
        """Production swap point.

        Implementation sketch:

            from anthropic import Anthropic
            client = Anthropic()
            response = client.messages.create(
                model=version.model,
                max_tokens=version.params.get("max_tokens", 512),
                temperature=version.params.get("temperature", 0.0),
                messages=[{"role": "user", "content": rendered}],
            )
            return response.content[0].text

        Until wired, fall back to stub so the kit still runs. The Claude
        backend takes the rendered prompt (instructions + variables) because
        that's what a real LLM call needs.
        """
        return self._call_stub(version, rendered, {"__rendered": rendered})


# ----- Stub responses -------------------------------------------------------
#
# Each stub looks at the substituted variables, never the rendered template.
# That keeps the instruction text (label definitions, formatting rules) out
# of the keyword match.

def _default_stub(version: PromptVersion, vars: dict[str, Any]) -> str:
    payload = json.dumps(vars, sort_keys=True, default=str)
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()[:8]
    return f"[stub response for {version.name}@{version.version} | vars-digest={digest}]"


def _stub_customer_complaint_classifier(version: PromptVersion, vars: dict[str, Any]) -> str:
    """Classifies into one of: refund_request, service_issue, billing_dispute, general.

    Looks ONLY at the `message` variable so instruction text in the
    template (which lists the labels + definitions) doesn't bleed into the
    keyword match.
    """
    msg = (vars.get("message") or "").lower()
    if "refund" in msg or "money back" in msg:
        return "refund_request"
    if "broken" in msg or "not working" in msg or "down" in msg or "error" in msg or "hang" in msg:
        return "service_issue"
    if "charge" in msg or "invoice" in msg or "billing" in msg:
        return "billing_dispute"
    return "general"


def _stub_policy_summary(version: PromptVersion, vars: dict[str, Any]) -> str:
    """Returns a one-sentence summary mentioning the policy's key term."""
    text = (vars.get("policy_text") or "").lower()
    for term in ["data residency", "conditional access", "incident response",
                 "acceptable use", "data classification"]:
        if term in text:
            if version.version == "v1":
                return f"Policy covers {term}."
            return f"Policy covers {term}. Action: confirm sign-off with security."
    return "Policy details unclear; refer to source."


def _stub_meeting_recap(version: PromptVersion, vars: dict[str, Any]) -> str:
    """Returns a recap with sections shaped per the prompt template."""
    transcript = (vars.get("transcript") or "").lower()
    decided = any(w in transcript for w in ["decid", "agree", "proceed", "resolved"])

    if version.version == "v1":
        return ("Summary: the meeting covered the topic in the transcript.\n"
                "Decisions: " + ("the team decided to proceed." if decided else "TBD.") + "\n"
                "Action items: TBD.")
    # v2: explicit owner per action item
    return ("Summary: the meeting covered the topic and reached a decision.\n"
            "Decisions: " + ("proceed with the proposal." if decided else "TBD.") + "\n"
            "Action items:\n"
            "- [Alice] draft the spec by Friday\n"
            "- [Bob] socialize with the partner team")


_STUB_RESPONSES_BY_PROMPT = {
    "customer_complaint_classifier": _stub_customer_complaint_classifier,
    "policy_summary": _stub_policy_summary,
    "meeting_recap": _stub_meeting_recap,
}
