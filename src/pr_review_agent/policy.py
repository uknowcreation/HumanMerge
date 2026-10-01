from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PullRequestMetadata:
    author: str
    labels: frozenset[str]
    is_draft: bool
    state: str
    head_sha: str


@dataclass(frozen=True)
class ReviewPolicy:
    current_user: str
    required_label: str

    def rejection_reason(self, pull_request: PullRequestMetadata) -> str | None:
        if pull_request.state.lower() != "open":
            return "pull request is not open"
        if pull_request.is_draft:
            return "pull request is a draft"
        if pull_request.author.casefold() == self.current_user.casefold():
            return "pull request belongs to the current user"
        if self.required_label not in pull_request.labels:
            return f"missing required label: {self.required_label}"
        return None

    def is_eligible(self, pull_request: PullRequestMetadata) -> bool:
        return self.rejection_reason(pull_request) is None

