"""Versioned prompt registry with eval-gated promotion.

Default LLM backend is a deterministic stub so the kit runs anywhere
without keys. Set PROMPT_REGISTRY_LLM=claude (with ANTHROPIC_API_KEY)
to route through Claude.
"""
__version__ = "1.0.0"
