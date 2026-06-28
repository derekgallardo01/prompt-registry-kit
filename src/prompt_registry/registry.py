"""Versioned prompt registry - the storage layer.

The registry is a directory of prompts, one subdirectory per prompt name.
Inside each prompt's directory:

    registry/
        customer_complaint_classifier/
            v1.json       # the first version (immutable once written)
            v2.json       # newer experimental version
            golden.json   # gold-labelled eval cases (shared across versions)
            active.txt    # one line: the version currently serving traffic

Each version file declares: the template (with {placeholders}), the model
hint, the params (temperature, max_tokens), a description, and a created_at
timestamp. Versions are immutable - to change a prompt you write a new
version and promote it.

This module owns the file-on-disk format. The runner/evaluator/CLI use
this API rather than touching files directly.
"""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


@dataclass
class PromptVersion:
    """One version of a prompt. Immutable once written to disk."""
    name: str
    version: str            # "v1", "v2", ... - human-friendly + sortable
    template: str           # contains {placeholder} substitutions
    model: str              # e.g., "claude-haiku-4-5-20251001"
    params: dict[str, Any]  # {"temperature": 0.0, "max_tokens": 256, ...}
    description: str        # what changed vs the previous version
    created_at: str         # ISO-8601 timestamp

    def variables(self) -> list[str]:
        """The {placeholder} variables in the template."""
        return sorted(set(re.findall(r"\{(\w+)\}", self.template)))

    def render(self, **kwargs: Any) -> str:
        """Substitute the {placeholders} with provided values."""
        missing = set(self.variables()) - set(kwargs)
        if missing:
            raise KeyError(f"Missing template variables: {sorted(missing)}")
        return self.template.format(**kwargs)


@dataclass
class PromptRegistration:
    """All known versions of one prompt + which one is currently active."""
    name: str
    versions: dict[str, PromptVersion]  # version -> PromptVersion
    active_version: str | None
    eval_cases_path: Path | None        # Path to golden.json, if present

    def active(self) -> PromptVersion | None:
        if not self.active_version:
            return None
        return self.versions.get(self.active_version)

    def latest_version(self) -> str | None:
        """The highest-numbered version (alphanumeric sort works for v1, v2, ..., v9)."""
        if not self.versions:
            return None
        return sorted(self.versions.keys(),
                      key=lambda v: int(v[1:]) if v[1:].isdigit() else 0)[-1]


class Registry:
    """File-backed registry. Owns the on-disk layout."""

    def __init__(self, root: str | Path):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    # ----- Listing -----------------------------------------------------------

    def list_prompts(self) -> list[str]:
        """Names of every prompt registered."""
        return sorted(p.name for p in self.root.iterdir()
                      if p.is_dir() and not p.name.startswith("."))

    def get(self, prompt_name: str) -> PromptRegistration:
        prompt_dir = self.root / prompt_name
        if not prompt_dir.exists():
            raise KeyError(f"No prompt named '{prompt_name}' in {self.root}.")

        versions = {}
        for version_file in sorted(prompt_dir.glob("v*.json")):
            with open(version_file) as f:
                data = json.load(f)
            versions[data["version"]] = PromptVersion(**data)

        active_file = prompt_dir / "active.txt"
        active = active_file.read_text(encoding="utf-8").strip() if active_file.exists() else None

        eval_file = prompt_dir / "golden.json"
        return PromptRegistration(
            name=prompt_name,
            versions=versions,
            active_version=active,
            eval_cases_path=eval_file if eval_file.exists() else None,
        )

    # ----- Writing -----------------------------------------------------------

    def add_version(self, version: PromptVersion) -> Path:
        """Write a new version file. Refuses to overwrite an existing version
        (versions are immutable - write a new version number instead)."""
        prompt_dir = self.root / version.name
        prompt_dir.mkdir(parents=True, exist_ok=True)
        target = prompt_dir / f"{version.version}.json"
        if target.exists():
            raise FileExistsError(
                f"Version {version.version} of '{version.name}' already exists. "
                f"Versions are immutable - bump to the next version instead."
            )
        with open(target, "w", encoding="utf-8") as f:
            json.dump(asdict(version), f, indent=2)
        return target

    def set_active(self, prompt_name: str, version: str) -> None:
        """Promote a version to be the serving (active) one."""
        reg = self.get(prompt_name)  # raises if prompt doesn't exist
        if version not in reg.versions:
            raise KeyError(
                f"Version '{version}' not in registry for '{prompt_name}'. "
                f"Available: {sorted(reg.versions)}"
            )
        active_file = self.root / prompt_name / "active.txt"
        active_file.write_text(version, encoding="utf-8")

    def rollback(self, prompt_name: str) -> str | None:
        """Revert active to the second-latest version (rollback after a bad promote).

        Returns the new active version, or None if there's nothing to roll back to.
        """
        reg = self.get(prompt_name)
        sorted_versions = sorted(reg.versions.keys(),
                                 key=lambda v: int(v[1:]) if v[1:].isdigit() else 0)
        if reg.active_version not in sorted_versions or len(sorted_versions) < 2:
            return None
        current_idx = sorted_versions.index(reg.active_version)
        if current_idx == 0:
            return None
        prev = sorted_versions[current_idx - 1]
        self.set_active(prompt_name, prev)
        return prev


# ----- Helpers --------------------------------------------------------------

def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def default_registry_path() -> Path:
    """The bundled registry path (for the kit's demo + CLI default)."""
    return Path(__file__).resolve().parents[2] / "registry"
