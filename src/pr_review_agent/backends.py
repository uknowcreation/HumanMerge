from __future__ import annotations

import json
import os
import selectors
import shutil
import subprocess
import time
from dataclasses import dataclass
from typing import Any, Protocol, Sequence
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


class BackendError(RuntimeError):
    """A safe, user-facing analysis backend error."""


@dataclass(frozen=True)
class ModelOption:
    id: str
    display_name: str
    description: str = ""
    is_default: bool = False

    @property
    def menu_title(self) -> str:
        suffix = " · recommandé" if self.is_default else ""
        details = f" — {self.description}" if self.description else ""
        return f"{self.display_name}{suffix}{details}"


class AnalysisBackend(Protocol):
    id: str
    display_name: str
    auth_kind: str

    def is_available(self) -> bool:
        ...

    def is_authenticated(self) -> bool:
        ...

    def authenticate(self) -> bool:
        ...

    def list_models(self) -> Sequence[ModelOption]:
        ...


def _run(command: Sequence[str], *, interactive: bool = False) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        check=False,
        capture_output=not interactive,
        text=True,
        timeout=None if interactive else 20,
    )


def _json_request(url: str, headers: dict[str, str]) -> dict[str, Any]:
    request = Request(url, headers=headers)
    try:
        with urlopen(request, timeout=20) as response:  # noqa: S310 - configured API endpoints
            return json.load(response)
    except HTTPError as error:
        raise BackendError(f"Le service a refusé la requête (HTTP {error.code}).") from error
    except URLError as error:
        raise BackendError("Impossible de joindre le service de modèles.") from error


