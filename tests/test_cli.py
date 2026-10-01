import unittest

from pr_review_agent.cli import CUSTOM_LABEL, Choice, MultiChoice, collect_config
from pr_review_agent.backends import ModelOption


class FakePrompter:
    def __init__(self, selects, checkboxes, texts):
        self.selects = iter(selects)
        self.checkboxes = iter(checkboxes)
        self.texts = iter(texts)
        self.messages = []

    def select(self, message: str, choices: tuple[Choice, ...]) -> str:
        self.messages.append(message)
        return next(self.selects)

    def checkbox(self, message: str, choices: tuple[MultiChoice, ...]) -> tuple[str, ...]:
        self.messages.append(message)
        return tuple(next(self.checkboxes))

    def text(self, message: str, default: str) -> str:
        self.messages.append(message)
        return next(self.texts)


class FakeGitHub:
    def __init__(self, authenticated=True):
        self.authenticated = authenticated
        self.login_called = False

    def is_available(self):
        return True

    def is_authenticated(self):
        return self.authenticated

    def login(self):
        self.login_called = True
        self.authenticated = True
        return True

    def current_user(self):
        return "alice"

    def organizations(self):
        return ("acme",)

    def repositories(self, owner):
        return (f"{owner}/web", f"{owner}/api")

    def languages(self, repository):
        if repository.endswith("/web"):
            return {"TypeScript": 900, "CSS": 100}
        return {"Python": 1000}

    def labels(self, repository):
        return ("front-end", "back-end", "bug")


class FakeBackend:
    id = "codex-cli"
    display_name = "Codex CLI · test"
    auth_kind = "browser"

    def __init__(self, authenticated=True, available=True):
        self.authenticated = authenticated
        self.available = available
        self.login_called = False

    def is_available(self):
        return self.available

    def is_authenticated(self):
        return self.authenticated

    def authenticate(self):
        self.login_called = True
        self.authenticated = True
        return True

    def list_models(self):
        return (ModelOption("gpt-test", "GPT Test", is_default=True),)


class SetupWizardTests(unittest.TestCase):
    def test_authenticated_frontend_uses_scanned_metadata(self) -> None:
        prompter = FakePrompter(
            selects=["alice", "frontend", "front-end", "codex-cli", "gpt-test"],
            checkboxes=[("alice/web",), ("typescript", "css")],
            texts=["fr"],
        )

        config = collect_config(prompter, FakeGitHub(), (FakeBackend(),))

        self.assertEqual(config.github_user, "alice")
        self.assertEqual(config.repositories, ("alice/web",))
        self.assertEqual(config.languages, ("typescript", "css"))
        self.assertEqual(config.frontend_label, "front-end")
        self.assertEqual(config.analysis_backend, "codex-cli")
        self.assertEqual(config.model, "gpt-test")
        self.assertIn("backend: codex-cli", config.to_yaml())
        self.assertNotIn("provider:", config.to_yaml())
        self.assertIsNone(config.backend_label)
        self.assertNotIn("GitHub n'est pas connecté", prompter.messages)
        self.assertFalse(any("reviewer backend" in item for item in prompter.messages))

    def test_offers_login_when_github_is_not_authenticated(self) -> None:
        github = FakeGitHub(authenticated=False)
        prompter = FakePrompter(
            selects=["login", "acme", "backend", "back-end", "codex-cli", "gpt-test"],
            checkboxes=[("acme/api",), ("python",)],
            texts=["fr"],
        )

        config = collect_config(prompter, github, (FakeBackend(),))

        self.assertTrue(github.login_called)
        self.assertEqual(config.repositories, ("acme/api",))
        self.assertEqual(config.languages, ("python",))

    def test_custom_label_is_asked_after_languages(self) -> None:
        prompter = FakePrompter(
            selects=["acme", "backend", CUSTOM_LABEL, "codex-cli", "gpt-test"],
            checkboxes=[("acme/api",), ("python",)],
            texts=["service-review", "fr"],
        )

        config = collect_config(prompter, FakeGitHub(), (FakeBackend(),))

        self.assertEqual(config.backend_label, "service-review")
        language_index = prompter.messages.index("Langages principaux détectés")
        label_index = prompter.messages.index("Quel label GitHub déclenche le reviewer backend ?")
        self.assertLess(language_index, label_index)

    def test_auto_asks_for_both_labels(self) -> None:
        prompter = FakePrompter(
            selects=["acme", "auto", "front-end", "back-end", "codex-cli", "gpt-test"],
            checkboxes=[("acme/web", "acme/api"), ("python", "typescript")],
            texts=["fr"],
        )

        config = collect_config(prompter, FakeGitHub(), (FakeBackend(),))

        self.assertEqual(config.frontend_label, "front-end")
        self.assertEqual(config.backend_label, "back-end")

    def test_model_backend_offers_login_then_discovers_models(self) -> None:
        backend = FakeBackend(authenticated=False)
        prompter = FakePrompter(
            selects=[
                "alice",
                "frontend",
                "front-end",
                "codex-cli",
                "login",
                "gpt-test",
            ],
            checkboxes=[("alice/web",), ("typescript",)],
            texts=["fr"],
        )

        config = collect_config(prompter, FakeGitHub(), (backend,))

        self.assertTrue(backend.login_called)
        self.assertEqual(config.model, "gpt-test")
        self.assertIn("Quel modèle utiliser ?", prompter.messages)

    def test_unavailable_backend_has_an_explicit_error(self) -> None:
        prompter = FakePrompter(
            selects=["alice", "frontend", "front-end", "codex-cli"],
            checkboxes=[("alice/web",), ("typescript",)],
            texts=[],
        )

        with self.assertRaisesRegex(RuntimeError, "n'est pas installé"):
            collect_config(prompter, FakeGitHub(), (FakeBackend(available=False),))

    def test_empty_repository_selection_is_asked_again(self) -> None:
        prompter = FakePrompter(
            selects=["alice", "frontend", "front-end", "codex-cli", "gpt-test"],
            checkboxes=[(), ("alice/web",), ("typescript",)],
            texts=["fr"],
        )

        config = collect_config(prompter, FakeGitHub(), (FakeBackend(),))

        self.assertEqual(config.repositories, ("alice/web",))
        self.assertEqual(
            prompter.messages.count("Quels dépôts surveiller ? · Espace pour cocher"),
            2,
        )


if __name__ == "__main__":
    unittest.main()
