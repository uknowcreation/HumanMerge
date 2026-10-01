from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional


VALID_REVIEWERS = {"frontend", "backend", "auto"}
VALID_BACKENDS = {
    "codex-cli",
    "claude-code",
    "openai-api",
    "anthropic-api",
    "openai-compatible",
    "ollama",
}


@dataclass(frozen=True)
class AgentConfig:
    github_user: str
    repositories: tuple[str, ...]
    reviewer: str
    frontend_label: Optional[str]
    backend_label: Optional[str]
    languages: tuple[str, ...]
    analysis_backend: str
    model: str
    output_language: str = "fr"
    require_human_approval: bool = True
    publish_automatically: bool = False

    def validate(self) -> None:
        if self.reviewer not in VALID_REVIEWERS:
            raise ValueError(f"Unknown reviewer: {self.reviewer}")
        if not self.github_user.strip():
            raise ValueError("A GitHub user is required")
        if not self.repositories:
            raise ValueError("At least one GitHub repository is required")
        if self.analysis_backend not in VALID_BACKENDS:
            raise ValueError(f"Unknown analysis backend: {self.analysis_backend}")
        if self.reviewer in {"frontend", "auto"} and not self.frontend_label:
            raise ValueError("A frontend label is required")
        if self.reviewer in {"backend", "auto"} and not self.backend_label:
            raise ValueError("A backend label is required")
        if not self.model.strip():
            raise ValueError("A model name is required")
        if not self.require_human_approval:
            raise ValueError("Human approval is mandatory")
        if self.publish_automatically:
            raise ValueError("Automatic publishing is forbidden")

    def to_yaml(self) -> str:
        self.validate()
        languages = ", ".join(self.languages)
        approval = str(self.require_human_approval).lower()
        automatic = str(self.publish_automatically).lower()
        label_lines = []
        if self.frontend_label:
            label_lines.append(f"    frontend: {self.frontend_label}")
        if self.backend_label:
            label_lines.append(f"    backend: {self.backend_label}")
        labels = "\n".join(label_lines)
        repository_lines = "\n".join(f"    - {repository}" for repository in self.repositories)
        return f"""version: 1

github:
  user: {self.github_user}
  repositories:
{repository_lines}

review:
  mode: {self.reviewer}
  labels:
{labels}
  languages: [{languages}]
  output_language: {self.output_language}

model:
  backend: {self.analysis_backend}
  name: {self.model}

approval:
  required: {approval}
  publish_automatically: {automatic}
"""

    def write(self, destination: Path) -> None:
        destination.write_text(self.to_yaml(), encoding="utf-8")