class CodexCliBackend:
    id = "codex-cli"
    display_name = "Codex CLI · abonnement ChatGPT"
    auth_kind = "browser"

    def is_available(self) -> bool:
        return shutil.which("codex") is not None

    def is_authenticated(self) -> bool:
        if not self.is_available():
            return False
        result = _run(("codex", "login", "status"))
        status = f"{result.stdout}\n{result.stderr}".casefold()
        return result.returncode == 0 and "logged in" in status

    def authenticate(self) -> bool:
        if not self.is_available():
            return False
        result = _run(("codex", "login"), interactive=True)
        return result.returncode == 0 and self.is_authenticated()

    def list_models(self) -> Sequence[ModelOption]:
        response = self._app_server_request("model/list", {"includeHidden": False, "limit": 100})
        models = response.get("data", [])
        return tuple(
            ModelOption(
                id=str(item.get("model") or item["id"]),
                display_name=str(item.get("displayName") or item.get("model") or item["id"]),
                description=str(item.get("description", "")),
                is_default=bool(item.get("isDefault", False)),
            )
            for item in models
            if isinstance(item, dict) and (item.get("model") or item.get("id"))
        )

    def _app_server_request(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        process = subprocess.Popen(
            ("codex", "app-server", "--stdio"),
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
        )
        if process.stdin is None or process.stdout is None:
            raise BackendError("Impossible de démarrer le catalogue de modèles Codex.")
        selector = selectors.DefaultSelector()
        selector.register(process.stdout, selectors.EVENT_READ)

        def send(payload: dict[str, Any]) -> None:
            process.stdin.write(json.dumps(payload) + "\n")
            process.stdin.flush()

        def receive(request_id: int, timeout: float = 20) -> dict[str, Any]:
            deadline = time.monotonic() + timeout
            while time.monotonic() < deadline:
                events = selector.select(max(0, deadline - time.monotonic()))
                for key, _ in events:
                    line = key.fileobj.readline()
                    if not line:
                        raise BackendError(
                            "Le catalogue Codex s'est arrêté de façon inattendue."
                        )
                    payload = json.loads(line)
                    if payload.get("id") != request_id:
                        continue
                    if "error" in payload:
                        raise BackendError("Codex n'a pas pu fournir son catalogue de modèles.")
                    result = payload.get("result", {})
                    return result if isinstance(result, dict) else {}
            raise BackendError("Le catalogue Codex ne répond pas.")

        try:
            send(
                {
                    "id": 1,
                    "method": "initialize",
                    "params": {
                        "clientInfo": {"name": "pr-review-agent", "version": "0.1.0"},
                        "capabilities": {},
                    },
                }
            )
            receive(1)
            send({"method": "initialized", "params": {}})
            send({"id": 2, "method": method, "params": params})
            return receive(2)
        except (OSError, json.JSONDecodeError) as error:
            raise BackendError("Impossible de lire le catalogue de modèles Codex.") from error
        finally:
            selector.close()
            process.terminate()
            try:
                process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                process.kill()


class ClaudeCodeBackend:
    id = "claude-code"
    display_name = "Claude Code · abonnement Claude"
    auth_kind = "browser"

    def is_available(self) -> bool:
        return shutil.which("claude") is not None

    def is_authenticated(self) -> bool:
        if not self.is_available():
            return False
        result = _run(("claude", "auth", "status", "--json"))
        if result.returncode != 0:
            return False
        try:
            return bool(json.loads(result.stdout).get("loggedIn"))
        except json.JSONDecodeError:
            return False

    def authenticate(self) -> bool:
        if not self.is_available():
            return False
        result = _run(("claude", "auth", "login", "--claudeai"), interactive=True)
        return result.returncode == 0 and self.is_authenticated()

    def list_models(self) -> Sequence[ModelOption]:
        # Claude Code resolves these public aliases against the signed-in account at execution time.
        return (
            ModelOption("sonnet", "Sonnet", "alias Claude Code", True),
            ModelOption("opus", "Opus", "alias Claude Code"),
            ModelOption("fable", "Fable", "alias Claude Code"),
        )


class OpenAIApiBackend:
    id = "openai-api"
    display_name = "OpenAI API · clé API"
    auth_kind = "environment"
    credential_name = "OPENAI_API_KEY"

    def is_available(self) -> bool:
        return True

    def is_authenticated(self) -> bool:
        return bool(os.environ.get(self.credential_name, "").strip())

    def authenticate(self) -> bool:
        return self.is_authenticated()

    def list_models(self) -> Sequence[ModelOption]:
        token = os.environ.get(self.credential_name, "")
        payload = _json_request(
            "https://api.openai.com/v1/models",
            {"Authorization": f"Bearer {token}", "Accept": "application/json"},
        )
        ids = sorted(
            str(item["id"])
            for item in payload.get("data", [])
            if isinstance(item, dict) and item.get("id")
        )
        return tuple(ModelOption(model_id, model_id) for model_id in ids)


class AnthropicApiBackend:
    id = "anthropic-api"
    display_name = "Anthropic API · clé API"
    auth_kind = "environment"
    credential_name = "ANTHROPIC_API_KEY"

    def is_available(self) -> bool:
        return True

    def is_authenticated(self) -> bool:
        return bool(os.environ.get(self.credential_name, "").strip())

    def authenticate(self) -> bool:
        return self.is_authenticated()

    def list_models(self) -> Sequence[ModelOption]:
        token = os.environ.get(self.credential_name, "")
        payload = _json_request(
            "https://api.anthropic.com/v1/models?limit=1000",
            {
                "x-api-key": token,
                "anthropic-version": "2023-06-01",
                "Accept": "application/json",
            },
        )
        return tuple(
            ModelOption(str(item["id"]), str(item.get("display_name") or item["id"]))
            for item in payload.get("data", [])
            if isinstance(item, dict) and item.get("id")
        )


class OpenAICompatibleBackend:
    id = "openai-compatible"
    display_name = "API compatible OpenAI · serveur personnalisé"
    auth_kind = "environment"
    credential_name = "OPENAI_COMPATIBLE_BASE_URL et OPENAI_COMPATIBLE_API_KEY"

    def is_available(self) -> bool:
        return True

    def is_authenticated(self) -> bool:
        return bool(
            os.environ.get("OPENAI_COMPATIBLE_BASE_URL", "").strip()
            and os.environ.get("OPENAI_COMPATIBLE_API_KEY", "").strip()
        )

    def authenticate(self) -> bool:
        return self.is_authenticated()

    def list_models(self) -> Sequence[ModelOption]:
        base_url = os.environ.get("OPENAI_COMPATIBLE_BASE_URL", "").rstrip("/")
        token = os.environ.get("OPENAI_COMPATIBLE_API_KEY", "")
        payload = _json_request(
            f"{base_url}/models",
            {"Authorization": f"Bearer {token}", "Accept": "application/json"},
        )
        ids = sorted(
            str(item["id"])
            for item in payload.get("data", [])
            if isinstance(item, dict) and item.get("id")
        )
        return tuple(ModelOption(model_id, model_id) for model_id in ids)


class OllamaBackend:
    id = "ollama"
    display_name = "Ollama · modèles locaux"
    auth_kind = "none"

    def is_available(self) -> bool:
        return shutil.which("ollama") is not None

    def is_authenticated(self) -> bool:
        return True

    def authenticate(self) -> bool:
        return True

    def list_models(self) -> Sequence[ModelOption]:
        payload = _json_request("http://127.0.0.1:11434/api/tags", {})
        return tuple(
            ModelOption(str(item["name"]), str(item["name"]))
            for item in payload.get("models", [])
            if isinstance(item, dict) and item.get("name")
        )


def default_backends() -> tuple[AnalysisBackend, ...]:
    return (
        CodexCliBackend(),
        ClaudeCodeBackend(),
        OpenAIApiBackend(),
        AnthropicApiBackend(),
        OpenAICompatibleBackend(),
        OllamaBackend(),
    )
