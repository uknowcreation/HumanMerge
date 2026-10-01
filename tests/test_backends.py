import json
import subprocess
import unittest
from unittest.mock import patch

from pr_review_agent.backends import (
    ClaudeCodeBackend,
    CodexCliBackend,
    ModelOption,
    OpenAIApiBackend,
)


class BackendTests(unittest.TestCase):
    def test_model_menu_marks_default(self) -> None:
        model = ModelOption("gpt-test", "GPT Test", "pour le code", True)

        self.assertEqual(model.menu_title, "GPT Test · recommandé — pour le code")

    @patch("pr_review_agent.backends.shutil.which", return_value="/usr/local/bin/claude")
    @patch("pr_review_agent.backends._run")
    def test_claude_auth_status_is_parsed(self, run, _which) -> None:
        run.return_value = subprocess.CompletedProcess(
            args=[], returncode=0, stdout=json.dumps({"loggedIn": True}), stderr=""
        )

        self.assertTrue(ClaudeCodeBackend().is_authenticated())

    @patch("pr_review_agent.backends.shutil.which", return_value="/usr/local/bin/codex")
    @patch("pr_review_agent.backends._run")
    def test_codex_accepts_status_written_to_stderr(self, run, _which) -> None:
        run.return_value = subprocess.CompletedProcess(
            args=[], returncode=0, stdout="", stderr="Logged in using ChatGPT\n"
        )

        self.assertTrue(CodexCliBackend().is_authenticated())

    @patch("pr_review_agent.backends.CodexCliBackend._app_server_request")
    def test_codex_models_are_read_from_local_catalog(self, request) -> None:
        request.return_value = {
            "data": [
                {
                    "id": "gpt-test",
                    "model": "gpt-test",
                    "displayName": "GPT Test",
                    "description": "Test model",
                    "isDefault": True,
                }
            ]
        }

        models = CodexCliBackend().list_models()

        self.assertEqual(models[0].id, "gpt-test")
        self.assertTrue(models[0].is_default)

    @patch.dict("os.environ", {"OPENAI_API_KEY": "secret"}, clear=False)
    @patch("pr_review_agent.backends._json_request")
    def test_openai_api_lists_account_models(self, request) -> None:
        request.return_value = {"data": [{"id": "z-model"}, {"id": "a-model"}]}

        models = OpenAIApiBackend().list_models()

        self.assertEqual(tuple(model.id for model in models), ("a-model", "z-model"))


if __name__ == "__main__":
    unittest.main()
