from __future__ import annotations

import json
import shutil
import subprocess
from dataclasses import dataclass
from typing import Mapping, Protocol, Sequence


class GitHubError(RuntimeError):
    """Raised when GitHub CLI cannot complete a requested operation."""


class GitHubClient(Protocol):
    def is_available(self) -> bool:
        ...

    def is_authenticated(self) -> bool:
        ...

    def login(self) -> bool:
        ...

    def current_user(self) -> str:
        ...

    def organizations(self) -> Sequence[str]:
        ...

    def repositories(self, owner: str) -> Sequence[str]:
        ...

    def languages(self, repository: str) -> Mapping[str, int]:
        ...

    def labels(self, repository: str) -> Sequence[str]:
        ...


@dataclass(frozen=True)
class RepositoryMetadata:
    languages: tuple[str, ...]
    labels: tuple[str, ...]


class GhGitHubClient:
    """Read GitHub metadata through the user's existing GitHub CLI session."""

    def is_available(self) -> bool:
        return shutil.which("gh") is not None

    def is_authenticated(self) -> bool:
        if not self.is_available():
            return False
        result = subprocess.run(
            ["gh", "auth", "status", "-h", "github.com"],
            capture_output=True,
            text=True,
            check=False,
        )
        return result.returncode == 0

    def login(self) -> bool:
        if not self.is_available():
            return False
        result = subprocess.run(
            ["gh", "auth", "login", "-h", "github.com", "-p", "https", "-w"],
            check=False,
        )
        return result.returncode == 0 and self.is_authenticated()

    def current_user(self) -> str:
        return self._run("api", "user", "--jq", ".login").strip()

    def organizations(self) -> Sequence[str]:
        output = self._run("api", "--paginate", "user/orgs", "--jq", ".[].login")
        return tuple(line for line in output.splitlines() if line)

    def repositories(self, owner: str) -> Sequence[str]:
        output = self._run(
            "repo",
            "list",
            owner,
            "--limit",
            "200",
            "--json",
            "nameWithOwner,isArchived",
            "--jq",
            ".[] | select(.isArchived == false) | .nameWithOwner",
        )
        return tuple(line for line in output.splitlines() if line)

    def languages(self, repository: str) -> Mapping[str, int]:
        payload = self._run("api", f"repos/{repository}/languages")
        parsed = json.loads(payload)
        if not isinstance(parsed, dict):
            raise GitHubError(f"Unexpected language response for {repository}")
        return {str(name): int(size) for name, size in parsed.items()}

    def labels(self, repository: str) -> Sequence[str]:
        output = self._run(
            "label",
            "list",
            "--repo",
            repository,
            "--limit",
            "100",
            "--json",
            "name",
            "--jq",
            ".[].name",
        )
        return tuple(line for line in output.splitlines() if line)

    def _run(self, *arguments: str) -> str:
        result = subprocess.run(
            ["gh", *arguments],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            details = result.stderr.strip() or "unknown GitHub CLI error"
            raise GitHubError(details)
        return result.stdout


def aggregate_metadata(
    github: GitHubClient,
    repositories: Sequence[str],
) -> RepositoryMetadata:
    language_bytes: dict[str, int] = {}
    labels: set[str] = set()
    for repository in repositories:
        for language, size in github.languages(repository).items():
            language_bytes[language] = language_bytes.get(language, 0) + size
        labels.update(github.labels(repository))

    ordered_languages = tuple(
        name.lower()
        for name, _ in sorted(language_bytes.items(), key=lambda item: item[1], reverse=True)
    )
    return RepositoryMetadata(
        languages=ordered_languages,
        labels=tuple(sorted(labels, key=str.casefold)),
    )

