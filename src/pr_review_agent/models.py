from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import Enum
import json


class Severity(str, Enum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


@dataclass(frozen=True)
class Finding:
    severity: Severity
    title: str
    explanation: str
    proposed_comment: str
    path: str
    line: int
    confidence: float

    def validate(self) -> None:
        if self.line < 1:
            raise ValueError("Finding line must be positive")
        if not 0 <= self.confidence <= 1:
            raise ValueError("Confidence must be between 0 and 1")
        if not self.proposed_comment.strip():
            raise ValueError("A proposed comment is required")


@dataclass(frozen=True)
class ReviewResult:
    repository: str
    pull_request: int
    head_sha: str
    reviewer: str
    findings: tuple[Finding, ...]
    publish_allowed: bool = False

    def validate(self) -> None:
        if self.pull_request < 1:
            raise ValueError("Pull request number must be positive")
        if self.publish_allowed:
            raise ValueError("Analysis results cannot authorize publication")
        for finding in self.findings:
            finding.validate()

    def to_json(self) -> str:
        self.validate()
        return json.dumps(asdict(self), ensure_ascii=False, indent=2)

